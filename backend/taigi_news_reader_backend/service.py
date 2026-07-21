"""Provider orchestration with no storage or fallback behavior."""

from __future__ import annotations

import base64

from .models import SourceLanguage, SynthesizeResponse
from .providers.base import SpeechProvider, TranslationProvider


class SynthesisService:
    def __init__(
        self, translator: TranslationProvider, synthesizer: SpeechProvider
    ) -> None:
        self.translator = translator
        self.synthesizer = synthesizer

    @property
    def provider_name(self) -> str:
        return f"{self.translator.name}+{self.synthesizer.name}"

    async def synthesize(
        self,
        text: str,
        rate: float,
        source_language: SourceLanguage = "zh-TW",
    ) -> SynthesizeResponse:
        if source_language == "zh-TW":
            taigi_text = await self.translator.translate(text)
            provider = self.provider_name
        elif source_language == "nan-Latn-TW":
            # The caller explicitly supplied Taiwanese Hokkien romanization.
            # Do not translate it again, and do not claim that the configured
            # translator participated in this result.
            taigi_text = text
            provider = f"direct:nan-Latn-TW+{self.synthesizer.name}"
        else:  # pragma: no cover - the HTTP model and type checker prevent it.
            raise ValueError(f"unsupported source language: {source_language}")
        audio = await self.synthesizer.synthesize(taigi_text, rate)
        if audio.mime_type != "audio/wav":
            raise RuntimeError(f"unsupported speech MIME type: {audio.mime_type}")
        return SynthesizeResponse(
            taigi_text=taigi_text,
            audio_base64=base64.b64encode(audio.audio).decode("ascii"),
            mime_type="audio/wav",
            provider=provider,
        )

    async def aclose(self) -> None:
        await self.translator.aclose()
        await self.synthesizer.aclose()
