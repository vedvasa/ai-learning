#!/usr/bin/env sh
set -eu

SERVICE_URL="${1:-}"
EXPECTED_VERSION="${2:-}"
TEMP_DIRECTORY="$(mktemp -d)"

cleanup() {
  status=$?
  trap - EXIT INT TERM
  rm -rf "$TEMP_DIRECTORY"
  exit "$status"
}
trap cleanup EXIT INT TERM

case "$SERVICE_URL" in
  https://*) ;;
  *)
    echo "Usage: $0 https://cloud-run-url [expected-version]" >&2
    exit 2
    ;;
esac
SERVICE_URL="${SERVICE_URL%/}"

attempt=1
live_status=""
while [ "$attempt" -le 30 ]; do
  if live_status="$(
    curl --silent --show-error \
      --connect-timeout 5 \
      --max-time 10 \
      --output "$TEMP_DIRECTORY/live.json" \
      --write-out '%{http_code}' \
      "$SERVICE_URL/health/live"
  )" && [ "$live_status" = "200" ]; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 2
done

if [ "$live_status" != "200" ]; then
  echo "Cloud Run service did not become live within 60 seconds." >&2
  exit 1
fi

grep -q '"status":"ok"' "$TEMP_DIRECTORY/live.json"
grep -q '"service":"KnowledgeDesk"' "$TEMP_DIRECTORY/live.json"
if [ -n "$EXPECTED_VERSION" ]; then
  grep -q "\"version\":\"$EXPECTED_VERSION\"" \
    "$TEMP_DIRECTORY/live.json"
fi

ready_status="$(
  curl --silent --show-error \
    --connect-timeout 5 \
    --max-time 10 \
    --output "$TEMP_DIRECTORY/ready.json" \
    --write-out '%{http_code}' \
    "$SERVICE_URL/health/ready"
)"
if [ "$ready_status" != "200" ]; then
  echo "Cloud Run readiness check returned HTTP $ready_status." >&2
  exit 1
fi
grep -q '"status":"ready"' "$TEMP_DIRECTORY/ready.json"
grep -q '"openai_api_key":true' "$TEMP_DIRECTORY/ready.json"
grep -q '"anthropic_api_key":true' "$TEMP_DIRECTORY/ready.json"

curl --silent --show-error --fail \
  --connect-timeout 5 \
  --max-time 10 \
  "$SERVICE_URL/" \
  >"$TEMP_DIRECTORY/home.html"
grep -q 'KnowledgeDesk' "$TEMP_DIRECTORY/home.html"
grep -q 'Ticket triage' "$TEMP_DIRECTORY/home.html"

curl --silent --show-error --fail \
  --connect-timeout 5 \
  --max-time 10 \
  "$SERVICE_URL/static/app.js" \
  >"$TEMP_DIRECTORY/app.js"
grep -q 'fetch("/api/triage"' "$TEMP_DIRECTORY/app.js"

curl --silent --show-error --fail \
  --connect-timeout 5 \
  --max-time 10 \
  "$SERVICE_URL/openapi.json" \
  >"$TEMP_DIRECTORY/openapi.json"
grep -q '"/api/triage"' "$TEMP_DIRECTORY/openapi.json"

echo "Cloud Run smoke test passed for $SERVICE_URL without model calls."
