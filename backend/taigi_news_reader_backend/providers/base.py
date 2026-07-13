"""Provider contracts and shared failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    """A concrete upstream provider could not produce a trustworthy result."""


@dataclass(frozen=True, slots=True)
class AudioResult:
    audio: bytes
    mime_type: str = "audio/wav"


class TranslationProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def translate(self, text: str) -> str: ...

    async def aclose(self) -> None: ...


class SpeechProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def synthesize(self, text: str, rate: float) -> AudioResult: ...

    async def aclose(self) -> None: ...
