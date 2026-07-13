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
