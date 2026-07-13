"""Generic OpenAI-compatible chat-completions translation adapter."""

from __future__ import annotations

import json
import re

import httpx

from .base import ProviderError
from .ollama import OllamaTranslator, REPAIR_SYSTEM_PROMPT, SYSTEM_PROMPT
from .poj import normalize_and_validate_mms_poj


GROQ_GPT_OSS_MODELS = frozenset(
    {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}
)


class _EmptyTranslationError(ProviderError):
    """An otherwise valid completion response contained no translation text."""

    def __init__(self, finish_reason: str | None) -> None:
        self.finish_reason = finish_reason
        suffix = f" (finish_reason={finish_reason})" if finish_reason else ""
        super().__init__(
            "OpenAI-compatible provider returned an empty translation" + suffix
        )


def _safe_finish_reason(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value):
        return value
    return None


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
        prompt = (
            "Translate the following JSON string containing a Traditional "
            "Chinese news passage:\n"
            + json.dumps(text, ensure_ascii=False)
        )
        try:
            translation = await self._generate(system=SYSTEM_PROMPT, prompt=prompt)
        except _EmptyTranslationError as first_empty:
            try:
                # Retry the same translation request once. Do not substitute
                # provider reasoning, another provider, or source-language text.
                translation = await self._generate(
                    system=SYSTEM_PROMPT,
                    prompt=prompt,
                )
            except _EmptyTranslationError as retry_empty:
                first_reason = first_empty.finish_reason or "unavailable"
                retry_reason = retry_empty.finish_reason or "unavailable"
                raise ProviderError(
                    "OpenAI-compatible provider returned an empty translation "
                    "twice after one retry "
                    f"(finish_reason: first={first_reason}, retry={retry_reason})"
                ) from retry_empty
        try:
            return normalize_and_validate_mms_poj(
                translation, provider="OpenAI-compatible provider"
            )
        except ProviderError:
            repair_prompt = (
                "Repair this JSON string containing the invalid translation:\n"
                + json.dumps(translation, ensure_ascii=False)
            )
            repaired = await self._generate(
                system=REPAIR_SYSTEM_PROMPT,
                prompt=repair_prompt,
            )
            try:
                return normalize_and_validate_mms_poj(
                    repaired, provider="OpenAI-compatible provider"
                )
            except ProviderError as exc:
                raise ProviderError(
                    "OpenAI-compatible provider failed to produce MMS-compatible "
                    "POJ after one repair attempt"
                ) from exc

    async def _generate(self, *, system: str, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        # Groq's GPT-OSS models otherwise spend the default completion budget
        # on hidden reasoning and can return HTTP 200 with empty content and
        # finish_reason=length. These fields are model-specific extensions, so
        # never send them to a generic OpenAI-compatible provider.
        if self.model in GROQ_GPT_OSS_MODELS:
            payload.update(
                reasoning_effort="low",
                include_reasoning=False,
                max_completion_tokens=8_192,
            )
        try:
            # A relative path preserves provider prefixes such as `/v1` in the
            # configured base URL; a leading slash would silently discard it.
            response = await self._client.post("chat/completions", json=payload)
            response.raise_for_status()
            body = response.json()
            choice = body["choices"][0]
            translation = choice["message"]["content"]
            finish_reason = _safe_finish_reason(choice.get("finish_reason"))
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenAI-compatible translation request failed") from exc
        if translation is None:
            raise _EmptyTranslationError(finish_reason)
        if not isinstance(translation, str):
            raise ProviderError("OpenAI-compatible provider returned no translation")
        translation = OllamaTranslator._clean_response(translation)
        if not translation:
            raise _EmptyTranslationError(finish_reason)
        if len(translation) > self.max_output_chars:
            raise ProviderError("translation exceeded the output limit")
        return translation

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
