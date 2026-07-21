"""HTTP API models."""

from datetime import date, datetime
import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


SourceLanguage = Literal["zh-TW", "nan-Latn-TW"]

_LATIN_LETTER_RE = re.compile(r"[A-Za-z\u00c0-\u024f\u1e00-\u1eff]")
_NON_ROMANIZED_SCRIPT_RE = re.compile(
    r"[\u2e80-\u2fff\u3040-\u30ff\u3100-\u312f\u31a0-\u31bf"
    r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]"
)


class SynthesizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5_000)
    source_language: SourceLanguage
    target_language: Literal["nan-TW"]
    rate: float = Field(ge=0.5, le=1.5)

    @field_validator("text")
    @classmethod
    def strip_and_reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value

    @model_validator(mode="after")
    def validate_declared_input_script(self) -> "SynthesizeRequest":
        if self.source_language != "nan-Latn-TW":
            return self
        if _NON_ROMANIZED_SCRIPT_RE.search(self.text):
            raise ValueError(
                "nan-Latn-TW input must already be Taiwanese Hokkien romanization, not Han text"
            )
        if not _LATIN_LETTER_RE.search(self.text):
            raise ValueError(
                "nan-Latn-TW input must contain at least one Latin-script letter"
            )
        return self


class SynthesizeResponse(BaseModel):
    taigi_text: str
    audio_base64: str
    mime_type: Literal["audio/wav"]
    provider: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["concrete", "mock"]
    translator: str
    synthesizer: str
    source_languages: tuple[SourceLanguage, ...] = (
        "zh-TW",
        "nan-Latn-TW",
    )
    target_languages: tuple[Literal["nan-TW"], ...] = ("nan-TW",)


class QuotaCounts(BaseModel):
    subject_jobs: int = Field(ge=0)
    subject_characters: int = Field(ge=0)
    global_jobs: int = Field(ge=0)
    global_characters: int = Field(ge=0)


class AccessResponse(BaseModel):
    authentication_required: bool
    subject: str | None = None
    utc_date: date | None = None
    resets_at: datetime | None = None
    limits: QuotaCounts | None = None
    used: QuotaCounts | None = None
    remaining: QuotaCounts | None = None


class SynthesisJobAccepted(BaseModel):
    job_id: str
    status: Literal["pending"] = "pending"


class SynthesisJobPending(BaseModel):
    job_id: str
    status: Literal["pending"] = "pending"


class SynthesisJobCompleted(BaseModel):
    job_id: str
    status: Literal["completed"] = "completed"
    result: SynthesizeResponse


class SynthesisJobFailed(BaseModel):
    job_id: str
    status: Literal["failed"] = "failed"
    error: str


SynthesisJobResponse = (
    SynthesisJobPending | SynthesisJobCompleted | SynthesisJobFailed
)
