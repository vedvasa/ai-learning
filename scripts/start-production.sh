#!/usr/bin/env sh
set -eu

# Render provides PORT. The default keeps the same command useful for a local
# production-style smoke test without duplicating platform configuration.
PORT="${PORT:-10000}"

exec uv run --no-sync uvicorn \
  --app-dir src \
  app.main:app \
  --host 0.0.0.0 \
  --port "$PORT"
