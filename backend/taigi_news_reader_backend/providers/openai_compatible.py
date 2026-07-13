"""Generic OpenAI-compatible chat-completions translation adapter."""

from __future__ import annotations

import json

import httpx

from .base import ProviderError
from .ollama import OllamaTranslator, SYSTEM_PROMPT
from .poj import normalize_and_validate_mms_poj


class OpenAICompatibleTranslator:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_chars: int,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.max_output_chars = max_output_chars
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout_seconds),
        )

    @property
    def name(self) -> str:
        return f"openai-compatible:{self.model}"

    async def translate(self, text: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Translate the following JSON string containing a "
                        "Traditional Chinese news passage:\n"
                        + json.dumps(text, ensure_ascii=False)
                    ),
                },
            ],
            "temperature": 0.1,
        }
        try:
            # A relative path preserves provider prefixes such as `/v1` in the
            # configured base URL; a leading slash would silently discard it.
            response = await self._client.post("chat/completions", json=payload)
            response.raise_for_status()
            body = response.json()
            translation = body["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenAI-compatible translation request failed") from exc
        if not isinstance(translation, str):
            raise ProviderError("OpenAI-compatible provider returned no translation")
        translation = OllamaTranslator._clean_response(translation)
        if not translation:
            raise ProviderError("OpenAI-compatible provider returned an empty translation")
        if len(translation) > self.max_output_chars:
            raise ProviderError("translation exceeded the output limit")
        return normalize_and_validate_mms_poj(
            translation, provider="OpenAI-compatible provider"
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
