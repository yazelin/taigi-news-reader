from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from taigi_news_reader_backend.providers import EdgeTtsSynthesizer, ProviderError


async def test_edge_tts_collects_bounded_mp3_with_mapped_rate(monkeypatch):
    calls: list[tuple[str, str, str]] = []

    class Communicate:
        def __init__(self, text: str, voice: str, *, rate: str) -> None:
            calls.append((text, voice, rate))

        async def stream(self):
            yield {"type": "WordBoundary", "data": None}
            yield {"type": "audio", "data": b"first"}
            yield {"type": "audio", "data": b"second"}

    monkeypatch.setitem(
        sys.modules,
        "edge_tts",
        SimpleNamespace(Communicate=Communicate),
    )
    provider = EdgeTtsSynthesizer(
        voice="zh-TW-HsiaoChenNeural",
        timeout_seconds=5,
        max_audio_bytes=32,
    )

    result = await provider.synthesize("台灣中文", 1.2)

    assert calls == [
        ("台灣中文", "zh-TW-HsiaoChenNeural", "+20%"),
    ]
    assert result.audio == b"firstsecond"
    assert result.mime_type == "audio/mpeg"
    assert provider.name == (
        "edge-tts-online-unofficial:zh-TW-HsiaoChenNeural"
    )


@pytest.mark.parametrize("chunks", [[], [b"too-large"]])
async def test_edge_tts_fails_loudly_for_empty_or_oversized_audio(
    monkeypatch,
    chunks,
):
    class Communicate:
        def __init__(self, text: str, voice: str, *, rate: str) -> None:
            pass

        async def stream(self):
            for chunk in chunks:
                yield {"type": "audio", "data": chunk}

    monkeypatch.setitem(
        sys.modules,
        "edge_tts",
        SimpleNamespace(Communicate=Communicate),
    )
    provider = EdgeTtsSynthesizer(
        voice="zh-TW-HsiaoChenNeural",
        timeout_seconds=5,
        max_audio_bytes=4,
    )

    with pytest.raises(ProviderError):
        await provider.synthesize("測試", 1.0)
