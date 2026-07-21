"""Provider orchestration with no storage or fallback behavior."""

from __future__ import annotations

import base64

from .models import (
    SourceLanguage,
    SynthesisCapability,
    SynthesizeResponse,
    TargetLanguage,
)
from .providers.base import ProviderError, SpeechProvider, TranslationProvider
from .providers.poj import normalize_and_validate_mms_poj


class SynthesisService:
    def __init__(
        self,
        translator: TranslationProvider,
        synthesizer: SpeechProvider,
        mandarin_synthesizer: SpeechProvider | None = None,
    ) -> None:
        self.translator = translator
        self.synthesizer = synthesizer
        self.mandarin_synthesizer = mandarin_synthesizer

    @property
    def provider_name(self) -> str:
        return f"{self.translator.name}+{self.synthesizer.name}"

    @property
    def source_languages(self) -> tuple[SourceLanguage, ...]:
        return ("zh-TW", "nan-Latn-TW")

    @property
    def target_languages(self) -> tuple[TargetLanguage, ...]:
        if self.mandarin_synthesizer is None:
            return ("nan-TW",)
        return ("nan-TW", "zh-TW")

    @property
    def capabilities(self) -> tuple[SynthesisCapability, ...]:
        capabilities = [
            SynthesisCapability(
                source_language="zh-TW",
                target_language="nan-TW",
                mode="translate-to-taigi",
                provider=self.provider_name,
            ),
            SynthesisCapability(
                source_language="nan-Latn-TW",
                target_language="nan-TW",
                mode="read-taigi-romanization",
                provider=f"direct:nan-Latn-TW+{self.synthesizer.name}",
            ),
        ]
        if self.mandarin_synthesizer is not None:
            provider = (
                f"direct:zh-TW+{self.mandarin_synthesizer.name}"
            )
            capabilities.append(
                SynthesisCapability(
                    source_language="zh-TW",
                    target_language="zh-TW",
                    mode="online-mandarin-backup",
                    provider=provider,
                    network_required=True,
                    unofficial=True,
                    sla_guaranteed=False,
                )
            )
        return tuple(capabilities)

    async def synthesize(
        self,
        text: str,
        rate: float,
        source_language: SourceLanguage = "zh-TW",
        target_language: TargetLanguage = "nan-TW",
    ) -> SynthesizeResponse:
        if source_language == "zh-TW" and target_language == "nan-TW":
            taigi_text = await self.translator.translate(text)
            spoken_text = taigi_text
            provider = self.provider_name
            synthesizer = self.synthesizer
        elif source_language == "nan-Latn-TW" and target_language == "nan-TW":
            # The caller explicitly supplied Taiwanese Hokkien romanization.
            # Do not translate it again, and do not claim that the configured
            # translator participated in this result.
            provider = f"direct:nan-Latn-TW+{self.synthesizer.name}"
            spoken_text = normalize_and_validate_mms_poj(
                text,
                provider=provider,
                value_kind="romanization input",
            )
            taigi_text = spoken_text
            synthesizer = self.synthesizer
        elif source_language == "zh-TW" and target_language == "zh-TW":
            if self.mandarin_synthesizer is None:
                raise ProviderError("online Mandarin backup is not configured")
            taigi_text = None
            spoken_text = text
            provider = f"direct:zh-TW+{self.mandarin_synthesizer.name}"
            synthesizer = self.mandarin_synthesizer
        else:  # pragma: no cover - the HTTP model prevents unsupported pairs.
            raise ValueError(
                f"unsupported language pair: {source_language}->{target_language}"
            )
        audio = await synthesizer.synthesize(spoken_text, rate)
        if audio.mime_type not in {"audio/wav", "audio/mpeg"}:
            raise RuntimeError(f"unsupported speech MIME type: {audio.mime_type}")
        return SynthesizeResponse(
            spoken_text=spoken_text,
            taigi_text=taigi_text,
            audio_base64=base64.b64encode(audio.audio).decode("ascii"),
            mime_type=audio.mime_type,
            provider=provider,
        )

    async def aclose(self) -> None:
        await self.translator.aclose()
        await self.synthesizer.aclose()
        if self.mandarin_synthesizer is not None:
            await self.mandarin_synthesizer.aclose()
