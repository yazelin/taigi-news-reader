from __future__ import annotations

import pytest


@pytest.fixture
def request_body() -> dict[str, object]:
    return {
        "text": "今天天氣晴朗。",
        "source_language": "zh-TW",
        "target_language": "nan-TW",
        "rate": 1.0,
    }

