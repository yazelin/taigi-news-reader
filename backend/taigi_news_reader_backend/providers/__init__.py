"""Translation and TTS provider adapters."""

from .base import AudioResult, ProviderError, SpeechProvider, TranslationProvider
from .edge_tts import EdgeTtsSynthesizer
from .gemini import GeminiTranslator
from .mms import MmsTtsSynthesizer
from .mock import MockMandarinTtsSynthesizer, MockTranslator, MockTtsSynthesizer
from .ollama import OllamaTranslator
from .openai_compatible import OpenAICompatibleTranslator
from .remote_tts import RemoteTtsSynthesizer

__all__ = [
    "AudioResult",
    "EdgeTtsSynthesizer",
    "GeminiTranslator",
    "MmsTtsSynthesizer",
    "MockTranslator",
    "MockMandarinTtsSynthesizer",
    "MockTtsSynthesizer",
    "OllamaTranslator",
    "OpenAICompatibleTranslator",
    "ProviderError",
    "RemoteTtsSynthesizer",
    "SpeechProvider",
    "TranslationProvider",
]
