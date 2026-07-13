"""Validation for the exact ``facebook/mms-tts-nan`` tokenizer alphabet."""

from __future__ import annotations

import unicodedata

from .base import ProviderError


# Copied from the published checkpoint's vocab.json, excluding `|`, which is
# the tokenizer blank/padding token rather than a character providers may emit.
MMS_NAN_ASCII_LETTERS = frozenset("abceghijklmnopstu")
MMS_NAN_PRECOMPOSED_TONES = frozenset(
    "àáâèéêìíîòóôùúûāēīńōūǹḿ"
)
MMS_NAN_COMBINING_MARKS = frozenset("\u0302\u0304\u030d\u0358")
MMS_NAN_SEPARATORS = frozenset(" '-")
MMS_NAN_ALLOWED_CHARACTERS = frozenset().union(
    MMS_NAN_ASCII_LETTERS,
    MMS_NAN_PRECOMPOSED_TONES,
    MMS_NAN_COMBINING_MARKS,
    MMS_NAN_SEPARATORS,
)


def normalize_and_validate_mms_poj(value: str, *, provider: str) -> str:
    """Return normalized POJ or fail before unsupported text reaches VITS.

    NFC composes ordinary vowel tone sequences when Unicode has a precomposed
    form. Lowercasing turns otherwise valid capitalized POJ into the checkpoint's
    lowercase vocabulary. No transliteration or source-text fallback occurs.
    """

    # Providers commonly wrap or line-break otherwise valid POJ. Collapse all
    # Unicode whitespace to the tokenizer's one supported ASCII space without
    # admitting any additional character into the final alphabet.
    normalized = unicodedata.normalize("NFC", " ".join(value.split())).lower()
    if not normalized:
        raise ProviderError(f"{provider} returned an empty translation")
    unsupported = sorted(set(normalized) - MMS_NAN_ALLOWED_CHARACTERS)
    if unsupported:
        rendered = ", ".join(
            f"U+{ord(character):04X} {unicodedata.name(character, 'UNKNOWN')}"
            for character in unsupported[:8]
        )
        raise ProviderError(
            f"{provider} translation is incompatible with the MMS Min Nan POJ "
            f"vocabulary (unsupported: {rendered})"
        )
    return normalized
