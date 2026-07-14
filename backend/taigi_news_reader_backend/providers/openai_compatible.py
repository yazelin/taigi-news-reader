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


class _RetryableTranslationError(ProviderError):
    """A completion response was valid JSON but not a complete translation."""

    def __init__(
        self,
        provider_label: str,
        *,
        kind: str,
        finish_reason: str | None,
    ) -> None:
        self.kind = kind
        self.finish_reason = finish_reason
        suffix = f" (finish_reason={finish_reason})" if finish_reason else ""
        messages = {
            "empty": "returned an empty translation",
            "incomplete": "returned an incomplete translation",
            "output_limit": "translation exceeded the output limit",
        }
        super().__init__(f"{provider_label} {messages[kind]}" + suffix)


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

    @property
    def _provider_label(self) -> str:
        return "OpenAI-compatible provider"

    async def translate(self, text: str) -> str:
        prompt = (
            "Translate the following JSON string containing a Traditional "
            "Chinese news passage. Do not repeat any sentence, phrase, word, "
            "or syllable. End immediately after translating the final source "
            "sentence:\n"
            + json.dumps(text, ensure_ascii=False)
        )
        translation = await self._generate_with_retry(
            system=SYSTEM_PROMPT,
            prompt=prompt,
        )
        try:
            return normalize_and_validate_mms_poj(
                translation, provider=self._provider_label
            )
        except ProviderError:
            repair_prompt = (
                "Repair this JSON string containing the invalid translation:\n"
                "Return one repaired copy only. Do not repeat any sentence, "
                "phrase, word, or syllable:\n"
                + json.dumps(translation, ensure_ascii=False)
            )
            repaired = await self._generate_with_retry(
                system=REPAIR_SYSTEM_PROMPT,
                prompt=repair_prompt,
            )
            try:
                return normalize_and_validate_mms_poj(
                    repaired, provider=self._provider_label
                )
            except ProviderError as exc:
                raise ProviderError(
                    f"{self._provider_label} failed to produce MMS-compatible "
                    "POJ after one repair attempt"
                ) from exc

    async def _generate_with_retry(self, *, system: str, prompt: str) -> str:
        try:
            return await self._generate(system=system, prompt=prompt)
        except _RetryableTranslationError as first_error:
            try:
                # Retry the identical request once. Never substitute provider
                # reasoning, another provider, or source-language text.
                return await self._generate(system=system, prompt=prompt)
            except _RetryableTranslationError as retry_error:
                first_reason = first_error.finish_reason or "unavailable"
                retry_reason = retry_error.finish_reason or "unavailable"
                raise ProviderError(
                    f"{self._provider_label} failed to return a complete "
                    "translation after one retry "
                    f"(first={first_error.kind}:{first_reason}, "
                    f"retry={retry_error.kind}:{retry_reason})"
                ) from retry_error

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
        # finish_reason=length. Groq also recommends a 0.5-0.7 temperature for
        # reasoning models to avoid repetitive or incoherent output. These
        # fields are model-specific extensions, so never send them to a generic
        # OpenAI-compatible provider.
        if self.model in GROQ_GPT_OSS_MODELS:
            payload.update(
                temperature=0.6,
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
            raise ProviderError(
                f"{self._provider_label} translation request failed"
            ) from exc
        if translation is None:
            raise _RetryableTranslationError(
                self._provider_label,
                kind="empty",
                finish_reason=finish_reason,
            )
        if not isinstance(translation, str):
            raise ProviderError(f"{self._provider_label} returned no translation")
        if finish_reason == "length" and translation.strip():
            raise _RetryableTranslationError(
                self._provider_label,
                kind="incomplete",
                finish_reason=finish_reason,
            )
        translation = OllamaTranslator._clean_response(translation)
        if len(translation) > self.max_output_chars:
            raise _RetryableTranslationError(
                self._provider_label,
                kind="output_limit",
                finish_reason=finish_reason,
            )
        if not translation:
            raise _RetryableTranslationError(
                self._provider_label,
                kind="empty",
                finish_reason=finish_reason,
            )
        return translation

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
