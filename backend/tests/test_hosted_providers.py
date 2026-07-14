from __future__ import annotations

import base64
import json

import httpx
import pytest

from taigi_news_reader_backend.providers import (
    OpenAICompatibleTranslator,
    ProviderError,
    RemoteTtsSynthesizer,
)
from taigi_news_reader_backend.providers.mms import float_waveform_to_wav
from taigi_news_reader_backend.providers.ollama import SYSTEM_PROMPT


async def test_openai_compatible_translator_uses_chat_completions_contract():
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Sin-bûn lâi--ah"}}]},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.test/v1",
        headers={"Authorization": "Bearer secret"},
    )
    provider = OpenAICompatibleTranslator(
        base_url="https://unused",
        api_key="unused",
        model="translator-model",
        timeout_seconds=1,
        max_output_chars=100,
        client=client,
    )

    result = await provider.translate("新聞來了。")

    assert result == "sin-bûn lâi--ah"
    assert seen["path"] == "/v1/chat/completions"
    assert seen["authorization"] == "Bearer secret"
    assert seen["body"]["model"] == "translator-model"
    assert set(seen["body"]) == {"model", "messages", "temperature"}
    await client.aclose()


@pytest.mark.parametrize(
    "model", ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
)
async def test_groq_gpt_oss_gets_model_specific_reasoning_budget(model):
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "tâi-gí sin-bûn"},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.groq.com/openai/v1/",
    )
    provider = OpenAICompatibleTranslator(
        base_url="https://unused",
        api_key="secret",
        model=model,
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    assert await provider.translate("新聞") == "tâi-gí sin-bûn"
    assert payloads == [
        {
            "model": model,
            "messages": payloads[0]["messages"],
            "temperature": 0.1,
            "reasoning_effort": "low",
            "include_reasoning": False,
            "max_completion_tokens": 8_192,
        }
    ]
    await client.aclose()


async def test_openai_compatible_retries_first_empty_content_then_succeeds():
    responses = iter(
        [
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": "",
                            # Reasoning is not translation and must be ignored.
                            "reasoning": "tâi-gí m̄-sī tsit-ê",
                        },
                    }
                ]
            },
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "tâi-gí sin-bûn"},
                    }
                ]
            },
        ]
    )
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json=next(responses))

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.groq.com/openai/v1/",
    )
    provider = OpenAICompatibleTranslator(
        base_url="https://unused",
        api_key="secret",
        model="openai/gpt-oss-120b",
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    assert await provider.translate("新聞") == "tâi-gí sin-bûn"
    assert len(payloads) == 2
    assert payloads[0] == payloads[1]
    await client.aclose()


async def test_openai_compatible_two_empty_contents_fail_after_one_retry():
    responses = iter(
        [
            {
                "choices": [
                    {"finish_reason": "length", "message": {"content": ""}}
                ]
            },
            {
                "choices": [
                    {"finish_reason": "stop", "message": {"content": "   "}}
                ]
            },
        ]
    )
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=next(responses))

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.test/v1/",
    )
    provider = OpenAICompatibleTranslator(
        base_url="https://unused",
        api_key="secret",
        model="translator-model",
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    with pytest.raises(ProviderError) as captured:
        await provider.translate("新聞")

    assert calls == 2
    assert "empty translation twice after one retry" in str(captured.value)
    assert "first=length" in str(captured.value)
    assert "retry=stop" in str(captured.value)
    await client.aclose()


async def test_openai_compatible_normalizes_groq_punctuation_and_superscript_n():
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "tâi-gí,\nthiⁿ-khì。"}}
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.test/v1/",
    )
    provider = OpenAICompatibleTranslator(
        base_url="https://unused",
        api_key="secret",
        model="translator-model",
        timeout_seconds=1,
        max_output_chars=100,
        client=client,
    )

    result = await provider.translate("新聞")

    assert result == "tâi-gí thinn-khì"
    assert len(payloads) == 1
    assert payloads[0]["messages"][0]["content"] == SYSTEM_PROMPT
    await client.aclose()


async def test_openai_compatible_normalizes_newline_without_repair():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "tâi-gí\n  sin-bûn"}}]},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.test/v1/",
    )
    provider = OpenAICompatibleTranslator(
        base_url="https://unused",
        api_key="secret",
        model="translator-model",
        timeout_seconds=1,
        max_output_chars=100,
        client=client,
    )

    assert await provider.translate("新聞") == "tâi-gí sin-bûn"
    assert calls == 1
    await client.aclose()


@pytest.mark.parametrize(
    ("output_length", "exceeds_limit"),
    [(2_000, False), (2_001, True)],
)
async def test_openai_compatible_enforces_exact_output_character_boundary(
    output_length, exceeds_limit
):
    translation = "a" * output_length

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": translation}}]},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.test/v1/",
    )
    provider = OpenAICompatibleTranslator(
        base_url="https://unused",
        api_key="secret",
        model="translator-model",
        timeout_seconds=1,
        max_output_chars=2_000,
        client=client,
    )

    if exceeds_limit:
        with pytest.raises(ProviderError, match="exceeded the output limit"):
            await provider.translate("新聞")
    else:
        assert await provider.translate("新聞") == translation
    await client.aclose()


@pytest.mark.parametrize(
    "invalid", ["這是中文", "sin-bun 2026", "bad", "tâi-gír"]
)
async def test_openai_compatible_fails_after_one_invalid_repair(invalid):
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": invalid}}]},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://provider.test/v1/",
    )
    provider = OpenAICompatibleTranslator(
        base_url="https://unused",
        api_key="secret",
        model="translator-model",
        timeout_seconds=1,
        max_output_chars=100,
        client=client,
    )

    with pytest.raises(ProviderError, match="after one repair attempt"):
        await provider.translate("新聞")
    assert calls == 2
    await client.aclose()


async def test_remote_tts_contract_and_wav_validation():
    wav = float_waveform_to_wav([0.0, 0.25, -0.25], 16_000)
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "audio_base64": base64.b64encode(wav).decode("ascii"),
                "mime_type": "audio/wav",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = RemoteTtsSynthesizer(
        url="https://tts.test/synthesize",
        api_key=None,
        timeout_seconds=1,
        max_audio_bytes=1_000,
        client=client,
    )

    result = await provider.synthesize("Sin-bûn", 0.8)

    assert result.audio == wav
    assert seen == {"text": "Sin-bûn", "language": "nan-TW", "rate": 0.8}
    await client.aclose()


@pytest.mark.parametrize(
    "body",
    [
        {"audio_base64": "not-base64", "mime_type": "audio/wav"},
        {"audio_base64": base64.b64encode(b"Mandarin MP3").decode(), "mime_type": "audio/mpeg"},
        {"audio_base64": base64.b64encode(b"not a wave").decode(), "mime_type": "audio/wav"},
    ],
)
async def test_remote_tts_rejects_untrusted_audio_response(body):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = RemoteTtsSynthesizer(
        url="https://tts.test/synthesize",
        api_key=None,
        timeout_seconds=1,
        max_audio_bytes=1_000,
        client=client,
    )

    with pytest.raises(ProviderError):
        await provider.synthesize("Sin-bûn", 1.0)
    await client.aclose()
