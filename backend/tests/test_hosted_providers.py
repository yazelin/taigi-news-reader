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
    await client.aclose()


@pytest.mark.parametrize("invalid", ["這是中文", "sin-bun 2026", "bad"])
async def test_openai_compatible_translation_rejects_non_mms_characters(invalid):
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

    with pytest.raises(ProviderError, match="incompatible"):
        await provider.translate("新聞")
    assert calls == 1
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
