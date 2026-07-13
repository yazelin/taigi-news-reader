from __future__ import annotations

import base64
import io
import wave

import httpx
import pytest

from taigi_news_reader_backend.app import create_app
from taigi_news_reader_backend.config import Settings
from taigi_news_reader_backend.providers import AudioResult, ProviderError
from taigi_news_reader_backend.service import SynthesisService


async def make_request(app, method: str, url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, url, **kwargs)


@pytest.fixture
def mock_app():
    return create_app(Settings(provider_mode="mock"))


async def test_health_reports_explicit_mock_providers_without_loading_models(mock_app):
    response = await make_request(mock_app, "GET", "/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "mock",
        "translator": "mock:taigi-translator",
        "synthesizer": "mock:wav-synthesizer",
    }


async def test_health_identifies_first_class_gemini_translator():
    app = create_app(
        Settings(
            translator_provider="gemini",
            gemini_api_key="test-key",
        )
    )

    response = await make_request(app, "GET", "/health")

    assert response.status_code == 200
    assert response.json()["translator"] == "gemini:gemini-3.5-flash"
    await app.state.synthesis_service.aclose()


async def test_synthesize_returns_taigi_and_valid_base64_wav(mock_app, request_body):
    response = await make_request(mock_app, "POST", "/v1/synthesize", json=request_body)

    assert response.status_code == 200
    body = response.json()
    assert body["taigi_text"] == "Tsit-ê sī tshik-thìng iōng ê Tâi-gí sin-bûn."
    assert body["mime_type"] == "audio/wav"
    assert body["provider"] == (
        "mock:taigi-translator+mock:wav-synthesizer"
    )
    audio = base64.b64decode(body["audio_base64"], validate=True)
    with wave.open(io.BytesIO(audio), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16_000
        assert wav.getnframes() > 0


@pytest.mark.parametrize(
    ("replacement", "field"),
    [
        ({"text": "   "}, "text"),
        ({"source_language": "en-US"}, "source_language"),
        ({"target_language": "zh-TW"}, "target_language"),
        ({"rate": 0.49}, "rate"),
        ({"rate": 1.51}, "rate"),
        ({"surprise": True}, "surprise"),
    ],
)
async def test_synthesize_rejects_invalid_contract(
    mock_app, request_body, replacement, field
):
    request_body.update(replacement)
    response = await make_request(mock_app, "POST", "/v1/synthesize", json=request_body)

    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])


async def test_synthesize_enforces_runtime_text_limit(request_body):
    app = create_app(Settings(provider_mode="mock", max_text_chars=5))
    request_body["text"] = "123456"

    response = await make_request(app, "POST", "/v1/synthesize", json=request_body)

    assert response.status_code == 413


async def test_direct_synthesis_can_be_explicitly_disabled(request_body):
    app = create_app(
        Settings(provider_mode="mock", allow_direct_synthesis=False)
    )

    response = await make_request(
        app,
        "POST",
        "/v1/synthesize",
        json=request_body,
    )

    assert response.status_code == 404


async def test_cors_allows_chrome_extension_and_localhost(mock_app):
    headers = {
        "Origin": f"chrome-extension://{'a' * 32}",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    chrome = await make_request(mock_app, "OPTIONS", "/v1/synthesize", headers=headers)
    local = await make_request(
        mock_app,
        "OPTIONS",
        "/v1/synthesize",
        headers={**headers, "Origin": "http://localhost:5173"},
    )
    evil = await make_request(
        mock_app,
        "OPTIONS",
        "/v1/synthesize",
        headers={**headers, "Origin": "https://evil.example"},
    )

    assert chrome.status_code == 200
    assert chrome.headers["access-control-allow-origin"] == headers["Origin"]
    assert local.status_code == 200
    assert evil.status_code == 400
    assert "access-control-allow-origin" not in evil.headers


async def test_cors_allows_extension_to_delete_synthesis_jobs(mock_app):
    origin = f"chrome-extension://{'a' * 32}"
    response = await make_request(
        mock_app,
        "OPTIONS",
        f"/v1/synthesis-jobs/{'1' * 36}",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "DELETE",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "DELETE" in response.headers["access-control-allow-methods"]


async def test_cors_can_pin_one_extension_id(request_body):
    allowed_id = "a" * 32
    app = create_app(
        Settings(
            provider_mode="mock",
            extension_ids=(allowed_id,),
            allow_localhost_origins=False,
        )
    )

    allowed = await make_request(
        app,
        "POST",
        "/v1/synthesize",
        json=request_body,
        headers={"Origin": f"chrome-extension://{allowed_id}"},
    )
    denied = await make_request(
        app,
        "POST",
        "/v1/synthesize",
        json=request_body,
        headers={"Origin": f"chrome-extension://{'b' * 32}"},
    )

    assert allowed.headers["access-control-allow-origin"].endswith(allowed_id)
    assert "access-control-allow-origin" not in denied.headers


async def test_strict_mode_requires_pinned_extension_header(request_body):
    allowed_id = "a" * 32
    app = create_app(
        Settings(
            provider_mode="mock",
            extension_ids=(allowed_id,),
            allow_localhost_origins=False,
            require_allowed_origin=True,
        )
    )

    missing = await make_request(
        app,
        "POST",
        "/v1/synthesize",
        json=request_body,
        headers={"Origin": f"chrome-extension://{allowed_id}"},
    )
    wrong = await make_request(
        app,
        "POST",
        "/v1/synthesize",
        json=request_body,
        headers={"X-Taigi-Extension-Id": "b" * 32},
    )
    allowed = await make_request(
        app,
        "POST",
        "/v1/synthesize",
        json=request_body,
        headers={"X-Taigi-Extension-Id": allowed_id},
    )
    health = await make_request(app, "GET", "/health")

    assert missing.status_code == 403
    assert missing.json() == {
        "detail": "request extension identity is not allowed"
    }
    assert wrong.status_code == 403
    assert allowed.status_code == 200
    assert health.status_code == 200


async def test_strict_mode_allows_header_only_job_poll(request_body):
    allowed_id = "a" * 32
    identity = {"X-Taigi-Extension-Id": allowed_id}
    app = create_app(
        Settings(
            provider_mode="mock",
            extension_ids=(allowed_id,),
            allow_localhost_origins=False,
            require_allowed_origin=True,
        )
    )

    created = await make_request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        json=request_body,
        headers={
            **identity,
            "Origin": f"chrome-extension://{allowed_id}",
        },
    )
    assert created.status_code == 202

    polled = await make_request(
        app,
        "GET",
        f"/v1/synthesis-jobs/{created.json()['job_id']}",
        headers=identity,
    )

    assert polled.status_code == 200


async def test_strict_mode_rejects_origin_mismatch_even_with_allowed_header(
    request_body,
):
    allowed_ids = ("a" * 32, "b" * 32)
    app = create_app(
        Settings(
            provider_mode="mock",
            extension_ids=allowed_ids,
            allow_localhost_origins=False,
            require_allowed_origin=True,
        )
    )

    response = await make_request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        json=request_body,
        headers={
            "X-Taigi-Extension-Id": allowed_ids[0],
            "Origin": f"chrome-extension://{allowed_ids[1]}",
        },
    )

    assert response.status_code == 403


async def test_strict_mode_allows_pinned_preflight():
    allowed_id = "a" * 32
    app = create_app(
        Settings(
            provider_mode="mock",
            extension_ids=(allowed_id,),
            allow_localhost_origins=False,
            require_allowed_origin=True,
        )
    )

    response = await make_request(
        app,
        "OPTIONS",
        "/v1/synthesis-jobs",
        headers={
            "Origin": f"chrome-extension://{allowed_id}",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "content-type,x-taigi-extension-id"
            ),
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"].endswith(allowed_id)
    assert "x-taigi-extension-id" in response.headers[
        "access-control-allow-headers"
    ].lower()


class FailingTranslator:
    name = "failing"

    async def translate(self, text: str) -> str:
        raise ProviderError("upstream unavailable")

    async def aclose(self) -> None:
        return None


class UnusedSynthesizer:
    name = "unused"

    async def synthesize(self, text: str, rate: float) -> AudioResult:
        raise AssertionError("TTS should not run after translation failure")

    async def aclose(self) -> None:
        return None


async def test_provider_failure_is_loud_and_does_not_fallback(request_body):
    service = SynthesisService(FailingTranslator(), UnusedSynthesizer())
    app = create_app(Settings(provider_mode="mock"), service)

    response = await make_request(app, "POST", "/v1/synthesize", json=request_body)

    assert response.status_code == 502
    assert response.json() == {"detail": "upstream unavailable"}
