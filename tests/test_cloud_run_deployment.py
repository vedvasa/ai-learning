from pathlib import Path
from stat import S_IXUSR

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GCLOUDIGNORE_PATH = PROJECT_ROOT / ".gcloudignore"
CLOUD_BUILD_PATH = PROJECT_ROOT / "cloudbuild.yaml"
DEPLOY_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "deploy-cloud-run.sh"
SMOKE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "smoke-cloud-run.sh"
RUNBOOK_PATH = PROJECT_ROOT / "docs" / "CLOUD_RUN_DEPLOYMENT.md"
CI_PATH = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


def test_cloud_build_upload_is_an_explicit_secret_free_whitelist() -> None:
    cloud_ignore = GCLOUDIGNORE_PATH.read_text(encoding="utf-8")

    assert cloud_ignore.splitlines()[0] == "**"
    assert "!Dockerfile" in cloud_ignore
    assert "!cloudbuild.yaml" in cloud_ignore
    assert "!src/**" in cloud_ignore
    assert "!datasets/**" in cloud_ignore
    assert "!scripts/start-container.sh" in cloud_ignore
    assert "**/__pycache__/" in cloud_ignore
    assert "**/*.py[cod]" in cloud_ignore
    assert "!.env" not in cloud_ignore
    assert "!.git" not in cloud_ignore
    assert "!tests/**" not in cloud_ignore

    docker_ignore = (PROJECT_ROOT / ".dockerignore").read_text(
        encoding="utf-8"
    )
    assert "**/__pycache__/" in docker_ignore
    assert "**/*.py[cod]" in docker_ignore


def test_cloud_build_uses_a_pinned_builder_and_offline_gate() -> None:
    cloud_build = CLOUD_BUILD_PATH.read_text(encoding="utf-8")
    pinned_builder = (
        "gcr.io/cloud-builders/docker@sha256:"
        "2e8d40d8e48dc14fab4213d5e532d74f63fd403d9e8d7f6463096a75820286c3"
    )

    assert cloud_build.count(pinned_builder) == 3
    assert "DOCKER_BUILDKIT=1" in cloud_build
    assert "${_IMAGE_URI}" in cloud_build
    assert "validate-offline-batch" in cloud_build
    assert "triage-batch" in cloud_build
    assert "rag-evaluation" in cloud_build
    assert "--validate-only" in cloud_build
    assert "images:" in cloud_build
    assert "OPENAI_API_KEY" not in cloud_build
    assert "ANTHROPIC_API_KEY" not in cloud_build
    assert "DATABASE_URL" not in cloud_build


def test_release_stages_digest_pinned_candidate_before_promotion() -> None:
    deploy = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")

    assert DEPLOY_SCRIPT_PATH.stat().st_mode & S_IXUSR
    assert 'PROJECT_ID="${GCP_PROJECT_ID:-}"' in deploy
    assert "git status --porcelain" in deploy
    assert "cloudbuild.yaml" in deploy
    assert 'image_reference="${image_path}@${image_digest}"' in deploy
    assert "--revision-suffix" in deploy
    assert "--no-traffic" in deploy
    assert "service_exists=0" in deploy
    assert "deploy_revision --no-traffic" in deploy
    assert "Cloud Run cannot create a service with --no-traffic" in deploy
    assert "--tag" in deploy
    assert "scripts/smoke-cloud-run.sh" in deploy
    assert "--to-tags" in deploy
    assert deploy.index("scripts/smoke-cloud-run.sh") < deploy.index("--to-tags")
    assert "Rollback command:" in deploy


def test_release_pins_secrets_and_bounds_runtime_cost() -> None:
    deploy = DEPLOY_SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'OPENAI_SECRET_VERSION="${OPENAI_SECRET_VERSION:-1}"' in deploy
    assert 'ANTHROPIC_SECRET_VERSION="${ANTHROPIC_SECRET_VERSION:-1}"' in deploy
    assert 'DATABASE_SECRET_VERSION="${DATABASE_SECRET_VERSION:-1}"' in deploy
    assert "must be an explicit positive integer, not latest" in deploy
    assert "openai-api-key:$OPENAI_SECRET_VERSION" in deploy
    assert "anthropic-api-key:$ANTHROPIC_SECRET_VERSION" in deploy
    assert "supabase-database-url:$DATABASE_SECRET_VERSION" in deploy
    assert "DATABASE_URL=supabase-database-url" in deploy
    assert "openai-api-key:latest" not in deploy
    assert "anthropic-api-key:latest" not in deploy
    assert "supabase-database-url:latest" not in deploy
    assert "RAG_DATABASE_REQUIRED=true" in deploy
    assert "--service-account" in deploy
    assert "--cpu-throttling" in deploy
    assert "--min=0" in deploy
    assert "--max=1" in deploy
    assert "--cpu=1" in deploy
    assert "--memory=512Mi" in deploy
    assert "--concurrency=4" in deploy
    assert "--startup-probe" in deploy
    assert "--readiness-probe" in deploy
    assert "--liveness-probe" in deploy


def test_public_smoke_is_provider_free_and_checks_deployed_contract() -> None:
    smoke = SMOKE_SCRIPT_PATH.read_text(encoding="utf-8")

    assert SMOKE_SCRIPT_PATH.stat().st_mode & S_IXUSR
    assert "/health/live" in smoke
    assert "/health/ready" in smoke
    assert "/static/styles.css" in smoke
    assert "/static/app.js" in smoke
    assert 'href="/static/styles.css"' in smoke
    assert 'src="/static/app.js"' in smoke
    assert "Static asset URLs must be root-relative" in smoke
    assert "/openapi.json" in smoke
    assert '"$SERVICE_URL/api/generate"' not in smoke
    assert '"$SERVICE_URL/api/stream"' not in smoke
    assert '"$SERVICE_URL/api/triage"' not in smoke
    assert '"$SERVICE_URL/api/answer"' not in smoke
    assert '"database_url":true' in smoke
    assert 'fetch("/api/answer"' in smoke
    assert '"/api/retrieve"' in smoke
    assert '"/api/answer"' in smoke
    assert "without model calls" in smoke


def test_ci_syntax_checks_cloud_scripts_without_deploying() -> None:
    workflow = CI_PATH.read_text(encoding="utf-8")

    assert "sh -n scripts/deploy-cloud-run.sh" in workflow
    assert "sh -n scripts/smoke-cloud-run.sh" in workflow
    assert "sh scripts/deploy-cloud-run.sh" not in workflow
    assert "GCP_PROJECT_ID" not in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "ANTHROPIC_API_KEY" not in workflow
    assert "\n          DATABASE_URL:" not in workflow


def test_runbook_documents_rollback_and_manual_cd_boundary() -> None:
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "--to-revisions=KNOWN_GOOD_REVISION=100" in runbook
    assert "Workload Identity Federation" in runbook
    assert "does not deploy it" in runbook
    assert "never enter Git" in runbook
    assert "supabase-database-url" in runbook
    assert "Transaction pooler" in runbook
    assert "DATABASE_SECRET_VERSION" in runbook
    assert "does not query Postgres" in runbook
