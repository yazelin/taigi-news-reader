"""Unofficial network-only Taiwan Mandarin backup via edge-tts."""

from __future__ import annotations

import asyncio

from .base import AudioResult, ProviderError


class EdgeTtsSynthesizer:
    """Collect edge-tts' MP3 stream with explicit time and size bounds.

    edge-tts is an unofficial client for a Microsoft-operated online service.
    It is a best-effort fallback, not an offline engine or an SLA-backed API.
    """

    def __init__(
        self,
        *,
        voice: str,
        timeout_seconds: float,
        max_audio_bytes: int,
    ) -> None:
        self.voice = voice
        self.timeout_seconds = timeout_seconds
        self.max_audio_bytes = max_audio_bytes

    @property
    def name(self) -> str:
        return f"edge-tts-online-unofficial:{self.voice}"

    async def synthesize(self, text: str, rate: float) -> AudioResult:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - deployment guard
            raise ProviderError(
                "online Mandarin backup dependency is not installed"
            ) from exc

        rate_percent = round((rate - 1.0) * 100)
        edge_rate = f"{rate_percent:+d}%"
        chunks: list[bytes] = []
        size = 0
        try:
            async with asyncio.timeout(self.timeout_seconds):
                stream = edge_tts.Communicate(
                    text,
                    self.voice,
                    rate=edge_rate,
                ).stream()
                async for chunk in stream:
                    if chunk.get("type") != "audio":
                        continue
                    data = chunk.get("data")
                    if not isinstance(data, bytes):
                        raise ProviderError(
                            "online Mandarin backup returned invalid audio"
                        )
                    size += len(data)
                    if size > self.max_audio_bytes:
                        raise ProviderError(
                            "online Mandarin backup audio exceeds the size limit"
                        )
                    chunks.append(data)
        except ProviderError:
            raise
        except TimeoutError as exc:
            raise ProviderError("online Mandarin backup timed out") from exc
        except Exception as exc:
            raise ProviderError("online Mandarin backup request failed") from exc

        audio = b"".join(chunks)
        if not audio:
            raise ProviderError("online Mandarin backup returned no audio")
        return AudioResult(audio=audio, mime_type="audio/mpeg")

    async def aclose(self) -> None:
        return None
