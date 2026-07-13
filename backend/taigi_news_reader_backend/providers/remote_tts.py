"""HTTP adapter for a hosted Taiwanese Hokkien TTS provider."""

from __future__ import annotations

import base64
import binascii

import httpx

from .base import AudioResult, ProviderError


class RemoteTtsSynthesizer:
    """Call a provider that accepts text/language/rate and returns base64 WAV.

    The remote response contract is deliberately the audio subset of this
    service's public response: ``audio_base64`` and ``mime_type``.
    """

    def __init__(
        self,
        *,
        url: str,
        api_key: str | None,
        timeout_seconds: float,
        max_audio_bytes: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url
        self.max_audio_bytes = max_audio_bytes
        self._owns_client = client is None
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
        )

    @property
    def name(self) -> str:
        return "remote:taigi-tts"

    async def synthesize(self, text: str, rate: float) -> AudioResult:
        try:
            response = await self._client.post(
                self.url,
                json={"text": text, "language": "nan-TW", "rate": rate},
            )
            response.raise_for_status()
            body = response.json()
            encoded = body["audio_base64"]
            mime_type = body["mime_type"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ProviderError("remote Taigi TTS request failed") from exc
        if mime_type != "audio/wav" or not isinstance(encoded, str):
            raise ProviderError("remote Taigi TTS returned an unsupported response")
        try:
            audio = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ProviderError("remote Taigi TTS returned invalid base64 audio") from exc
        if not audio or len(audio) > self.max_audio_bytes:
            raise ProviderError("remote Taigi TTS audio is empty or exceeds the size limit")
        if not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
            raise ProviderError("remote Taigi TTS did not return a WAV file")
        return AudioResult(audio=audio)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

