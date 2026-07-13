from __future__ import annotations

import re

import pytest

from taigi_news_reader_backend.config import Settings


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
