"""Provider orchestration with no storage or fallback behavior."""

from __future__ import annotations

import base64

from .models import SynthesizeResponse
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

    async def synthesize(self, text: str, rate: float) -> SynthesizeResponse:
        taigi_text = await self.translator.translate(text)
        audio = await self.synthesizer.synthesize(taigi_text, rate)
        if audio.mime_type != "audio/wav":
            raise RuntimeError(f"unsupported speech MIME type: {audio.mime_type}")
        return SynthesizeResponse(
            taigi_text=taigi_text,
            audio_base64=base64.b64encode(audio.audio).decode("ascii"),
            mime_type="audio/wav",
            provider=self.provider_name,
        )

    async def aclose(self) -> None:
        await self.translator.aclose()
        await self.synthesizer.aclose()
