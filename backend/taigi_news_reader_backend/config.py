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
class AccessTokenHash:
    """A stable pseudonymous subject mapped to one SHA-256 token digest."""

    subject: str
    sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", self.subject):
            raise ValueError(
                "access token subject must be 1-64 letters, numbers, dots, underscores, or hyphens"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError(
                "access token digest must be a lowercase 64-character SHA-256 hex value"
            )


def _get_access_token_hashes() -> tuple[AccessTokenHash, ...]:
    raw = os.getenv("TAIGI_ACCESS_TOKEN_HASHES", "")
    entries: list[AccessTokenHash] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(
                "TAIGI_ACCESS_TOKEN_HASHES entries must use subject=sha256 format"
            )
        subject, digest = (part.strip() for part in item.split("=", 1))
        entries.append(AccessTokenHash(subject=subject, sha256=digest))
    return tuple(entries)


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
    require_allowed_origin: bool = False
    require_access_token: bool = False
    access_token_hashes: tuple[AccessTokenHash, ...] = field(
        default=(),
        repr=False,
    )
    quota_database_path: str = "./taigi-access.sqlite3"
    daily_subject_job_limit: int = 20
    daily_subject_character_limit: int = 50_000
    daily_global_job_limit: int = 100
    daily_global_character_limit: int = 250_000
    max_active_jobs: int = 4
    max_outstanding_jobs: int = 12
    max_outstanding_jobs_per_subject: int = 3
    max_terminal_result_bytes: int = 128 * 1024 * 1024
    max_terminal_result_bytes_per_subject: int = 40 * 1024 * 1024
    terminal_job_ttl_seconds: int = 600

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
        if self.require_allowed_origin and not self.extension_ids:
            raise ValueError(
                "strict extension validation requires at least one Chrome extension ID"
            )
        subjects = [entry.subject for entry in self.access_token_hashes]
        digests = [entry.sha256 for entry in self.access_token_hashes]
        if len(subjects) != len(set(subjects)):
            raise ValueError("access token subjects must be unique")
        if len(digests) != len(set(digests)):
            raise ValueError("access token SHA-256 digests must be unique")
        if self.require_access_token and not self.access_token_hashes:
            raise ValueError(
                "strict access-token authentication requires at least one configured hash"
            )
        if not self.quota_database_path.strip():
            raise ValueError("quota_database_path must not be blank")
        quota_values = {
            "daily_subject_job_limit": self.daily_subject_job_limit,
            "daily_subject_character_limit": self.daily_subject_character_limit,
            "daily_global_job_limit": self.daily_global_job_limit,
            "daily_global_character_limit": self.daily_global_character_limit,
        }
        for name, value in quota_values.items():
            if value < 1:
                raise ValueError(f"{name} must be positive")
        if self.max_active_jobs < 1:
            raise ValueError("max_active_jobs must be positive")
        if self.max_outstanding_jobs < self.max_active_jobs:
            raise ValueError(
                "max_outstanding_jobs must be at least max_active_jobs"
            )
        if not 1 <= self.max_outstanding_jobs_per_subject <= self.max_outstanding_jobs:
            raise ValueError(
                "max_outstanding_jobs_per_subject must be between 1 and max_outstanding_jobs"
            )
        if self.max_terminal_result_bytes < 1:
            raise ValueError("max_terminal_result_bytes must be positive")
        if not 1 <= self.max_terminal_result_bytes_per_subject <= self.max_terminal_result_bytes:
            raise ValueError(
                "max_terminal_result_bytes_per_subject must be between 1 and max_terminal_result_bytes"
            )
        if self.terminal_job_ttl_seconds < 1:
            raise ValueError("terminal_job_ttl_seconds must be positive")
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
            require_allowed_origin=_get_bool(
                "TAIGI_REQUIRE_ALLOWED_ORIGIN", False
            ),
            require_access_token=_get_bool(
                "TAIGI_REQUIRE_ACCESS_TOKEN", False
            ),
            access_token_hashes=_get_access_token_hashes(),
            quota_database_path=os.getenv(
                "TAIGI_QUOTA_DATABASE_PATH", "./taigi-access.sqlite3"
            ),
            daily_subject_job_limit=_get_int(
                "TAIGI_DAILY_SUBJECT_JOB_LIMIT",
                20,
                minimum=1,
                maximum=1_000_000,
            ),
            daily_subject_character_limit=_get_int(
                "TAIGI_DAILY_SUBJECT_CHARACTER_LIMIT",
                50_000,
                minimum=1,
                maximum=2_000_000_000,
            ),
            daily_global_job_limit=_get_int(
                "TAIGI_DAILY_GLOBAL_JOB_LIMIT",
                100,
                minimum=1,
                maximum=1_000_000,
            ),
            daily_global_character_limit=_get_int(
                "TAIGI_DAILY_GLOBAL_CHARACTER_LIMIT",
                250_000,
                minimum=1,
                maximum=2_000_000_000,
            ),
            max_active_jobs=_get_int(
                "TAIGI_MAX_ACTIVE_JOBS",
                4,
                minimum=1,
                maximum=1_000,
            ),
            max_outstanding_jobs=_get_int(
                "TAIGI_MAX_OUTSTANDING_JOBS",
                12,
                minimum=1,
                maximum=10_000,
            ),
            max_outstanding_jobs_per_subject=_get_int(
                "TAIGI_MAX_OUTSTANDING_JOBS_PER_SUBJECT",
                3,
                minimum=1,
                maximum=10_000,
            ),
            max_terminal_result_bytes=_get_int(
                "TAIGI_MAX_TERMINAL_RESULT_BYTES",
                128 * 1024 * 1024,
                minimum=1,
                maximum=2_000_000_000,
            ),
            max_terminal_result_bytes_per_subject=_get_int(
                "TAIGI_MAX_TERMINAL_RESULT_BYTES_PER_SUBJECT",
                40 * 1024 * 1024,
                minimum=1,
                maximum=2_000_000_000,
            ),
            terminal_job_ttl_seconds=_get_int(
                "TAIGI_TERMINAL_JOB_TTL_SECONDS",
                600,
                minimum=1,
                maximum=86_400,
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

    def origin_is_allowed(self, origin: str) -> bool:
        return re.fullmatch(self.cors_origin_regex(), origin) is not None

    def extension_request_is_allowed(
        self, extension_id: str, origin: str | None = None
    ) -> bool:
        if extension_id not in self.extension_ids:
            return False
        if not origin:
            return True
        if origin.startswith("chrome-extension://"):
            return origin == f"chrome-extension://{extension_id}"
        return self.origin_is_allowed(origin)
