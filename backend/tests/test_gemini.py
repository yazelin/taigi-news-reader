from __future__ import annotations

import json

import httpx
import pytest

from taigi_news_reader_backend.app import create_app
from taigi_news_reader_backend.config import Settings
from taigi_news_reader_backend.providers import (
    GeminiTranslator,
    MockTtsSynthesizer,
    ProviderError,
)
from taigi_news_reader_backend.providers.ollama import SYSTEM_PROMPT
from taigi_news_reader_backend.service import SynthesisService


async def test_gemini_uses_official_openai_compatibility_contract():
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "Tâi-gí\n sin-bûn"},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        headers={"Authorization": "Bearer test-key"},
    )
    provider = GeminiTranslator(
        base_url="https://unused",
        api_key="unused",
        model="gemini-3.5-flash",
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    result = await provider.translate("新聞")

    assert result == "tâi-gí sin-bûn"
    assert provider.name == "gemini:gemini-3.5-flash"
    assert seen["path"] == "/v1beta/openai/chat/completions"
    assert seen["authorization"] == "Bearer test-key"
    assert seen["payload"]["model"] == "gemini-3.5-flash"
    assert set(seen["payload"]) == {"model", "messages", "temperature"}
    await client.aclose()


async def test_gemini_constructor_applies_bearer_key_and_timeout():
    provider = GeminiTranslator(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key="test-key",
        model="gemini-3.5-flash",
        timeout_seconds=17,
        max_output_chars=500,
    )

    assert provider._client.headers["authorization"] == "Bearer test-key"
    assert provider._client.timeout.connect == 17
    assert provider._client.timeout.read == 17
    assert provider._client.timeout.write == 17
    assert provider._client.timeout.pool == 17
    await provider.aclose()


async def test_gemini_upstream_failure_does_not_expose_key_in_api_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": "rejected test-secret-marker"},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        headers={"Authorization": "Bearer test-secret-marker"},
    )
    provider = GeminiTranslator(
        base_url="https://unused",
        api_key="unused",
        model="gemini-3.5-flash",
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    service = SynthesisService(provider, MockTtsSynthesizer())
    app = create_app(Settings(provider_mode="mock"), service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as api_client:
        response = await api_client.post(
            "/v1/synthesize",
            json={
                "text": "新聞",
                "source_language": "zh-TW",
                "target_language": "nan-TW",
                "rate": 1.0,
            },
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini translation request failed"}
    assert "test-secret-marker" not in response.text
    await client.aclose()


async def test_gemini_inherits_empty_retry_and_poj_format_normalization():
    responses = iter(["", "tâi-gí, thiⁿ-khì。"])
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": next(responses)},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    provider = GeminiTranslator(
        base_url="https://unused",
        api_key="test-key",
        model="gemini-3.5-flash",
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    assert await provider.translate("新聞") == "tâi-gí thinn-khì"
    assert len(payloads) == 2
    assert payloads[0]["messages"][0]["content"] == SYSTEM_PROMPT
    assert payloads[1] == payloads[0]
    await client.aclose()


async def test_gemini_errors_use_gemini_identity():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": ""},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    provider = GeminiTranslator(
        base_url="https://unused",
        api_key="test-key",
        model="gemini-3.5-flash",
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    with pytest.raises(ProviderError) as captured:
        await provider.translate("新聞")

    assert str(captured.value).startswith(
        "Gemini failed to return a complete translation after one retry"
    )
    assert "OpenAI-compatible" not in str(captured.value)
    await client.aclose()
