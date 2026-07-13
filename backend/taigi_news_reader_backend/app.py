"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .models import HealthResponse, SynthesizeRequest, SynthesizeResponse
from .providers import (
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
    else:
        # These values are guaranteed by Settings validation.
        translator = OpenAICompatibleTranslator(
            base_url=settings.openai_base_url or "",
            api_key=settings.openai_api_key or "",
            model=settings.openai_model or "",
            timeout_seconds=settings.openai_timeout_seconds,
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
) -> FastAPI:
    settings = settings or Settings.from_env()
    service = service or build_service(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await service.aclose()

    application = FastAPI(
        title="Taigi News Reader API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.synthesis_service = service
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.cors_origin_regex(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
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
        if len(request.text) > settings.max_text_chars:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"text exceeds the configured {settings.max_text_chars}-character limit",
            )
        try:
            return await service.synthesize(request.text, request.rate)
        except ProviderError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

    return application


app = create_app()
