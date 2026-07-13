"""Bounded in-memory orchestration for asynchronous synthesis jobs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Callable, Literal
import uuid

from .models import SynthesizeResponse
from .providers.base import ProviderError
from .service import SynthesisService


JobStatus = Literal["pending", "completed", "failed"]
UNEXPECTED_JOB_ERROR = "Synthesis job failed unexpectedly."
DELIVERY_CAPACITY_ERROR = "Synthesis result exceeded temporary delivery capacity."


class JobCapacityError(RuntimeError):
    """The configured number of concurrently active jobs is exhausted."""


@dataclass(frozen=True, slots=True)
class JobView:
    job_id: str
    status: JobStatus
    result: SynthesizeResponse | None = None
    error: str | None = None


@dataclass(slots=True)
class _JobRecord:
    # Source text is intentionally never retained in the job registry. It only
    # exists in the active task's arguments until synthesis finishes.
    job_id: str
    owner: str = "local-open-access"
    status: JobStatus = "pending"
    task: asyncio.Task[None] | None = None
    result: SynthesizeResponse | None = None
    error: str | None = None
    terminal_at: float | None = None
    delivered: bool = False
    retained_bytes: int = 0


class JobManager:
    def __init__(
        self,
        service: SynthesisService,
        *,
        max_active_jobs: int = 4,
        max_outstanding_jobs: int = 12,
        max_outstanding_jobs_per_owner: int = 3,
        max_terminal_bytes: int = 128 * 1024 * 1024,
        max_terminal_bytes_per_owner: int = 40 * 1024 * 1024,
        terminal_ttl_seconds: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
        uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    ) -> None:
        if max_active_jobs < 1:
            raise ValueError("max_active_jobs must be positive")
        if max_outstanding_jobs < max_active_jobs:
            raise ValueError("max_outstanding_jobs must be at least max_active_jobs")
        if not 1 <= max_outstanding_jobs_per_owner <= max_outstanding_jobs:
            raise ValueError(
                "max_outstanding_jobs_per_owner must be between 1 and max_outstanding_jobs"
            )
        if max_terminal_bytes < 1:
            raise ValueError("max_terminal_bytes must be positive")
        if not 1 <= max_terminal_bytes_per_owner <= max_terminal_bytes:
            raise ValueError(
                "max_terminal_bytes_per_owner must be between 1 and max_terminal_bytes"
            )
        if terminal_ttl_seconds <= 0:
            raise ValueError("terminal_ttl_seconds must be positive")
        self._service = service
        self._max_active_jobs = max_active_jobs
        self._max_outstanding_jobs = max_outstanding_jobs
        self._max_outstanding_jobs_per_owner = max_outstanding_jobs_per_owner
        self._max_terminal_bytes = max_terminal_bytes
        self._max_terminal_bytes_per_owner = max_terminal_bytes_per_owner
        self._terminal_ttl_seconds = terminal_ttl_seconds
        self._clock = clock
        self._uuid_factory = uuid_factory
        self._jobs: dict[str, _JobRecord] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def create(
        self,
        text: str,
        rate: float,
        *,
        owner: str = "local-open-access",
        admit: Callable[[], None] | None = None,
    ) -> str:
        async with self._lock:
            self._prune_terminal_locked()
            if self._closed:
                raise RuntimeError("job manager is closed")
            active = sum(job.status == "pending" for job in self._jobs.values())
            if active >= self._max_active_jobs:
                raise JobCapacityError("too many active synthesis jobs")
            if len(self._jobs) >= self._max_outstanding_jobs:
                raise JobCapacityError("too many outstanding synthesis jobs")
            owned = sum(job.owner == owner for job in self._jobs.values())
            if owned >= self._max_outstanding_jobs_per_owner:
                raise JobCapacityError(
                    "too many outstanding synthesis jobs for this subject"
                )

            # Admission executes after the in-memory concurrency check but
            # before a task is created. A durable quota reservation can be
            # made here without charging requests rejected for local capacity.
            if admit is not None:
                admit()

            job_id = self._new_job_id_locked()
            record = _JobRecord(job_id=job_id, owner=owner)
            self._jobs[job_id] = record
            record.task = asyncio.create_task(
                self._run(job_id, text, rate),
                name=f"synthesis-job-{job_id}",
            )
            return job_id

    async def get(
        self,
        job_id: str,
        *,
        owner: str | None = None,
        consume_terminal: bool = False,
    ) -> JobView | None:
        async with self._lock:
            self._prune_terminal_locked()
            record = self._jobs.get(job_id)
            if (
                record is None
                or record.delivered
                or (owner is not None and record.owner != owner)
            ):
                return None
            view = JobView(
                job_id=record.job_id,
                status=record.status,
                result=record.result,
                error=record.error,
            )
            if consume_terminal and record.status != "pending":
                # A terminal result is a one-shot delivery. Keep only a small
                # tombstone so the extension's follow-up DELETE can succeed;
                # repeated GET cannot amplify large WAV egress or retained RAM.
                record.delivered = True
                record.result = None
                record.error = None
                record.retained_bytes = 0
            return view

    async def delete(self, job_id: str, *, owner: str | None = None) -> bool:
        async with self._lock:
            self._prune_terminal_locked()
            record = self._jobs.get(job_id)
            if record is None or (owner is not None and record.owner != owner):
                return False
            del self._jobs[job_id]
        if record.task is not None and not record.task.done():
            record.task.cancel()
            await asyncio.gather(record.task, return_exceptions=True)
        return True

    async def shutdown(self) -> None:
        async with self._lock:
            self._closed = True
            records = tuple(self._jobs.values())
            self._jobs.clear()
        tasks = [
            record.task
            for record in records
            if record.task is not None and not record.task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, job_id: str, text: str, rate: float) -> None:
        try:
            result = await self._service.synthesize(text, rate)
        except asyncio.CancelledError:
            raise
        except ProviderError as exc:
            await self._finish(job_id, status="failed", error=str(exc))
        except Exception:
            await self._finish(
                job_id,
                status="failed",
                error=UNEXPECTED_JOB_ERROR,
            )
        else:
            await self._finish(job_id, status="completed", result=result)

    async def _finish(
        self,
        job_id: str,
        *,
        status: Literal["completed", "failed"],
        result: SynthesizeResponse | None = None,
        error: str | None = None,
    ) -> None:
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            if result is not None:
                result_bytes = self._retained_result_bytes(result)
                owner_bytes = sum(
                    job.retained_bytes
                    for job in self._jobs.values()
                    if job.owner == record.owner
                )
                global_bytes = sum(
                    job.retained_bytes for job in self._jobs.values()
                )
                if (
                    result_bytes > self._max_terminal_bytes_per_owner
                    or result_bytes > self._max_terminal_bytes
                    or owner_bytes + result_bytes
                    > self._max_terminal_bytes_per_owner
                    or global_bytes + result_bytes > self._max_terminal_bytes
                ):
                    status = "failed"
                    result = None
                    error = DELIVERY_CAPACITY_ERROR
                    result_bytes = 0
                record.retained_bytes = result_bytes
            record.status = status
            record.result = result
            record.error = error
            record.terminal_at = self._clock()
            # Do not let a terminal record retain a completed Task/coroutine
            # longer than the source text is needed for synthesis.
            record.task = None

    @staticmethod
    def _retained_result_bytes(result: SynthesizeResponse) -> int:
        return (
            len(result.audio_base64.encode("ascii"))
            + len(result.taigi_text.encode("utf-8"))
            + len(result.provider.encode("utf-8"))
            + len(result.mime_type)
        )

    def _new_job_id_locked(self) -> str:
        while True:
            candidate = str(self._uuid_factory())
            if candidate not in self._jobs:
                return candidate

    def _prune_terminal_locked(self) -> None:
        cutoff = self._clock() - self._terminal_ttl_seconds
        expired = [
            job_id
            for job_id, record in self._jobs.items()
            if record.terminal_at is not None and record.terminal_at <= cutoff
        ]
        for job_id in expired:
            del self._jobs[job_id]
