from __future__ import annotations

import re

import pytest

from taigi_news_reader_backend.config import AccessTokenHash, Settings


def test_concrete_defaults_are_local_real_providers():
    settings = Settings()

    assert settings.provider_mode == "concrete"
    assert settings.translator_provider == "ollama"
    assert settings.ollama_model == "qwen3:4b-instruct-2507-q4_K_M"
    assert settings.tts_provider == "mms"
    assert settings.mms_model == "facebook/mms-tts-nan"


def test_hosted_translation_fails_startup_validation_when_unconfigured():
    with pytest.raises(ValueError, match="base URL, model, and API key"):
        Settings(translator_provider="openai_compatible")


def test_gemini_requires_key_only_when_selected():
    assert Settings().gemini_api_key is None
    with pytest.raises(ValueError, match="TAIGI_GEMINI_API_KEY"):
        Settings(translator_provider="gemini")
    assert Settings(
        provider_mode="mock", translator_provider="gemini"
    ).translator_provider == "gemini"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"gemini_api_key": "   "}, "TAIGI_GEMINI_API_KEY"),
        ({"gemini_api_key": "test-key", "gemini_model": "  "}, "model"),
        (
            {"gemini_api_key": "test-key", "gemini_timeout_seconds": 0},
            "between 1 and 300",
        ),
        (
            {"gemini_api_key": "test-key", "gemini_timeout_seconds": 301},
            "between 1 and 300",
        ),
    ],
)
def test_gemini_direct_settings_reject_invalid_credentials_and_timeout(
    overrides, message
):
    with pytest.raises(ValueError, match=message):
        Settings(translator_provider="gemini", **overrides)


def test_settings_repr_never_contains_provider_keys():
    settings = Settings(
        openai_api_key="openai-secret-marker",
        gemini_api_key="gemini-secret-marker",
        remote_tts_api_key="tts-secret-marker",
    )

    rendered = repr(settings)
    assert "openai-secret-marker" not in rendered
    assert "gemini-secret-marker" not in rendered
    assert "tts-secret-marker" not in rendered


def test_gemini_environment_defaults(monkeypatch):
    monkeypatch.setenv("TAIGI_PROVIDER_MODE", "concrete")
    monkeypatch.setenv("TAIGI_TRANSLATOR_PROVIDER", "gemini")
    monkeypatch.setenv("TAIGI_TTS_PROVIDER", "mms")
    monkeypatch.setenv("TAIGI_GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("TAIGI_GEMINI_BASE_URL", raising=False)
    monkeypatch.delenv("TAIGI_GEMINI_MODEL", raising=False)
    monkeypatch.delenv("TAIGI_GEMINI_TIMEOUT_SECONDS", raising=False)

    settings = Settings.from_env()

    assert settings.gemini_base_url == (
        "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    assert settings.gemini_model == "gemini-3.5-flash"
    assert settings.gemini_timeout_seconds == 45


def test_remote_tts_fails_startup_validation_when_unconfigured():
    with pytest.raises(ValueError, match="TAIGI_REMOTE_TTS_URL"):
        Settings(tts_provider="remote")


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "translator_provider": "openai_compatible",
            "openai_base_url": "http://api.example/v1",
            "openai_api_key": "secret",
            "openai_model": "model",
        },
        {
            "tts_provider": "remote",
            "remote_tts_url": "http://tts.example/synthesize",
            "remote_tts_api_key": "secret",
        },
        {
            "translator_provider": "gemini",
            "gemini_base_url": "http://generativelanguage.googleapis.com/v1beta/openai/",
            "gemini_api_key": "secret",
        },
    ],
)
def test_hosted_provider_urls_require_https(kwargs):
    with pytest.raises(ValueError, match="must use HTTPS"):
        Settings(**kwargs)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:9000/v1",
        "http://127.0.0.1:9000/v1",
        "https://api.example/v1",
    ],
)
def test_openai_provider_allows_https_or_loopback_http(url):
    settings = Settings(
        translator_provider="openai_compatible",
        openai_base_url=url,
        openai_api_key="secret",
        openai_model="model",
    )

    assert settings.openai_base_url == url


def test_mock_mode_does_not_require_hosted_configuration():
    settings = Settings(
        provider_mode="mock",
        translator_provider="openai_compatible",
        tts_provider="remote",
    )

    assert settings.provider_mode == "mock"


def test_extension_ids_are_validated_and_escaped():
    extension_id = "a" * 32
    regex = Settings(extension_ids=(extension_id,)).cors_origin_regex()

    assert re.fullmatch(regex, f"chrome-extension://{extension_id}")
    assert not re.fullmatch(regex, f"chrome-extension://{'b' * 32}")
    with pytest.raises(ValueError, match="invalid Chrome extension ID"):
        Settings(extension_ids=("not-an-id",))


def test_strict_extension_validation_requires_a_pinned_extension_id():
    with pytest.raises(ValueError, match="requires at least one Chrome extension ID"):
        Settings(require_allowed_origin=True)

    extension_id = "a" * 32
    settings = Settings(
        extension_ids=(extension_id,),
        allow_localhost_origins=False,
        require_allowed_origin=True,
    )

    assert settings.extension_request_is_allowed(extension_id)
    assert settings.extension_request_is_allowed(
        extension_id, f"chrome-extension://{extension_id}"
    )
    assert not settings.extension_request_is_allowed("b" * 32)
    assert not settings.extension_request_is_allowed(
        extension_id, f"chrome-extension://{'b' * 32}"
    )
    assert settings.origin_is_allowed(f"chrome-extension://{extension_id}")
    assert not settings.origin_is_allowed(f"chrome-extension://{'b' * 32}")
    assert not settings.origin_is_allowed("http://localhost:5173")


def test_strict_extension_validation_loads_from_environment(monkeypatch):
    extension_id = "a" * 32
    monkeypatch.setenv("TAIGI_EXTENSION_IDS", extension_id)
    monkeypatch.setenv("TAIGI_ALLOW_LOCALHOST_ORIGINS", "false")
    monkeypatch.setenv("TAIGI_REQUIRE_ALLOWED_ORIGIN", "true")

    settings = Settings.from_env()

    assert settings.extension_ids == (extension_id,)
    assert settings.allow_localhost_origins is False
    assert settings.require_allowed_origin is True


def test_strict_access_authentication_requires_hashed_tokens_only():
    with pytest.raises(ValueError, match="at least one configured hash"):
        Settings(require_access_token=True)

    digest = "a" * 64
    settings = Settings(
        require_access_token=True,
        access_token_hashes=(
            AccessTokenHash(subject="reviewer-01", sha256=digest),
        ),
    )

    assert settings.require_access_token is True
    assert settings.access_token_hashes[0].subject == "reviewer-01"
    assert digest not in repr(settings)


@pytest.mark.parametrize(
    ("subject", "digest", "message"),
    [
        ("email@example.com", "a" * 64, "subject"),
        ("", "a" * 64, "subject"),
        ("reviewer", "A" * 64, "lowercase"),
        ("reviewer", "not-a-sha256", "SHA-256"),
    ],
)
def test_access_token_hash_entries_are_strictly_validated(subject, digest, message):
    with pytest.raises(ValueError, match=message):
        AccessTokenHash(subject=subject, sha256=digest)


def test_access_token_subjects_and_hashes_must_be_unique():
    first = AccessTokenHash(subject="tester-a", sha256="a" * 64)
    with pytest.raises(ValueError, match="subjects must be unique"):
        Settings(access_token_hashes=(first, AccessTokenHash("tester-a", "b" * 64)))
    with pytest.raises(ValueError, match="digests must be unique"):
        Settings(access_token_hashes=(first, AccessTokenHash("tester-b", "a" * 64)))


def test_access_and_quota_configuration_loads_from_environment(monkeypatch):
    monkeypatch.setenv("TAIGI_REQUIRE_ACCESS_TOKEN", "true")
    monkeypatch.setenv(
        "TAIGI_ACCESS_TOKEN_HASHES",
        f"reviewer-01={'a' * 64},tester-02={'b' * 64}",
    )
    monkeypatch.setenv("TAIGI_QUOTA_DATABASE_PATH", "/tmp/quota.sqlite")
    monkeypatch.setenv("TAIGI_DAILY_SUBJECT_JOB_LIMIT", "7")
    monkeypatch.setenv("TAIGI_DAILY_SUBJECT_CHARACTER_LIMIT", "8000")
    monkeypatch.setenv("TAIGI_DAILY_GLOBAL_JOB_LIMIT", "30")
    monkeypatch.setenv("TAIGI_DAILY_GLOBAL_CHARACTER_LIMIT", "40000")
    monkeypatch.setenv("TAIGI_MAX_ACTIVE_JOBS", "2")
    monkeypatch.setenv("TAIGI_MAX_OUTSTANDING_JOBS", "8")
    monkeypatch.setenv("TAIGI_MAX_OUTSTANDING_JOBS_PER_SUBJECT", "2")
    monkeypatch.setenv("TAIGI_MAX_TERMINAL_RESULT_BYTES", "1000000")
    monkeypatch.setenv(
        "TAIGI_MAX_TERMINAL_RESULT_BYTES_PER_SUBJECT", "500000"
    )
    monkeypatch.setenv("TAIGI_TERMINAL_JOB_TTL_SECONDS", "300")

    settings = Settings.from_env()

    assert [entry.subject for entry in settings.access_token_hashes] == [
        "reviewer-01",
        "tester-02",
    ]
    assert settings.quota_database_path == "/tmp/quota.sqlite"
    assert settings.daily_subject_job_limit == 7
    assert settings.daily_subject_character_limit == 8000
    assert settings.daily_global_job_limit == 30
    assert settings.daily_global_character_limit == 40000
    assert settings.max_active_jobs == 2
    assert settings.max_outstanding_jobs == 8
    assert settings.max_outstanding_jobs_per_subject == 2
    assert settings.max_terminal_result_bytes == 1000000
    assert settings.max_terminal_result_bytes_per_subject == 500000
    assert settings.terminal_job_ttl_seconds == 300


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"daily_subject_job_limit": 0}, "positive"),
        (
            {"max_active_jobs": 5, "max_outstanding_jobs": 4},
            "at least max_active_jobs",
        ),
        ({"max_outstanding_jobs_per_subject": 13}, "between 1"),
        (
            {
                "max_terminal_result_bytes": 10,
                "max_terminal_result_bytes_per_subject": 11,
            },
            "between 1",
        ),
        ({"terminal_job_ttl_seconds": 0}, "positive"),
    ],
)
def test_access_capacity_configuration_rejects_unsafe_bounds(overrides, message):
    with pytest.raises(ValueError, match=message):
        Settings(**overrides)
