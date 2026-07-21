"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask
from starlette.types import ASGIApp, Receive, Scope, Send

from .access import (
    DailyQuotaStore,
    OPEN_ACCESS_SUBJECT,
    QuotaExceededError,
    QuotaSnapshot,
    TokenAuthenticator,
)
from .config import Settings
from .jobs import JobCapacityError, JobManager, UNEXPECTED_JOB_ERROR
from .models import (
    AccessResponse,
    HealthResponse,
    QuotaCounts,
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
    EdgeTtsSynthesizer,
    MmsTtsSynthesizer,
    MockMandarinTtsSynthesizer,
    MockTranslator,
    MockTtsSynthesizer,
    OllamaTranslator,
    OpenAICompatibleTranslator,
    ProviderError,
    RemoteTtsSynthesizer,
)
from .service import SynthesisService


class RequestSecurityMiddleware:
    """Pure-ASGI identity/auth checks that do not buffer response bodies."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        authenticator: TokenAuthenticator | None,
    ) -> None:
        self.app = app
        self.settings = settings
        self.authenticator = authenticator

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/v1/"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if self.settings.require_allowed_origin:
            origin = request.headers.get("origin")
            extension_id = request.headers.get("x-taigi-extension-id", "")
            if not self.settings.extension_request_is_allowed(extension_id, origin):
                response = JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": "request extension identity is not allowed"
                    },
                )
                await response(scope, receive, send)
                return

        if request.method != "OPTIONS":
            subject = OPEN_ACCESS_SUBJECT
            if self.authenticator is not None:
                subject = self.authenticator.authenticate(
                    request.headers.get("authorization")
                )
                if subject is None:
                    response = JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "access credential is not accepted"},
                        headers={
                            "WWW-Authenticate": 'Bearer realm="taigi-news-reader"',
                            "Cache-Control": "no-store",
                        },
                    )
                    await response(scope, receive, send)
                    return
            scope.setdefault("state", {})["access_subject"] = subject
        await self.app(scope, receive, send)


class FinalizingJSONResponse(JSONResponse):
    """Run a response BackgroundTask after send success or transport failure."""

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        background = self.background
        self.background = None
        try:
            await super().__call__(scope, receive, send)
        finally:
            if background is not None:
                await background()


def build_service(settings: Settings) -> SynthesisService:
    if settings.provider_mode == "mock":
        return SynthesisService(
            MockTranslator(),
            MockTtsSynthesizer(),
            (
                MockMandarinTtsSynthesizer()
                if settings.mandarin_tts_provider == "edge"
                else None
            ),
        )
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
            max_audio_bytes=settings.max_audio_bytes,
        )
    else:
        synthesizer = RemoteTtsSynthesizer(
            url=settings.remote_tts_url or "",
            api_key=settings.remote_tts_api_key,
            timeout_seconds=settings.remote_tts_timeout_seconds,
            max_audio_bytes=settings.max_audio_bytes,
        )
    mandarin_synthesizer = (
        EdgeTtsSynthesizer(
            voice=settings.edge_tts_voice,
            timeout_seconds=settings.edge_tts_timeout_seconds,
            max_audio_bytes=settings.max_audio_bytes,
        )
        if settings.mandarin_tts_provider == "edge"
        else None
    )
    return SynthesisService(translator, synthesizer, mandarin_synthesizer)


def create_app(
    settings: Settings | None = None,
    service: SynthesisService | None = None,
    job_manager: JobManager | None = None,
    quota_store: DailyQuotaStore | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    service = service or build_service(settings)
    job_manager = job_manager or JobManager(
        service,
        max_active_jobs=settings.max_active_jobs,
        max_outstanding_jobs=settings.max_outstanding_jobs,
        max_outstanding_jobs_per_owner=(
            settings.max_outstanding_jobs_per_subject
        ),
        max_terminal_bytes=settings.max_terminal_result_bytes,
        max_terminal_bytes_per_owner=(
            settings.max_terminal_result_bytes_per_subject
        ),
        terminal_ttl_seconds=settings.terminal_job_ttl_seconds,
    )
    authenticator = (
        TokenAuthenticator(settings.access_token_hashes)
        if settings.require_access_token
        else None
    )
    if (
        settings.require_access_token or settings.enforce_open_access_quota
    ) and quota_store is None:
        quota_store = DailyQuotaStore.from_settings(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            try:
                await job_manager.shutdown()
            finally:
                try:
                    await service.aclose()
                finally:
                    if quota_store is not None:
                        quota_store.close()

    application = FastAPI(
        title="Taigi News Reader API",
        version="0.1.2",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.synthesis_service = service
    application.state.job_manager = job_manager
    application.state.quota_store = quota_store
    application.state.token_authenticator = authenticator

    application.add_middleware(
        RequestSecurityMiddleware,
        settings=settings,
        authenticator=authenticator,
    )

    # Register CORS after security middleware so it is the outermost layer.
    # This lets Chrome read generic 401/403 responses while CORS itself handles
    # browser preflights before bearer authentication is possible.
    application.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.cors_origin_regex(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Taigi-Extension-Id",
        ],
        expose_headers=[
            "Retry-After",
            "X-RateLimit-Reset",
            "X-RateLimit-Remaining",
            "X-RateLimit-Scope",
        ],
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
            mandarin_synthesizer=(
                service.mandarin_synthesizer.name
                if service.mandarin_synthesizer is not None
                else None
            ),
            source_languages=service.source_languages,
            target_languages=service.target_languages,
            capabilities=service.capabilities,
        )

    @application.get("/v1/access", response_model=AccessResponse)
    async def access_status(http_request: Request) -> AccessResponse:
        if quota_store is None:
            return AccessResponse(authentication_required=False)
        snapshot = quota_store.status(access_subject(http_request))
        return access_response(
            snapshot,
            authentication_required=settings.require_access_token,
        )

    if settings.allow_direct_synthesis:

        @application.post("/v1/synthesize", response_model=SynthesizeResponse)
        async def synthesize(
            request: SynthesizeRequest,
            http_request: Request,
        ) -> SynthesizeResponse:
            enforce_text_limit(request)
            if quota_store is not None:
                reserve_quota(
                    quota_store,
                    access_subject(http_request),
                    len(request.text),
                )
            try:
                if (
                    request.source_language == "zh-TW"
                    and request.target_language == "nan-TW"
                ):
                    return await service.synthesize(request.text, request.rate)
                return await service.synthesize(
                    request.text,
                    request.rate,
                    source_language=request.source_language,
                    target_language=request.target_language,
                )
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
        http_request: Request,
    ) -> SynthesisJobAccepted:
        enforce_text_limit(request)
        owner = access_subject(http_request)
        try:
            job_id = await job_manager.create(
                request.text,
                request.rate,
                source_language=request.source_language,
                target_language=request.target_language,
                owner=owner,
                admit=(
                    lambda: reserve_quota(
                        quota_store,
                        owner,
                        len(request.text),
                    )
                    if quota_store is not None
                    else None
                ),
            )
        except JobCapacityError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
                headers={
                    "Retry-After": "5",
                    "X-RateLimit-Scope": "active_jobs",
                },
            ) from exc
        return SynthesisJobAccepted(job_id=job_id)

    @application.get(
        "/v1/synthesis-jobs/{job_id}",
        response_model=SynthesisJobResponse,
    )
    async def get_synthesis_job(
        job_id: str,
        http_request: Request,
    ) -> SynthesisJobResponse | Response:
        owner = access_subject(http_request)
        job = await job_manager.get(
            job_id,
            owner=owner,
            consume_terminal=True,
        )
        if job is None:
            raise job_not_found()
        if job.status == "pending":
            return SynthesisJobPending(job_id=job.job_id)
        if job.status == "completed" and job.result is not None:
            terminal: SynthesisJobResponse = SynthesisJobCompleted(
                job_id=job.job_id,
                result=job.result,
            )
        else:
            terminal = SynthesisJobFailed(
                job_id=job.job_id,
                error=job.error or UNEXPECTED_JOB_ERROR,
            )
        assert job.delivery_lease is not None
        return FinalizingJSONResponse(
            content=terminal.model_dump(mode="json"),
            background=BackgroundTask(
                job_manager.release_delivery,
                job.job_id,
                job.delivery_lease,
                owner=owner,
            ),
        )

    @application.delete(
        "/v1/synthesis-jobs/{job_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_synthesis_job(job_id: str, http_request: Request) -> Response:
        if not await job_manager.delete(
            job_id,
            owner=access_subject(http_request),
        ):
            raise job_not_found()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    def enforce_text_limit(request: SynthesizeRequest) -> None:
        if len(request.text) > settings.max_text_chars:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"text exceeds the configured {settings.max_text_chars}-character limit",
            )

    def access_subject(request: Request) -> str:
        return getattr(request.state, "access_subject", OPEN_ACCESS_SUBJECT)

    def reserve_quota(
        store: DailyQuotaStore,
        subject: str,
        characters: int,
    ) -> None:
        try:
            store.reserve(subject, characters)
        except QuotaExceededError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="daily synthesis quota exceeded",
                headers=exc.response_headers(),
            ) from exc

    def access_response(
        snapshot: QuotaSnapshot,
        *,
        authentication_required: bool,
    ) -> AccessResponse:
        limits = QuotaCounts(
            subject_jobs=snapshot.subject_job_limit,
            subject_characters=snapshot.subject_character_limit,
            global_jobs=snapshot.global_job_limit,
            global_characters=snapshot.global_character_limit,
        )
        used = QuotaCounts(
            subject_jobs=snapshot.subject_jobs,
            subject_characters=snapshot.subject_characters,
            global_jobs=snapshot.global_jobs,
            global_characters=snapshot.global_characters,
        )
        remaining = QuotaCounts(
            subject_jobs=max(0, limits.subject_jobs - used.subject_jobs),
            subject_characters=max(
                0,
                limits.subject_characters - used.subject_characters,
            ),
            global_jobs=max(0, limits.global_jobs - used.global_jobs),
            global_characters=max(
                0,
                limits.global_characters - used.global_characters,
            ),
        )
        return AccessResponse(
            authentication_required=authentication_required,
            subject=snapshot.subject,
            utc_date=snapshot.utc_date,
            resets_at=snapshot.resets_at,
            limits=limits,
            used=used,
            remaining=remaining,
        )

    def job_not_found() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="synthesis job not found",
        )

    return application


app = create_app()
