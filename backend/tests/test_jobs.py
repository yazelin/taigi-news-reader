from __future__ import annotations

import asyncio
import base64
import io
import uuid
import wave

import httpx

from taigi_news_reader_backend.app import create_app
from taigi_news_reader_backend.config import Settings
from taigi_news_reader_backend.jobs import JobManager, UNEXPECTED_JOB_ERROR
from taigi_news_reader_backend.models import SynthesizeResponse
from taigi_news_reader_backend.providers import ProviderError
from taigi_news_reader_backend.providers.mms import float_waveform_to_wav


REQUEST = {
    "text": "今天天氣晴朗。",
    "source_language": "zh-TW",
    "target_language": "nan-TW",
    "rate": 1.0,
}


async def request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


async def wait_for_status(app, job_id: str, status: str) -> httpx.Response:
    for _ in range(100):
        response = await request(app, "GET", f"/v1/synthesis-jobs/{job_id}")
        if response.status_code == 200 and response.json()["status"] == status:
            return response
        await asyncio.sleep(0)
    raise AssertionError(f"job {job_id} never reached {status}")


def wav_result() -> SynthesizeResponse:
    wav = float_waveform_to_wav([0.0, 0.25, -0.25], 16_000)
    return SynthesizeResponse(
        taigi_text="tâi-gí sin-bûn",
        audio_base64=base64.b64encode(wav).decode("ascii"),
        mime_type="audio/wav",
        provider="test:translator+test:tts",
    )


class DeferredService:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.future = asyncio.get_running_loop().create_future()
        self.closed = False

    async def synthesize(self, text: str, rate: float) -> SynthesizeResponse:
        self.started.set()
        try:
            return await self.future
        except asyncio.CancelledError:
            self.cancelled.set()
            raise

    async def aclose(self) -> None:
        self.closed = True


class ImmediateService:
    def __init__(self, outcome: SynthesizeResponse | Exception) -> None:
        self.outcome = outcome
        self.closed = False

    async def synthesize(self, text: str, rate: float) -> SynthesizeResponse:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def aclose(self) -> None:
        self.closed = True


async def test_create_returns_202_pending_immediately_for_deferred_service():
    service = DeferredService()
    manager = JobManager(service)
    app = create_app(Settings(provider_mode="mock"), service, manager)

    response = await asyncio.wait_for(
        request(app, "POST", "/v1/synthesis-jobs", json=REQUEST),
        timeout=1,
    )

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    parsed_id = uuid.UUID(response.json()["job_id"])
    assert parsed_id.version == 4
    await asyncio.wait_for(service.started.wait(), timeout=1)
    pending = await request(
        app,
        "GET",
        f"/v1/synthesis-jobs/{parsed_id}",
    )
    assert pending.json() == {"job_id": str(parsed_id), "status": "pending"}
    await manager.shutdown()


async def test_job_transitions_pending_to_completed_with_wav_result():
    service = DeferredService()
    manager = JobManager(service)
    app = create_app(Settings(provider_mode="mock"), service, manager)
    created = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    job_id = created.json()["job_id"]
    await asyncio.wait_for(service.started.wait(), timeout=1)
    assert (await request(app, "GET", f"/v1/synthesis-jobs/{job_id}")).json()[
        "status"
    ] == "pending"

    service.future.set_result(wav_result())
    completed = await wait_for_status(app, job_id, "completed")

    body = completed.json()
    assert body["job_id"] == job_id
    assert body["result"]["taigi_text"] == "tâi-gí sin-bûn"
    assert body["result"]["mime_type"] == "audio/wav"
    audio = base64.b64decode(body["result"]["audio_base64"], validate=True)
    with wave.open(io.BytesIO(audio), "rb") as wav:
        assert wav.getframerate() == 16_000
        assert wav.getnframes() == 3
    record = manager._jobs[job_id]
    assert record.task is None
    assert not hasattr(record, "text")
    assert (
        await request(app, "DELETE", f"/v1/synthesis-jobs/{job_id}")
    ).status_code == 204
    assert (
        await request(app, "GET", f"/v1/synthesis-jobs/{job_id}")
    ).status_code == 404
    await manager.shutdown()


async def test_provider_failure_retains_only_existing_safe_message():
    service = ImmediateService(ProviderError("Gemini translation request failed"))
    manager = JobManager(service)
    app = create_app(Settings(provider_mode="mock"), service, manager)

    created = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    failed = await wait_for_status(app, created.json()["job_id"], "failed")

    assert failed.json()["error"] == "Gemini translation request failed"
    await manager.shutdown()


async def test_unexpected_failure_is_generic_and_does_not_store_exception_detail():
    service = ImmediateService(RuntimeError("api-key=secret-marker"))
    manager = JobManager(service)
    app = create_app(Settings(provider_mode="mock"), service, manager)

    created = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    failed = await wait_for_status(app, created.json()["job_id"], "failed")

    assert failed.json()["error"] == UNEXPECTED_JOB_ERROR
    assert "secret-marker" not in failed.text
    await manager.shutdown()


async def test_unknown_job_get_and_delete_return_404():
    service = ImmediateService(wav_result())
    manager = JobManager(service)
    app = create_app(Settings(provider_mode="mock"), service, manager)
    unknown = str(uuid.uuid4())

    get_response = await request(app, "GET", f"/v1/synthesis-jobs/{unknown}")
    delete_response = await request(
        app,
        "DELETE",
        f"/v1/synthesis-jobs/{unknown}",
    )

    assert get_response.status_code == 404
    assert get_response.json() == {"detail": "synthesis job not found"}
    assert delete_response.status_code == 404
    await manager.shutdown()


async def test_delete_cancels_pending_job_and_clears_it():
    service = DeferredService()
    manager = JobManager(service)
    app = create_app(Settings(provider_mode="mock"), service, manager)
    created = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    job_id = created.json()["job_id"]
    await asyncio.wait_for(service.started.wait(), timeout=1)

    deleted = await request(app, "DELETE", f"/v1/synthesis-jobs/{job_id}")

    assert deleted.status_code == 204
    assert deleted.content == b""
    await asyncio.wait_for(service.cancelled.wait(), timeout=1)
    assert (
        await request(app, "GET", f"/v1/synthesis-jobs/{job_id}")
    ).status_code == 404


async def test_active_capacity_rejects_until_pending_job_is_deleted():
    service = DeferredService()
    manager = JobManager(service, max_active_jobs=1)
    app = create_app(Settings(provider_mode="mock"), service, manager)
    first = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    first_id = first.json()["job_id"]
    await asyncio.wait_for(service.started.wait(), timeout=1)

    full = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    assert full.status_code == 429
    assert full.json() == {"detail": "too many active synthesis jobs"}

    assert (
        await request(app, "DELETE", f"/v1/synthesis-jobs/{first_id}")
    ).status_code == 204
    replacement = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    assert replacement.status_code == 202
    await manager.shutdown()


async def test_terminal_job_is_opportunistically_pruned_after_monotonic_ttl():
    now = [100.0]
    service = ImmediateService(wav_result())
    manager = JobManager(
        service,
        terminal_ttl_seconds=600,
        clock=lambda: now[0],
    )
    app = create_app(Settings(provider_mode="mock"), service, manager)
    created = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    job_id = created.json()["job_id"]
    await wait_for_status(app, job_id, "completed")

    now[0] = 699.9
    assert (
        await request(app, "GET", f"/v1/synthesis-jobs/{job_id}")
    ).status_code == 200
    now[0] = 700.0
    assert (
        await request(app, "GET", f"/v1/synthesis-jobs/{job_id}")
    ).status_code == 404
    await manager.shutdown()


async def test_async_endpoint_enforces_same_runtime_text_limit_as_direct_endpoint():
    service = ImmediateService(wav_result())
    manager = JobManager(service)
    app = create_app(
        Settings(provider_mode="mock", max_text_chars=5),
        service,
        manager,
    )
    too_long = {**REQUEST, "text": "123456"}

    response = await request(app, "POST", "/v1/synthesis-jobs", json=too_long)

    assert response.status_code == 413
    assert await manager.get(str(uuid.uuid4())) is None
    await manager.shutdown()


async def test_lifespan_shutdown_cancels_jobs_before_closing_service():
    events: list[str] = []

    class ShutdownService(DeferredService):
        async def synthesize(self, text: str, rate: float) -> SynthesizeResponse:
            events.append("started")
            try:
                return await super().synthesize(text, rate)
            except asyncio.CancelledError:
                events.append("cancelled")
                raise

        async def aclose(self) -> None:
            events.append("closed")
            await super().aclose()

    service = ShutdownService()
    manager = JobManager(service)
    app = create_app(Settings(provider_mode="mock"), service, manager)

    async with app.router.lifespan_context(app):
        created = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
        job_id = created.json()["job_id"]
        await asyncio.wait_for(service.started.wait(), timeout=1)

    assert events == ["started", "cancelled", "closed"]
    assert service.closed is True
    assert await manager.get(job_id) is None
