#!/usr/bin/env sh
set -eu

PORT="${PORT:-8080}"

case "$PORT" in
  ""|*[!0-9]*)
    echo "PORT must be an integer between 1 and 65535." >&2
    exit 1
    ;;
esac

if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "PORT must be an integer between 1 and 65535." >&2
  exit 1
fi

exec uvicorn \
  app.main:app \
  --host 0.0.0.0 \
  --port "$PORT"
