from pathlib import Path
from stat import S_IXUSR

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_PATH = PROJECT_ROOT / "render.yaml"
START_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "start-production.sh"


def load_service() -> dict:
    blueprint = yaml.safe_load(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    assert set(blueprint) == {"services"}
    assert len(blueprint["services"]) == 1
    return blueprint["services"][0]


def env_vars_by_key(service: dict) -> dict[str, dict]:
    return {item["key"]: item for item in service["envVars"]}


def test_render_blueprint_defines_one_gated_free_web_service() -> None:
    service = load_service()

    assert service["type"] == "web"
    assert service["name"] == "ai-learning-promptbench"
    assert service["runtime"] == "python"
    assert service["plan"] == "free"
    assert service["region"] == "oregon"
    assert service["autoDeployTrigger"] == "checksPass"
    assert service["healthCheckPath"] == "/health/ready"
    assert service["maxShutdownDelaySeconds"] == 30
    assert service["buildCommand"] == (
        "uv sync --locked --no-dev --no-editable"
    )
    assert service["startCommand"] == "./scripts/start-production.sh"
    assert "previews" not in service


def test_render_blueprint_prompts_for_secrets_without_values() -> None:
    service = load_service()
    env_vars = env_vars_by_key(service)

    assert env_vars["OPENAI_API_KEY"] == {
        "key": "OPENAI_API_KEY",
        "sync": False,
    }
    assert env_vars["ANTHROPIC_API_KEY"] == {
        "key": "ANTHROPIC_API_KEY",
        "sync": False,
    }
    assert "value" not in env_vars["OPENAI_API_KEY"]
    assert "value" not in env_vars["ANTHROPIC_API_KEY"]


def test_render_blueprint_keeps_learning_cost_limits() -> None:
    service = load_service()
    env_vars = env_vars_by_key(service)

    assert env_vars["APP_ENV"]["value"] == "production"
    assert env_vars["UV_VERSION"]["value"] == "0.12.3"
    assert env_vars["LLM_TIMEOUT_SECONDS"]["value"] == "30"
    assert env_vars["LLM_MAX_OUTPUT_TOKENS"]["value"] == "64"
    assert env_vars["MAX_MODEL_COST_USD_PER_REQUEST"]["value"] == "0.05"


def test_production_start_script_is_executable_and_binds_render_port() -> None:
    script = START_SCRIPT_PATH.read_text(encoding="utf-8")
    mode = START_SCRIPT_PATH.stat().st_mode

    assert mode & S_IXUSR
    assert "set -eu" in script
    assert 'PORT="${PORT:-10000}"' in script
    assert "uv run --no-sync uvicorn" in script
    assert "--app-dir src" in script
    assert "--host 0.0.0.0" in script
    assert '--port "$PORT"' in script
