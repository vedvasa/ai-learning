import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


def make_settings(
    *,
    openai_api_key: str | None = "test-openai-key",
    anthropic_api_key: str | None = "test-anthropic-key",
) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        app_version="0.1.0-test",
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
    )


def test_liveness_reports_process_identity() -> None:
    app = create_app(make_settings())

    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "PromptBench",
        "version": "0.1.0-test",
    }


def test_readiness_succeeds_without_provider_calls() -> None:
    app = create_app(make_settings())

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {
            "openai_api_key": True,
            "anthropic_api_key": True,
        },
    }


def test_readiness_fails_when_required_key_is_missing() -> None:
    app = create_app(make_settings(anthropic_api_key=None))

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "openai_api_key": True,
            "anthropic_api_key": False,
        },
    }


def test_home_page_and_static_asset_do_not_expose_secrets() -> None:
    app = create_app(
        make_settings(
            openai_api_key="private-openai-value",
            anthropic_api_key="private-anthropic-value",
        )
    )

    with TestClient(app) as client:
        page = client.get("/")
        stylesheet = client.get("/static/styles.css")

    assert page.status_code == 200
    assert "PromptBench" in page.text
    assert "FastAPI foundation online" in page.text
    assert "private-openai-value" not in page.text
    assert "private-anthropic-value" not in page.text
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")


def test_settings_reject_nonpositive_limits() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            llm_timeout_seconds=0,
            llm_max_output_tokens=0,
        )
