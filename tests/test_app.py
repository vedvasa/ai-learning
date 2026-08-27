import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


def make_settings(
    *,
    openai_api_key: str | None = "test-openai-key",
    anthropic_api_key: str | None = "test-anthropic-key",
    database_url: str | None = None,
    rag_database_required: bool = False,
) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        app_version="0.1.0-test",
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
        database_url=database_url,
        rag_database_required=rag_database_required,
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


def test_readiness_requires_database_only_when_release_opts_in() -> None:
    app = create_app(
        make_settings(
            database_url="postgresql://test:test@db.example.com/postgres",
            rag_database_required=True,
        )
    )

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {
        "openai_api_key": True,
        "anthropic_api_key": True,
        "database_url": True,
    }


def test_readiness_fails_when_opted_in_database_is_missing() -> None:
    app = create_app(make_settings(rag_database_required=True))

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database_url"] is False


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
    assert "Citation Q&amp;A workspace" in page.text
    assert 'id="answer-form"' in page.text
    assert 'id="answer-provider"' in page.text
    assert 'id="answer-model"' in page.text
    assert 'id="answer-top-k"' in page.text
    assert 'name="question"' in page.text
    assert re.search(
        r'id="answer-question"\s+name="question"\s+maxlength="2000"',
        page.text,
    )
    assert 'id="answer-sources"' in page.text
    assert 'id="answer-metric-conversation-id"' in page.text
    assert "Generation is capped at 512 tokens" in " ".join(page.text.split())
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
    assert 'fetch("/api/answer"' in script.text
    assert "answerSources.replaceChildren()" in script.text
    assert "innerHTML" not in script.text
    assert "AbortController" in script.text


def test_home_page_uses_same_origin_static_asset_urls() -> None:
    app = create_app(make_settings())

    with TestClient(app) as client:
        page = client.get("/")

    assert page.status_code == 200
    assert 'href="/static/styles.css"' in page.text
    assert 'src="/static/app.js"' in page.text
    assert 'href="http://testserver/static/' not in page.text
    assert 'src="http://testserver/static/' not in page.text


def test_settings_reject_nonpositive_limits() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            llm_timeout_seconds=0,
            llm_max_output_tokens=0,
            triage_max_output_tokens=0,
            rag_answer_max_output_tokens=0,
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


@pytest.mark.parametrize("capacity", [0, 10_001])
def test_settings_rejects_unsafe_usage_recorder_capacity(capacity: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, usage_recorder_capacity=capacity)


@pytest.mark.parametrize(
    "override",
    [
        {"rag_tenant_id": ""},
        {"rag_tenant_id": "tenant with spaces"},
        {"rag_retrieval_min_similarity": -1.01},
        {"rag_retrieval_min_similarity": 1.01},
    ],
)
def test_settings_rejects_unsafe_retrieval_bounds(override: dict) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **override)
