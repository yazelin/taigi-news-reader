"""HTTP API models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SynthesizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=5_000)
    source_language: Literal["zh-TW"]
    target_language: Literal["nan-TW"]
    rate: float = Field(ge=0.5, le=1.5)

    @field_validator("text")
    @classmethod
    def strip_and_reject_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value


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
