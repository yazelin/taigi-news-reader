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

# Formatting variants produced by otherwise valid translation models. Keep
# this mapping deliberately narrow: it fixes typography, not language content.
MMS_NAN_FORMAT_TRANSLATION = str.maketrans(
    {
        "\u207f": "nn",  # superscript Latin small letter n
        "\u2018": "'",  # left single quotation mark
        "\u2019": "'",  # right single quotation mark
        "\u201b": "'",  # single high-reversed-9 quotation mark
        "\u02bc": "'",  # modifier letter apostrophe
        "\uff07": "'",  # fullwidth apostrophe
        "\u2010": "-",  # hyphen
        "\u2011": "-",  # non-breaking hyphen
        "\u2012": "-",  # figure dash
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2015": "-",  # horizontal bar
        "\ufe58": "-",  # small em dash
        "\ufe63": "-",  # small hyphen-minus
        "\uff0d": "-",  # fullwidth hyphen-minus
    }
)


def normalize_and_validate_mms_poj(value: str, *, provider: str) -> str:
    """Return normalized POJ or fail before unsupported text reaches VITS.

    Common typography is made deterministic before validation. NFC composes
    ordinary vowel tone sequences when Unicode has a precomposed form, and
    lowercasing turns otherwise valid capitalized POJ into the checkpoint's
    lowercase vocabulary. No transliteration or source-text fallback occurs.
    """

    formatted = value.translate(MMS_NAN_FORMAT_TRANSLATION)
    # Sentence punctuation carries no pronunciation. Replace unsupported
    # Unicode punctuation with boundaries, while leaving letters, digits,
    # symbols, and other unsupported content intact so validation still fails.
    formatted = "".join(
        " "
        if character not in MMS_NAN_ALLOWED_CHARACTERS
        and unicodedata.category(character).startswith("P")
        else character
        for character in formatted
    )
    # Providers commonly wrap or line-break otherwise valid POJ. Collapse all
    # Unicode whitespace to the tokenizer's one supported ASCII space without
    # admitting any additional character into the final alphabet.
    normalized = unicodedata.normalize("NFC", " ".join(formatted.split())).lower()
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
