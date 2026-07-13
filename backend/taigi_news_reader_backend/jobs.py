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
    status: JobStatus = "pending"
    task: asyncio.Task[None] | None = None
    result: SynthesizeResponse | None = None
    error: str | None = None
    terminal_at: float | None = None


class JobManager:
    def __init__(
        self,
        service: SynthesisService,
        *,
        max_active_jobs: int = 4,
        terminal_ttl_seconds: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
        uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    ) -> None:
        if max_active_jobs < 1:
            raise ValueError("max_active_jobs must be positive")
        if terminal_ttl_seconds <= 0:
            raise ValueError("terminal_ttl_seconds must be positive")
        self._service = service
        self._max_active_jobs = max_active_jobs
        self._terminal_ttl_seconds = terminal_ttl_seconds
        self._clock = clock
        self._uuid_factory = uuid_factory
        self._jobs: dict[str, _JobRecord] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def create(self, text: str, rate: float) -> str:
        async with self._lock:
            self._prune_terminal_locked()
            if self._closed:
                raise RuntimeError("job manager is closed")
            active = sum(job.status == "pending" for job in self._jobs.values())
            if active >= self._max_active_jobs:
                raise JobCapacityError("too many active synthesis jobs")

            job_id = self._new_job_id_locked()
            record = _JobRecord(job_id=job_id)
            self._jobs[job_id] = record
            record.task = asyncio.create_task(
                self._run(job_id, text, rate),
                name=f"synthesis-job-{job_id}",
            )
            return job_id

    async def get(self, job_id: str) -> JobView | None:
        async with self._lock:
            self._prune_terminal_locked()
            record = self._jobs.get(job_id)
            if record is None:
                return None
            return JobView(
                job_id=record.job_id,
                status=record.status,
                result=record.result,
                error=record.error,
            )

    async def delete(self, job_id: str) -> bool:
        async with self._lock:
            self._prune_terminal_locked()
            record = self._jobs.pop(job_id, None)
        if record is None:
            return False
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
            record.status = status
            record.result = result
            record.error = error
            record.terminal_at = self._clock()
            # Do not let a terminal record retain a completed Task/coroutine
            # longer than the source text is needed for synthesis.
            record.task = None

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
