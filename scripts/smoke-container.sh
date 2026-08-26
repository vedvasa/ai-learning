#!/usr/bin/env sh
set -eu

IMAGE="${1:-ai-learning:local}"
CONTAINER_NAME="ai-learning-smoke-$$"
CONTAINER_PORT=8091
TEMP_DIRECTORY="$(mktemp -d)"
CONTAINER_STARTED=0

cleanup() {
  status=$?
  trap - EXIT INT TERM
  if [ "$status" -ne 0 ] && [ "$CONTAINER_STARTED" -eq 1 ]; then
    docker logs "$CONTAINER_NAME" >&2 || true
  fi
  if [ "$CONTAINER_STARTED" -eq 1 ]; then
    docker rm --force "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
  rm -rf "$TEMP_DIRECTORY"
  exit "$status"
}
trap cleanup EXIT INT TERM

container_uid="$(docker run --rm --entrypoint id "$IMAGE" -u)"
if [ "$container_uid" -eq 0 ]; then
  echo "Container must not run as root." >&2
  exit 1
fi

docker run --rm --entrypoint sh "$IMAGE" -c \
  'test ! -e /app/src && test ! -w /app/.venv && ! command -v uv >/dev/null'

if docker run --rm --env PORT=invalid "$IMAGE" \
  >"$TEMP_DIRECTORY/invalid-port.log" 2>&1; then
  echo "Container must reject an invalid PORT value." >&2
  exit 1
fi
grep -q 'PORT must be an integer between 1 and 65535' \
  "$TEMP_DIRECTORY/invalid-port.log"

if docker image inspect --format '{{json .Config.Env}}' "$IMAGE" \
  | grep -Eq 'OPENAI_API_KEY|ANTHROPIC_API_KEY'; then
  echo "Provider secret names must not be baked into the image." >&2
  exit 1
fi

docker run --rm --entrypoint triage-batch "$IMAGE" --validate-only

docker run \
  --detach \
  --env "PORT=$CONTAINER_PORT" \
  --name "$CONTAINER_NAME" \
  --publish "127.0.0.1::${CONTAINER_PORT}" \
  "$IMAGE" >/dev/null
CONTAINER_STARTED=1

host_port="$(docker port "$CONTAINER_NAME" "${CONTAINER_PORT}/tcp" \
  | awk -F: 'NR == 1 {print $NF}')"
if [ -z "$host_port" ]; then
  echo "Docker did not publish the injected container port." >&2
  exit 1
fi

attempt=1
live_ready=0
while [ "$attempt" -le 30 ]; do
  if curl --silent --show-error --fail \
    "http://127.0.0.1:${host_port}/health/live" \
    >"$TEMP_DIRECTORY/live.json" 2>/dev/null; then
    live_ready=1
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done

if [ "$live_ready" -ne 1 ]; then
  echo "Container did not become live within 30 seconds." >&2
  exit 1
fi

grep -q '"status":"ok"' "$TEMP_DIRECTORY/live.json"
grep -q '"service":"KnowledgeDesk"' "$TEMP_DIRECTORY/live.json"

ready_status="$(curl --silent --show-error \
  --output "$TEMP_DIRECTORY/ready.json" \
  --write-out '%{http_code}' \
  "http://127.0.0.1:${host_port}/health/ready")"
if [ "$ready_status" != "503" ]; then
  echo "Readiness without provider secrets must return HTTP 503." >&2
  exit 1
fi
grep -q '"status":"not_ready"' "$TEMP_DIRECTORY/ready.json"

curl --silent --show-error --fail \
  "http://127.0.0.1:${host_port}/" \
  >"$TEMP_DIRECTORY/home.html"
grep -q 'KnowledgeDesk' "$TEMP_DIRECTORY/home.html"

curl --silent --show-error --fail \
  "http://127.0.0.1:${host_port}/static/app.js" \
  >"$TEMP_DIRECTORY/app.js"
grep -q 'fetch("/api/triage"' "$TEMP_DIRECTORY/app.js"
grep -q 'fetch("/api/answer"' "$TEMP_DIRECTORY/app.js"

curl --silent --show-error --fail \
  "http://127.0.0.1:${host_port}/openapi.json" \
  >"$TEMP_DIRECTORY/openapi.json"
grep -q '"/api/answer"' "$TEMP_DIRECTORY/openapi.json"

echo "Container smoke test passed for $IMAGE on port $host_port."
