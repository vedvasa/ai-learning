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
        "service": "KnowledgeDesk",
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
        script = client.get("/static/app.js")

    assert page.status_code == 200
    assert "KnowledgeDesk" in page.text
    assert "Structured triage online" in page.text
    assert 'id="triage-form"' in page.text
    assert 'id="triage-metric-attempt-count"' in page.text
    assert 'name="ticket_id"' in page.text
    assert 'name="subject"' in page.text
    assert 'name="channel"' in page.text
    assert 'name="body"' in page.text
    assert 'id="generation-form"' in page.text
    assert 'id="cancel-button"' in page.text
    assert 'name="prompt"' in page.text
    assert "Output is capped at 64 tokens" in " ".join(page.text.split())
    assert "disabled" not in page.text
    assert "private-openai-value" not in page.text
    assert "private-anthropic-value" not in page.text
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("text/javascript")
    assert "private-openai-value" not in script.text
    assert "private-anthropic-value" not in script.text
    assert 'fetch("/api/stream"' in script.text
    assert 'fetch("/api/triage"' in script.text
    assert "AbortController" in script.text


def test_settings_reject_nonpositive_limits() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            llm_timeout_seconds=0,
            llm_max_output_tokens=0,
            triage_max_output_tokens=0,
        )


@pytest.mark.parametrize(
    "override",
    [
        {"llm_max_attempts": 6},
        {"llm_retry_base_delay_seconds": -0.1},
        {"llm_retry_max_delay_seconds": 61},
        {"llm_retry_jitter_ratio": 1.1},
    ],
)
def test_settings_reject_unsafe_retry_bounds(override: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **override)
