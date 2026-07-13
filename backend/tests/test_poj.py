from __future__ import annotations

import pytest

from taigi_news_reader_backend.providers import ProviderError
from taigi_news_reader_backend.providers.poj import normalize_and_validate_mms_poj


def test_valid_poj_is_normalized_to_checkpoint_lowercase_vocabulary():
    assert normalize_and_validate_mms_poj(
        " TÂI-GÍ si̍t-chāi hó͘ ", provider="test"
    ) == "tâi-gí si̍t-chāi hó͘"


def test_unicode_whitespace_collapses_to_supported_ascii_space():
    assert normalize_and_validate_mms_poj(
        "tâi-gí\n\t sin-bûn", provider="test"
    ) == "tâi-gí sin-bûn"


@pytest.mark.parametrize(
    "invalid",
    [
        "這是中文",
        "sin-bun 2026",
        "bad",
        "tâi-gí.",
        "tâi|gí",
    ],
)
def test_invalid_characters_never_pass_mms_vocabulary_gate(invalid):
    with pytest.raises(ProviderError, match="incompatible"):
        normalize_and_validate_mms_poj(invalid, provider="test")
