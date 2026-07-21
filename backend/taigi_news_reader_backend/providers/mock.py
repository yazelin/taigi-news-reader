"""Explicit deterministic providers for tests and UI development."""

from __future__ import annotations

import hashlib
import math

from .base import AudioResult
from .mms import float_waveform_to_wav


class MockTranslator:
    @property
    def name(self) -> str:
        return "mock:taigi-translator"

    async def translate(self, text: str) -> str:
        del text
        return "Tsit-ê sī tshik-thìng iōng ê Tâi-gí sin-bûn."

    async def aclose(self) -> None:
        return None


class MockTtsSynthesizer:
    @property
    def name(self) -> str:
        return "mock:wav-synthesizer"

    async def synthesize(self, text: str, rate: float) -> AudioResult:
        sample_rate = 16_000
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        frequency = 300 + int.from_bytes(digest[:2], "big") % 300
        sample_count = max(1, round(sample_rate * 0.25 / rate))
        samples = (
            0.15 * math.sin(2 * math.pi * frequency * index / sample_rate)
            for index in range(sample_count)
        )
        return AudioResult(float_waveform_to_wav(samples, sample_rate))

    async def aclose(self) -> None:
        return None


class MockMandarinTtsSynthesizer(MockTtsSynthesizer):
    @property
    def name(self) -> str:
        return "mock:online-mandarin-backup"
