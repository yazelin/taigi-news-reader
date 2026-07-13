"""Environment-backed service configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from urllib.parse import urlsplit


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _get_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _get_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _validate_secret_bearing_url(value: str, *, name: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{name} must be a valid http(s) URL")
    if parsed.scheme == "http" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
    }:
        raise ValueError(
            f"{name} must use HTTPS unless it points to localhost or 127.0.0.1"
        )


@dataclass(frozen=True, slots=True)
class Settings:
    provider_mode: str = "concrete"
    translator_provider: str = "ollama"
    tts_provider: str = "mms"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    ollama_timeout_seconds: float = 45.0
    mms_model: str = "facebook/mms-tts-nan"
    mms_device: str = "cpu"
    mms_timeout_seconds: float = 180.0
    openai_base_url: str | None = None
    openai_api_key: str | None = field(default=None, repr=False)
    openai_model: str | None = None
    openai_timeout_seconds: float = 45.0
    gemini_base_url: str = (
        "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_model: str = "gemini-3.5-flash"
    gemini_timeout_seconds: float = 45.0
    remote_tts_url: str | None = None
    remote_tts_api_key: str | None = field(default=None, repr=False)
    remote_tts_timeout_seconds: float = 180.0
    max_audio_bytes: int = 25 * 1024 * 1024
    max_text_chars: int = 5_000
    max_translated_chars: int = 12_000
    extension_ids: tuple[str, ...] = ()
    allow_localhost_origins: bool = True

    def __post_init__(self) -> None:
        if self.provider_mode not in {"concrete", "mock"}:
            raise ValueError("provider_mode must be 'concrete' or 'mock'")
        if self.translator_provider not in {
            "ollama",
            "openai_compatible",
            "gemini",
        }:
            raise ValueError(
                "translator_provider must be 'ollama', 'openai_compatible', or 'gemini'"
            )
        if self.tts_provider not in {"mms", "remote"}:
            raise ValueError("tts_provider must be 'mms' or 'remote'")
        if not self.ollama_base_url.startswith(("http://", "https://")):
            raise ValueError("ollama_base_url must be an http(s) URL")
        if self.mms_device != "cpu" and not self.mms_device.startswith("cuda"):
            raise ValueError("mms_device must be 'cpu' or a CUDA device")
        if not 1 <= self.max_text_chars <= 5_000:
            raise ValueError("max_text_chars must be between 1 and 5000")
        if not self.max_text_chars <= self.max_translated_chars <= 20_000:
            raise ValueError("max_translated_chars must be between max_text_chars and 20000")
        for extension_id in self.extension_ids:
            if not re.fullmatch(r"[a-p]{32}", extension_id):
                raise ValueError(f"invalid Chrome extension ID: {extension_id!r}")
        if self.provider_mode == "concrete":
            if self.translator_provider == "openai_compatible":
                if not self.openai_base_url or not self.openai_model or not self.openai_api_key:
                    raise ValueError(
                        "OpenAI-compatible translation requires base URL, model, and API key"
                    )
                _validate_secret_bearing_url(
                    self.openai_base_url, name="openai_base_url"
                )
            if self.translator_provider == "gemini":
                if not self.gemini_api_key or not self.gemini_api_key.strip():
                    raise ValueError(
                        "Gemini translation requires TAIGI_GEMINI_API_KEY"
                    )
                if not self.gemini_model or not self.gemini_model.strip():
                    raise ValueError("Gemini translation requires a model")
                if not 1 <= self.gemini_timeout_seconds <= 300:
                    raise ValueError(
                        "gemini_timeout_seconds must be between 1 and 300"
                    )
                _validate_secret_bearing_url(
                    self.gemini_base_url, name="gemini_base_url"
                )
            if self.tts_provider == "remote":
                if not self.remote_tts_url:
                    raise ValueError("remote TTS requires TAIGI_REMOTE_TTS_URL")
                _validate_secret_bearing_url(
                    self.remote_tts_url, name="remote_tts_url"
                )

    @classmethod
    def from_env(cls) -> "Settings":
        ids = tuple(
            value.strip()
            for value in os.getenv("TAIGI_EXTENSION_IDS", "").split(",")
            if value.strip()
        )
        return cls(
            provider_mode=os.getenv("TAIGI_PROVIDER_MODE", "concrete").strip().lower(),
            translator_provider=os.getenv(
                "TAIGI_TRANSLATOR_PROVIDER", "ollama"
            ).strip().lower(),
            tts_provider=os.getenv("TAIGI_TTS_PROVIDER", "mms").strip().lower(),
            ollama_base_url=os.getenv(
                "TAIGI_OLLAMA_BASE_URL", "http://127.0.0.1:11434"
            ).rstrip("/"),
            ollama_model=os.getenv(
                "TAIGI_OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M"
            ),
            ollama_timeout_seconds=_get_float(
                "TAIGI_OLLAMA_TIMEOUT_SECONDS", 45, minimum=1, maximum=300
            ),
            mms_model=os.getenv("TAIGI_MMS_MODEL", "facebook/mms-tts-nan"),
            mms_device=os.getenv("TAIGI_MMS_DEVICE", "cpu"),
            mms_timeout_seconds=_get_float(
                "TAIGI_MMS_TIMEOUT_SECONDS", 180, minimum=1, maximum=900
            ),
            openai_base_url=(
                os.getenv("TAIGI_OPENAI_BASE_URL", "").rstrip("/") or None
            ),
            openai_api_key=os.getenv("TAIGI_OPENAI_API_KEY") or None,
            openai_model=os.getenv("TAIGI_OPENAI_MODEL") or None,
            openai_timeout_seconds=_get_float(
                "TAIGI_OPENAI_TIMEOUT_SECONDS", 45, minimum=1, maximum=300
            ),
            gemini_base_url=os.getenv(
                "TAIGI_GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta/openai/",
            ),
            gemini_api_key=os.getenv("TAIGI_GEMINI_API_KEY") or None,
            gemini_model=os.getenv(
                "TAIGI_GEMINI_MODEL", "gemini-3.5-flash"
            ),
            gemini_timeout_seconds=_get_float(
                "TAIGI_GEMINI_TIMEOUT_SECONDS", 45, minimum=1, maximum=300
            ),
            remote_tts_url=os.getenv("TAIGI_REMOTE_TTS_URL") or None,
            remote_tts_api_key=os.getenv("TAIGI_REMOTE_TTS_API_KEY") or None,
            remote_tts_timeout_seconds=_get_float(
                "TAIGI_REMOTE_TTS_TIMEOUT_SECONDS", 180, minimum=1, maximum=900
            ),
            max_audio_bytes=_get_int(
                "TAIGI_MAX_AUDIO_BYTES",
                25 * 1024 * 1024,
                minimum=1_024,
                maximum=100 * 1024 * 1024,
            ),
            max_text_chars=_get_int(
                "TAIGI_MAX_TEXT_CHARS", 5_000, minimum=1, maximum=5_000
            ),
            max_translated_chars=_get_int(
                "TAIGI_MAX_TRANSLATED_CHARS", 12_000, minimum=1, maximum=20_000
            ),
            extension_ids=ids,
            allow_localhost_origins=_get_bool(
                "TAIGI_ALLOW_LOCALHOST_ORIGINS", True
            ),
        )

    def cors_origin_regex(self) -> str:
        if self.extension_ids:
            extensions = "(?:" + "|".join(map(re.escape, self.extension_ids)) + ")"
        else:
            extensions = r"[a-p]{32}"
        origins = [rf"chrome-extension://{extensions}"]
        if self.allow_localhost_origins:
            origins.append(r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?")
        return r"^(?:" + "|".join(origins) + r")$"
