"""Gemini adapter through Google's OpenAI-compatible HTTPS API."""

from __future__ import annotations

from .openai_compatible import OpenAICompatibleTranslator


class GeminiTranslator(OpenAICompatibleTranslator):
    """Reuse the hardened chat-completions flow with Gemini-specific identity."""

    @property
    def name(self) -> str:
        return f"gemini:{self.model}"

    @property
    def _provider_label(self) -> str:
        return "Gemini"
