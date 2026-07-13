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


def test_superscript_n_and_sentence_punctuation_are_normalized():
    assert normalize_and_validate_mms_poj(
        "Tâi-gí,\nthiⁿ-khì。 (hó͘!)", provider="test"
    ) == "tâi-gí thinn-khì hó͘"


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("hit’ê", "hit'ê"),
        ("hit‘ê", "hit'ê"),
        ("hitʼê", "hit'ê"),
        ("sin‑bûn", "sin-bûn"),
        ("sin–bûn", "sin-bûn"),
        ("sin—bûn", "sin-bûn"),
    ],
)
def test_common_apostrophe_and_hyphen_variants_are_normalized(
    variant, expected
):
    assert normalize_and_validate_mms_poj(variant, provider="test") == expected


@pytest.mark.parametrize(
    "invalid",
    [
        "這是中文",
        "sin-bun 2026",
        "bad",
        "tâi-gír",
        "tâi|gí",
        "tâi+gí",
    ],
)
def test_invalid_characters_never_pass_mms_vocabulary_gate(invalid):
    with pytest.raises(ProviderError, match="incompatible"):
        normalize_and_validate_mms_poj(invalid, provider="test")
