from pathlib import Path
from stat import S_IXUSR

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE_PATH = PROJECT_ROOT / "Dockerfile"
DOCKERIGNORE_PATH = PROJECT_ROOT / ".dockerignore"
CONTAINER_START_PATH = PROJECT_ROOT / "scripts" / "start-container.sh"
CONTAINER_SMOKE_PATH = PROJECT_ROOT / "scripts" / "smoke-container.sh"
CI_PATH = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
PYTHON_VERSION_PATH = PROJECT_ROOT / ".python-version"


def test_dockerfile_uses_pinned_multistage_nonroot_runtime() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    pinned_frontend = (
        "# syntax=docker/dockerfile:1.7@sha256:"
        "a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e"
    )
    pinned_python = (
        "python:3.14.7-slim-bookworm@sha256:"
        "23c59390fc717bf09f9336908199a0ae75d9c4264bf296123f94ad772fea3b52"
    )
    pinned_uv = (
        "ghcr.io/astral-sh/uv:0.12.3@sha256:"
        "2d890623d310b57771ce840f0da5eed5fc6d657da05ffaa45d82797b53fa3abc"
    )

    assert dockerfile.startswith(pinned_frontend)
    assert f"FROM {pinned_python} AS builder" in dockerfile
    assert f"FROM {pinned_python} AS runtime" in dockerfile
    assert f"COPY --from={pinned_uv} /uv /uvx /bin/" in dockerfile
    assert dockerfile.count("FROM ") == 2
    assert "USER 10001:10001" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert 'ENTRYPOINT ["/app/scripts/start-container.sh"]' in dockerfile
    assert "HEALTHCHECK" not in dockerfile
    assert PYTHON_VERSION_PATH.read_text(encoding="utf-8").strip() == "3.14.7"


def test_dockerfile_installs_locked_dependencies_before_project() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    dependency_sync = (
        "uv sync --locked --no-dev --no-install-project --no-editable"
    )
    project_sync = "uv sync --locked --no-dev --no-editable"

    dependency_sync_position = dockerfile.index(dependency_sync)
    source_copy_position = dockerfile.index("COPY src ./src")
    project_sync_position = dockerfile.index(
        project_sync,
        dependency_sync_position + len(dependency_sync),
    )

    assert dependency_sync_position < source_copy_position < project_sync_position
    assert "COPY ." not in dockerfile
    assert "COPY --from=builder /app/.venv /app/.venv" in dockerfile
    assert "COPY datasets ./datasets" in dockerfile


def test_container_configuration_does_not_bake_provider_secrets() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    dockerignore = DOCKERIGNORE_PATH.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY" not in dockerfile
    assert "ANTHROPIC_API_KEY" not in dockerfile
    assert dockerignore.splitlines()[0] == "**"
    assert "!src/**" in dockerignore
    assert "!datasets/**" in dockerignore
    assert "!.env" not in dockerignore
    assert "!.git" not in dockerignore


def test_container_scripts_are_executable_and_follow_runtime_contract() -> None:
    start_script = CONTAINER_START_PATH.read_text(encoding="utf-8")
    smoke_script = CONTAINER_SMOKE_PATH.read_text(encoding="utf-8")

    assert CONTAINER_START_PATH.stat().st_mode & S_IXUSR
    assert CONTAINER_SMOKE_PATH.stat().st_mode & S_IXUSR
    assert 'PORT="${PORT:-8080}"' in start_script
    assert "--host 0.0.0.0" in start_script
    assert '--port "$PORT"' in start_script
    assert "exec uvicorn" in start_script
    assert "triage-batch \"$IMAGE\" --validate-only" in smoke_script
    assert "rag-evaluation \"$IMAGE\" --validate-only" in smoke_script
    assert 'fetch(\"/api/answer\"' in smoke_script
    assert "/health/live" in smoke_script
    assert "/health/ready" in smoke_script
    assert '"/api/answer"' in smoke_script
    assert "Container must not run as root" in smoke_script
    assert "test ! -e /app/src" in smoke_script
    assert "test ! -w /app/.venv" in smoke_script
    assert "! command -v uv" in smoke_script
    assert "--env PORT=invalid" in smoke_script
    assert "CONTAINER_PORT=8091" in smoke_script
    assert '--env "PORT=$CONTAINER_PORT"' in smoke_script


def test_ci_builds_and_smoke_tests_without_paid_calls() -> None:
    workflow = CI_PATH.read_text(encoding="utf-8")

    assert "docker build --tag ai-learning:ci ." in workflow
    assert "sh scripts/smoke-container.sh ai-learning:ci" in workflow
    assert "--allow-paid-calls" not in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "ANTHROPIC_API_KEY" not in workflow
