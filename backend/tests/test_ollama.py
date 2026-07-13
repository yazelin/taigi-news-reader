from __future__ import annotations

import httpx
import pytest

from taigi_news_reader_backend.providers import OllamaTranslator, ProviderError


async def test_ollama_posts_non_streaming_elder_friendly_translation_prompt():
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.read() and __import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={"response": "<think>draft</think>\n```text\nKin-á-ji̍t thinn-khì tsin hó\n```"},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )
    translator = OllamaTranslator(
        base_url="http://unused",
        model="qwen-test",
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    result = await translator.translate("今天天氣很好。")

    assert result == "kin-á-ji̍t thinn-khì tsin hó"
    assert seen["model"] == "qwen-test"
    assert seen["stream"] is False
    assert seen["options"] == {"temperature": 0.1}
    assert "elderly" in seen["system"]
    assert "今天天氣很好。" in seen["prompt"]
    await client.aclose()


async def test_ollama_repairs_chinese_output_once_then_accepts_valid_poj():
    outputs = iter(["這是中文新聞。", "tsit-ê sī tâi-gí sin-bûn"])
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(__import__("json").loads(request.content))
        return httpx.Response(200, json={"response": next(outputs)})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )
    translator = OllamaTranslator(
        base_url="http://unused",
        model="qwen-test",
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    result = await translator.translate("這是新聞。")

    assert result == "tsit-ê sī tâi-gí sin-bûn"
    assert len(payloads) == 2
    assert "exact character whitelist" in payloads[0]["system"]
    assert "Repair" in payloads[1]["system"]
    assert "這是中文新聞。" in payloads[1]["prompt"]
    await client.aclose()


@pytest.mark.parametrize("invalid", ["這是中文", "sin-bun 2026", "bad"])
async def test_ollama_fails_after_one_repair_for_unsupported_characters(invalid):
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"response": invalid})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )
    translator = OllamaTranslator(
        base_url="http://unused",
        model="qwen-test",
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    with pytest.raises(ProviderError, match="after one repair attempt"):
        await translator.translate("新聞")
    assert calls == 2
    await client.aclose()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, text="offline"),
        httpx.Response(200, json={"done": True}),
        httpx.Response(200, json={"response": "  "}),
    ],
)
async def test_ollama_fails_loudly_on_bad_upstream_response(response):
    async def handler(request: httpx.Request) -> httpx.Response:
        return response

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )
    translator = OllamaTranslator(
        base_url="http://unused",
        model="qwen-test",
        timeout_seconds=1,
        max_output_chars=500,
        client=client,
    )

    with pytest.raises(ProviderError):
        await translator.translate("新聞")
    await client.aclose()
