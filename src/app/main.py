import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.generate import router as generate_router
from app.api.health import router as health_router
from app.api.answering import router as answering_router
from app.api.retrieval import router as retrieval_router
from app.api.stream import router as stream_router
from app.api.triage import router as triage_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handling
from app.providers.base import ProviderRegistry
from app.providers.registry import build_provider_registry
from app.rag.embeddings import OpenAIEmbeddingClient
from app.rag.repository import PsycopgKnowledgeRepository
from app.schemas.generation import MAX_PROMPT_CHARACTERS
from app.schemas.triage import (
    MAX_TICKET_BODY_CHARACTERS,
    MAX_TICKET_ID_CHARACTERS,
    MAX_TICKET_SUBJECT_CHARACTERS,
    TicketChannel,
)
from app.services.retrieval import SemanticRetriever
from app.services.answering import GroundedAnswerService
from app.services.retry import RetryPolicy
from app.services.usage import InMemoryUsageRecorder, UsageRecorder

APP_DIRECTORY = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=APP_DIRECTORY / "templates")


def create_app(
    settings: Settings | None = None,
    provider_registry: ProviderRegistry | None = None,
    usage_recorder: UsageRecorder | None = None,
    semantic_retriever: SemanticRetriever | None = None,
    grounded_answer_service: GroundedAnswerService | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description=(
            "A production-learning support and research assistant."
        ),
    )

    logging.getLogger("app").setLevel(app_settings.log_level)
    registry = (
        provider_registry
        if provider_registry is not None
        else build_provider_registry(app_settings)
    )
    app.state.provider_registry = registry
    app.state.usage_recorder = (
        usage_recorder
        if usage_recorder is not None
        else InMemoryUsageRecorder(
            capacity=app_settings.usage_recorder_capacity,
        )
    )
    retriever = semantic_retriever or _build_retriever(
        app_settings
    )
    app.state.semantic_retriever = retriever
    app.state.grounded_answer_service = (
        grounded_answer_service
        if grounded_answer_service is not None
        else _build_grounded_answer_service(
            app_settings,
            registry=registry,
            retriever=retriever,
        )
    )

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: app_settings

    register_error_handling(app)
    app.include_router(health_router)
    app.include_router(answering_router)
    app.include_router(generate_router)
    app.include_router(stream_router)
    app.include_router(triage_router)
    app.include_router(retrieval_router)
    app.mount(
        "/static",
        StaticFiles(directory=APP_DIRECTORY / "static"),
        name="static",
    )

    @app.get(
        "/",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "app_name": app_settings.app_name,
                "app_version": app_settings.app_version,
                "providers": (
                    {
                        "value": "openai",
                        "label": "OpenAI",
                        "model": app_settings.openai_model,
                    },
                    {
                        "value": "anthropic",
                        "label": "Anthropic",
                        "model": app_settings.anthropic_model,
                    },
                ),
                "default_provider": app_settings.llm_provider,
                "max_prompt_characters": MAX_PROMPT_CHARACTERS,
                "max_output_tokens": app_settings.llm_max_output_tokens,
                "triage_max_output_tokens": (
                    app_settings.triage_max_output_tokens
                ),
                "max_ticket_id_characters": MAX_TICKET_ID_CHARACTERS,
                "max_ticket_subject_characters": (
                    MAX_TICKET_SUBJECT_CHARACTERS
                ),
                "max_ticket_body_characters": MAX_TICKET_BODY_CHARACTERS,
                "ticket_channels": tuple(channel.value for channel in TicketChannel),
            },
        )

    return app


def _build_retriever(settings: Settings) -> SemanticRetriever | None:
    if settings.database_url is None or settings.openai_api_key is None:
        return None
    return SemanticRetriever(
        repository=PsycopgKnowledgeRepository(
            settings.database_url.get_secret_value()
        ),
        embedding_client=OpenAIEmbeddingClient(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            batch_size=1,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        tenant_id=settings.rag_tenant_id,
        minimum_similarity=settings.rag_retrieval_min_similarity,
        allowed_visibilities=("public",),
    )


def _build_grounded_answer_service(
    settings: Settings,
    *,
    registry: ProviderRegistry,
    retriever: SemanticRetriever | None,
) -> GroundedAnswerService | None:
    if settings.database_url is None or retriever is None:
        return None
    return GroundedAnswerService(
        registry=registry,
        retriever=retriever,
        repository=PsycopgKnowledgeRepository(
            settings.database_url.get_secret_value()
        ),
        retry_policy=RetryPolicy.from_settings(settings),
        timeout_seconds=settings.llm_timeout_seconds,
        tenant_id=settings.rag_tenant_id,
    )


app = create_app()
