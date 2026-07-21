from __future__ import annotations

import pytest

from taigi_news_reader_backend.providers import AudioResult, ProviderError
from taigi_news_reader_backend.service import SynthesisService


RAW_ROMANIZATION = "Kin-á-ji̍t thiⁿ-khì chin hó。"
NORMALIZED_ROMANIZATION = "kin-á-ji̍t thinn-khì chin hó"


class TranslationMustNotRun:
    name = "translator:must-not-run"

    async def translate(self, text: str) -> str:
        raise AssertionError("direct romanization must not call translation")

    async def aclose(self) -> None:
        return None


class RecordingSynthesizer:
    name = "test:mms-tts-nan"

    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    async def synthesize(self, text: str, rate: float) -> AudioResult:
        self.calls.append((text, rate))
        return AudioResult(audio=b"RIFF-test-WAVE")

    async def aclose(self) -> None:
        return None


async def test_direct_romanization_is_normalized_before_mms_and_response():
    synthesizer = RecordingSynthesizer()
    service = SynthesisService(TranslationMustNotRun(), synthesizer)

    result = await service.synthesize(
        RAW_ROMANIZATION,
        1.1,
        source_language="nan-Latn-TW",
        target_language="nan-TW",
    )

    assert synthesizer.calls == [(NORMALIZED_ROMANIZATION, 1.1)]
    assert result.spoken_text == NORMALIZED_ROMANIZATION
    assert result.taigi_text == NORMALIZED_ROMANIZATION
    assert result.provider == "direct:nan-Latn-TW+test:mms-tts-nan"


async def test_direct_romanization_rejects_unsupported_mms_characters_before_tts():
    synthesizer = RecordingSynthesizer()
    service = SynthesisService(TranslationMustNotRun(), synthesizer)

    with pytest.raises(ProviderError, match="romanization input is incompatible"):
        await service.synthesize(
            "Tâi-gí 2026",
            1.0,
            source_language="nan-Latn-TW",
            target_language="nan-TW",
        )

    assert synthesizer.calls == []
