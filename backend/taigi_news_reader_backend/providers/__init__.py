"""Translation and TTS provider adapters."""

from .base import AudioResult, ProviderError, SpeechProvider, TranslationProvider
from .gemini import GeminiTranslator
from .mms import MmsTtsSynthesizer
from .mock import MockTranslator, MockTtsSynthesizer
from .ollama import OllamaTranslator
from .openai_compatible import OpenAICompatibleTranslator
from .remote_tts import RemoteTtsSynthesizer

__all__ = [
    "AudioResult",
    "GeminiTranslator",
    "MmsTtsSynthesizer",
    "MockTranslator",
    "MockTtsSynthesizer",
    "OllamaTranslator",
    "OpenAICompatibleTranslator",
    "ProviderError",
    "RemoteTtsSynthesizer",
    "SpeechProvider",
    "TranslationProvider",
]
