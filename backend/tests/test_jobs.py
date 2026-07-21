from __future__ import annotations

import asyncio
import base64
import io
import uuid
import wave

import httpx
import pytest

from taigi_news_reader_backend.app import create_app
from taigi_news_reader_backend.config import Settings
from taigi_news_reader_backend.jobs import (
    DELIVERY_CAPACITY_ERROR,
    JobCapacityError,
    JobManager,
    UNEXPECTED_JOB_ERROR,
)
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


async def slow_asgi_get(
    app,
    path: str,
    body_started: asyncio.Event,
    allow_finish: asyncio.Event,
    messages: list[dict],
    send_failure: Exception | None = None,
) -> None:
    request_delivered = False
    wait_forever = asyncio.Event()

    async def receive():
        nonlocal request_delivered
        if not request_delivered:
            request_delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await wait_forever.wait()

    async def send(message):
        messages.append(message)
        if (
            message["type"] == "http.response.body"
            and not message.get("more_body", False)
        ):
            body_started.set()
            if send_failure is not None:
                raise send_failure
            await allow_finish.wait()

    path_bytes = path.encode("ascii")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path_bytes,
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test")],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    await app(scope, receive, send)


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
        spoken_text="tâi-gí sin-bûn",
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


async def test_async_job_preserves_direct_romanization_input_mode():
    app = create_app(Settings(provider_mode="mock"))
    direct_request = {
        **REQUEST,
        "text": "Guá beh kóng Tâi-gí.",
        "source_language": "nan-Latn-TW",
    }

    created = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        json=direct_request,
    )
    completed = await wait_for_status(
        app,
        created.json()["job_id"],
        "completed",
    )

    assert completed.json()["result"]["taigi_text"] == direct_request["text"]
    assert completed.json()["result"]["provider"] == (
        "direct:nan-Latn-TW+mock:wav-synthesizer"
    )
    await app.state.job_manager.shutdown()


async def test_async_job_dispatches_mandarin_backup_without_taigi_label():
    app = create_app(
        Settings(provider_mode="mock", mandarin_tts_provider="edge")
    )
    mandarin_request = {
        **REQUEST,
        "text": "今天天氣真好。",
        "target_language": "zh-TW",
    }

    created = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        json=mandarin_request,
    )
    completed = await wait_for_status(
        app,
        created.json()["job_id"],
        "completed",
    )

    result = completed.json()["result"]
    assert result["spoken_text"] == mandarin_request["text"]
    assert result["taigi_text"] is None
    assert result["provider"] == (
        "direct:zh-TW+mock:online-mandarin-backup"
    )
    await app.state.job_manager.shutdown()


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


async def test_delete_hides_pending_job_until_provider_actually_finishes():
    service = DeferredService()
    manager = JobManager(service)
    app = create_app(Settings(provider_mode="mock"), service, manager)
    created = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    job_id = created.json()["job_id"]
    await asyncio.wait_for(service.started.wait(), timeout=1)

    deleted = await request(app, "DELETE", f"/v1/synthesis-jobs/{job_id}")

    assert deleted.status_code == 204
    assert deleted.content == b""
    assert (
        await request(app, "GET", f"/v1/synthesis-jobs/{job_id}")
    ).status_code == 404
    assert (
        await request(app, "DELETE", f"/v1/synthesis-jobs/{job_id}")
    ).status_code == 204
    assert service.cancelled.is_set() is False
    assert manager._jobs[job_id].status == "pending"
    assert manager._jobs[job_id].discarded is True

    service.future.set_result(wav_result())
    for _ in range(100):
        if manager._jobs[job_id].status != "pending":
            break
        await asyncio.sleep(0)
    assert manager._jobs[job_id].discarded is True
    assert manager._jobs[job_id].result is None
    assert (
        await request(app, "DELETE", f"/v1/synthesis-jobs/{job_id}")
    ).status_code == 204
    await manager.shutdown()


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
    assert full.headers["retry-after"] == "5"
    assert full.headers["x-ratelimit-scope"] == "active_jobs"

    assert (
        await request(app, "DELETE", f"/v1/synthesis-jobs/{first_id}")
    ).status_code == 204
    still_full = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    assert still_full.status_code == 429

    service.future.set_result(wav_result())
    for _ in range(100):
        if manager._jobs[first_id].status != "pending":
            break
        await asyncio.sleep(0)
    replacement = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        json=REQUEST,
    )
    assert replacement.status_code == 202
    await manager.shutdown()


async def test_capacity_rejection_happens_before_durable_admission_callback():
    service = DeferredService()
    manager = JobManager(service, max_active_jobs=1)
    first_id = await manager.create(REQUEST["text"], 1.0, owner="tester-a")
    await asyncio.wait_for(service.started.wait(), timeout=1)
    admissions: list[str] = []

    with pytest.raises(JobCapacityError, match="active"):
        await manager.create(
            REQUEST["text"],
            1.0,
            owner="tester-b",
            admit=lambda: admissions.append("charged"),
        )

    assert admissions == []
    await manager.delete(first_id)
    service.future.set_result(wav_result())
    for _ in range(100):
        if manager._jobs[first_id].status != "pending":
            break
        await asyncio.sleep(0)
    await manager.shutdown()


async def test_pending_delete_is_idempotent_for_owner_but_hidden_cross_owner():
    service = DeferredService()
    manager = JobManager(service)
    job_id = await manager.create(REQUEST["text"], 1.0, owner="tester-a")
    await asyncio.wait_for(service.started.wait(), timeout=1)

    assert await manager.delete(job_id, owner="tester-b") is False
    assert await manager.delete(job_id, owner="tester-a") is True
    assert await manager.delete(job_id, owner="tester-a") is True
    assert await manager.delete(job_id, owner="tester-b") is False
    assert await manager.get(job_id, owner="tester-a") is None

    service.future.set_result(wav_result())
    for _ in range(100):
        if manager._jobs[job_id].status != "pending":
            break
        await asyncio.sleep(0)
    assert await manager.delete(job_id, owner="tester-a") is True
    assert await manager.delete(job_id, owner="tester-b") is False
    await manager.shutdown()


async def test_outstanding_job_caps_bound_terminal_records_per_owner_and_global():
    service = ImmediateService(wav_result())
    manager = JobManager(
        service,
        max_active_jobs=2,
        max_outstanding_jobs=2,
        max_outstanding_jobs_per_owner=1,
    )
    first_id = await manager.create(REQUEST["text"], 1.0, owner="tester-a")
    for _ in range(100):
        first = await manager.get(first_id)
        if first is not None and first.status == "completed":
            break
        await asyncio.sleep(0)

    with pytest.raises(JobCapacityError, match="this subject"):
        await manager.create(REQUEST["text"], 1.0, owner="tester-a")
    second_id = await manager.create(REQUEST["text"], 1.0, owner="tester-b")
    with pytest.raises(JobCapacityError, match="outstanding"):
        await manager.create(REQUEST["text"], 1.0, owner="tester-c")

    await manager.delete(first_id)
    await manager.delete(second_id)


async def test_terminal_result_bytes_are_bounded_with_safe_failure():
    service = ImmediateService(wav_result())
    manager = JobManager(
        service,
        max_terminal_bytes=1,
        max_terminal_bytes_per_owner=1,
    )
    app = create_app(Settings(provider_mode="mock"), service, manager)
    created = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)

    failed = await wait_for_status(app, created.json()["job_id"], "failed")

    assert failed.json()["error"] == DELIVERY_CAPACITY_ERROR
    assert "audio_base64" not in failed.text


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
    for _ in range(100):
        view = await manager.get(job_id)
        if view is not None and view.status == "completed":
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("job never completed")

    now[0] = 699.9
    assert (await manager.get(job_id)) is not None
    now[0] = 700.0
    assert (await manager.get(job_id)) is None
    await manager.shutdown()


async def test_terminal_http_result_is_delivered_only_once_then_delete_succeeds():
    service = ImmediateService(wav_result())
    manager = JobManager(service)
    app = create_app(Settings(provider_mode="mock"), service, manager)
    created = await request(app, "POST", "/v1/synthesis-jobs", json=REQUEST)
    job_id = created.json()["job_id"]

    delivered = await wait_for_status(app, job_id, "completed")
    repeated = await request(app, "GET", f"/v1/synthesis-jobs/{job_id}")
    deleted = await request(app, "DELETE", f"/v1/synthesis-jobs/{job_id}")

    assert delivered.status_code == 200
    assert repeated.status_code == 404
    assert deleted.status_code == 204
    assert job_id not in manager._jobs


@pytest.mark.parametrize(
    ("second_owner", "global_multiplier"),
    [("tester-a", 2), ("tester-b", 1)],
)
async def test_inflight_delivery_lease_keeps_per_owner_and_global_bytes_charged(
    second_owner,
    global_multiplier,
):
    result = wav_result()
    result_bytes = JobManager._retained_result_bytes(result)
    service = ImmediateService(result)
    manager = JobManager(
        service,
        max_active_jobs=2,
        max_outstanding_jobs=4,
        max_outstanding_jobs_per_owner=3,
        max_terminal_bytes=result_bytes * global_multiplier,
        max_terminal_bytes_per_owner=result_bytes,
    )
    first_id = await manager.create(REQUEST["text"], 1.0, owner="tester-a")
    for _ in range(100):
        first = await manager.get(first_id, owner="tester-a")
        if first is not None and first.status == "completed":
            break
        await asyncio.sleep(0)
    claimed = await manager.get(
        first_id,
        owner="tester-a",
        consume_terminal=True,
    )
    assert claimed is not None and claimed.delivery_lease is not None
    assert manager._jobs[first_id].retained_bytes == result_bytes

    second_id = await manager.create(
        REQUEST["text"],
        1.0,
        owner=second_owner,
    )
    for _ in range(100):
        second = await manager.get(second_id, owner=second_owner)
        if second is not None and second.status == "failed":
            break
        await asyncio.sleep(0)

    assert second is not None
    assert second.status == "failed"
    assert second.error == DELIVERY_CAPACITY_ERROR
    assert manager._jobs[first_id].retained_bytes == result_bytes
    assert await manager.release_delivery(
        first_id,
        claimed.delivery_lease,
        owner="tester-a",
    )
    assert manager._jobs[first_id].retained_bytes == 0
    await manager.shutdown()


async def test_concurrent_delete_does_not_release_slow_response_lease_early():
    result = wav_result()
    service = ImmediateService(result)
    manager = JobManager(
        service,
        max_active_jobs=1,
        max_outstanding_jobs=1,
        max_outstanding_jobs_per_owner=1,
    )
    app = create_app(Settings(provider_mode="mock"), service, manager)
    job_id = await manager.create(
        REQUEST["text"],
        1.0,
        owner="local-open-access",
    )
    for _ in range(100):
        view = await manager.get(job_id, owner="local-open-access")
        if view is not None and view.status == "completed":
            break
        await asyncio.sleep(0)

    body_started = asyncio.Event()
    allow_finish = asyncio.Event()
    messages: list[dict] = []
    slow_response = asyncio.create_task(
        slow_asgi_get(
            app,
            f"/v1/synthesis-jobs/{job_id}",
            body_started,
            allow_finish,
            messages,
        )
    )
    await asyncio.wait_for(body_started.wait(), timeout=1)
    record = manager._jobs[job_id]
    retained_bytes = record.retained_bytes
    assert retained_bytes > 0
    assert record.delivery_lease is not None

    repeated_get = await request(
        app,
        "GET",
        f"/v1/synthesis-jobs/{job_id}",
    )
    deleted = await request(
        app,
        "DELETE",
        f"/v1/synthesis-jobs/{job_id}",
    )
    replacement_while_sending = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        json=REQUEST,
    )

    assert repeated_get.status_code == 404
    assert deleted.status_code == 204
    assert replacement_while_sending.status_code == 429
    assert job_id in manager._jobs
    assert manager._jobs[job_id].delete_requested is True
    assert manager._jobs[job_id].retained_bytes == retained_bytes

    allow_finish.set()
    await asyncio.wait_for(slow_response, timeout=1)
    assert any(
        message["type"] == "http.response.start"
        and message["status"] == 200
        for message in messages
    )
    assert job_id not in manager._jobs
    replacement_after_send = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        json=REQUEST,
    )
    assert replacement_after_send.status_code == 202
    await manager.shutdown()


async def test_abandoned_delivery_lease_is_pruned_after_bounded_ttl():
    now = [100.0]
    service = ImmediateService(wav_result())
    manager = JobManager(
        service,
        terminal_ttl_seconds=600,
        clock=lambda: now[0],
    )
    job_id = await manager.create(REQUEST["text"], 1.0, owner="tester-a")
    for _ in range(100):
        view = await manager.get(job_id, owner="tester-a")
        if view is not None and view.status == "completed":
            break
        await asyncio.sleep(0)
    claimed = await manager.get(
        job_id,
        owner="tester-a",
        consume_terminal=True,
    )
    assert claimed is not None and claimed.delivery_lease is not None

    now[0] = 699.9
    await manager.get("unknown")
    assert job_id in manager._jobs
    now[0] = 700.0
    await manager.get("unknown")
    assert job_id not in manager._jobs
    assert not await manager.release_delivery(
        job_id,
        claimed.delivery_lease,
        owner="tester-a",
    )
    await manager.shutdown()


async def test_transport_failure_still_releases_terminal_delivery_bytes():
    service = ImmediateService(wav_result())
    manager = JobManager(service)
    app = create_app(Settings(provider_mode="mock"), service, manager)
    job_id = await manager.create(
        REQUEST["text"],
        1.0,
        owner="local-open-access",
    )
    for _ in range(100):
        view = await manager.get(job_id, owner="local-open-access")
        if view is not None and view.status == "completed":
            break
        await asyncio.sleep(0)

    with pytest.raises(ConnectionError, match="client disconnected"):
        await slow_asgi_get(
            app,
            f"/v1/synthesis-jobs/{job_id}",
            asyncio.Event(),
            asyncio.Event(),
            [],
            send_failure=ConnectionError("client disconnected"),
        )

    assert manager._jobs[job_id].delivery_lease is None
    assert manager._jobs[job_id].retained_bytes == 0
    assert manager._jobs[job_id].delivered is True
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
