import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.generate import router as generate_router
from app.api.stream import router as stream_router
from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handling
from app.providers.base import ProviderRegistry
from app.providers.registry import build_provider_registry
from app.schemas.generation import MAX_PROMPT_CHARACTERS

APP_DIRECTORY = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=APP_DIRECTORY / "templates")


def create_app(
    settings: Settings | None = None,
    provider_registry: ProviderRegistry | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description=(
            "A production-learning playground for comparing direct model providers."
        ),
    )

    logging.getLogger("app").setLevel(app_settings.log_level)
    app.state.provider_registry = (
        provider_registry
        if provider_registry is not None
        else build_provider_registry(app_settings)
    )

    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: app_settings

    register_error_handling(app)
    app.include_router(health_router)
    app.include_router(generate_router)
    app.include_router(stream_router)
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
            },
        )

    return app


app = create_app()
