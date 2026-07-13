"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .jobs import JobCapacityError, JobManager, UNEXPECTED_JOB_ERROR
from .models import (
    HealthResponse,
    SynthesisJobAccepted,
    SynthesisJobCompleted,
    SynthesisJobFailed,
    SynthesisJobPending,
    SynthesisJobResponse,
    SynthesizeRequest,
    SynthesizeResponse,
)
from .providers import (
    GeminiTranslator,
    MmsTtsSynthesizer,
    MockTranslator,
    MockTtsSynthesizer,
    OllamaTranslator,
    OpenAICompatibleTranslator,
    ProviderError,
    RemoteTtsSynthesizer,
)
from .service import SynthesisService


def build_service(settings: Settings) -> SynthesisService:
    if settings.provider_mode == "mock":
        return SynthesisService(MockTranslator(), MockTtsSynthesizer())
    if settings.translator_provider == "ollama":
        translator = OllamaTranslator(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            max_output_chars=settings.max_translated_chars,
        )
    elif settings.translator_provider == "openai_compatible":
        # These values are guaranteed by Settings validation.
        translator = OpenAICompatibleTranslator(
            base_url=settings.openai_base_url or "",
            api_key=settings.openai_api_key or "",
            model=settings.openai_model or "",
            timeout_seconds=settings.openai_timeout_seconds,
            max_output_chars=settings.max_translated_chars,
        )
    else:
        translator = GeminiTranslator(
            base_url=settings.gemini_base_url,
            api_key=settings.gemini_api_key or "",
            model=settings.gemini_model,
            timeout_seconds=settings.gemini_timeout_seconds,
            max_output_chars=settings.max_translated_chars,
        )
    if settings.tts_provider == "mms":
        synthesizer = MmsTtsSynthesizer(
            model_name=settings.mms_model,
            device=settings.mms_device,
            timeout_seconds=settings.mms_timeout_seconds,
        )
    else:
        synthesizer = RemoteTtsSynthesizer(
            url=settings.remote_tts_url or "",
            api_key=settings.remote_tts_api_key,
            timeout_seconds=settings.remote_tts_timeout_seconds,
            max_audio_bytes=settings.max_audio_bytes,
        )
    return SynthesisService(translator, synthesizer)


def create_app(
    settings: Settings | None = None,
    service: SynthesisService | None = None,
    job_manager: JobManager | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    service = service or build_service(settings)
    job_manager = job_manager or JobManager(service)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            try:
                await job_manager.shutdown()
            finally:
                await service.aclose()

    application = FastAPI(
        title="Taigi News Reader API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.synthesis_service = service
    application.state.job_manager = job_manager
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.cors_origin_regex(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        # Health is intentionally readiness-light: it does not download the MMS
        # model or generate billable/expensive output.
        return HealthResponse(
            mode=settings.provider_mode,
            translator=service.translator.name,
            synthesizer=service.synthesizer.name,
        )

    @application.post("/v1/synthesize", response_model=SynthesizeResponse)
    async def synthesize(request: SynthesizeRequest) -> SynthesizeResponse:
        enforce_text_limit(request)
        try:
            return await service.synthesize(request.text, request.rate)
        except ProviderError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

    @application.post(
        "/v1/synthesis-jobs",
        response_model=SynthesisJobAccepted,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_synthesis_job(
        request: SynthesizeRequest,
    ) -> SynthesisJobAccepted:
        enforce_text_limit(request)
        try:
            job_id = await job_manager.create(request.text, request.rate)
        except JobCapacityError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
            ) from exc
        return SynthesisJobAccepted(job_id=job_id)

    @application.get(
        "/v1/synthesis-jobs/{job_id}",
        response_model=SynthesisJobResponse,
    )
    async def get_synthesis_job(job_id: str) -> SynthesisJobResponse:
        job = await job_manager.get(job_id)
        if job is None:
            raise job_not_found()
        if job.status == "pending":
            return SynthesisJobPending(job_id=job.job_id)
        if job.status == "completed" and job.result is not None:
            return SynthesisJobCompleted(job_id=job.job_id, result=job.result)
        return SynthesisJobFailed(
            job_id=job.job_id,
            error=job.error or UNEXPECTED_JOB_ERROR,
        )

    @application.delete(
        "/v1/synthesis-jobs/{job_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_synthesis_job(job_id: str) -> Response:
        if not await job_manager.delete(job_id):
            raise job_not_found()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    def enforce_text_limit(request: SynthesizeRequest) -> None:
        if len(request.text) > settings.max_text_chars:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"text exceeds the configured {settings.max_text_chars}-character limit",
            )

    def job_not_found() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="synthesis job not found",
        )

    return application


app = create_app()
