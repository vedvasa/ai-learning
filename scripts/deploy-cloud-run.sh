#!/usr/bin/env sh
set -eu

SCRIPT_DIRECTORY="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIRECTORY/.." && pwd)"
cd "$PROJECT_ROOT"

PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-us-west1}"
REPOSITORY="${GCP_ARTIFACT_REPOSITORY:-ai-learning}"
IMAGE_NAME="${GCP_IMAGE_NAME:-ai-learning}"
SERVICE="${CLOUD_RUN_SERVICE:-ai-learning}"
OPENAI_SECRET_VERSION="${OPENAI_SECRET_VERSION:-1}"
ANTHROPIC_SECRET_VERSION="${ANTHROPIC_SECRET_VERSION:-1}"
RUNTIME_SERVICE_ACCOUNT="${CLOUD_RUN_SERVICE_ACCOUNT:-ai-learning-runtime@${PROJECT_ID}.iam.gserviceaccount.com}"

fail() {
  echo "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

validate_lowercase_identifier() {
  value="$1"
  label="$2"
  case "$value" in
    ""|*[!a-z0-9-]*|[!a-z]*)
      fail "$label must start with a lowercase letter and contain only lowercase letters, digits, and hyphens."
      ;;
  esac
}

validate_secret_version() {
  value="$1"
  label="$2"
  case "$value" in
    ""|*[!0-9]*|0)
      fail "$label must be an explicit positive integer, not latest."
      ;;
  esac
}

require_command curl
require_command gcloud
require_command git
require_command python3

validate_lowercase_identifier "$PROJECT_ID" "GCP_PROJECT_ID"
validate_lowercase_identifier "$REGION" "GCP_REGION"
validate_lowercase_identifier "$REPOSITORY" "GCP_ARTIFACT_REPOSITORY"
validate_lowercase_identifier "$IMAGE_NAME" "GCP_IMAGE_NAME"
validate_lowercase_identifier "$SERVICE" "CLOUD_RUN_SERVICE"
validate_secret_version "$OPENAI_SECRET_VERSION" "OPENAI_SECRET_VERSION"
validate_secret_version \
  "$ANTHROPIC_SECRET_VERSION" \
  "ANTHROPIC_SECRET_VERSION"

configured_project="$(gcloud config get-value project 2>/dev/null)"
if [ "$configured_project" != "$PROJECT_ID" ]; then
  fail "Active gcloud project is $configured_project; expected $PROJECT_ID."
fi

if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
  fail "Refusing to release a dirty worktree. Commit or remove local changes first."
fi

commit_sha="$(git rev-parse HEAD)"
case "$commit_sha" in
  *[!0-9a-f]*)
    fail "Expected git rev-parse HEAD to return a 40-character SHA."
    ;;
esac
if [ "${#commit_sha}" -ne 40 ]; then
  fail "Expected git rev-parse HEAD to return a 40-character SHA."
fi
short_sha="$(printf '%.12s' "$commit_sha")"
revision_suffix="git-$short_sha"
candidate_tag="git-$short_sha"

gcloud artifacts repositories describe "$REPOSITORY" \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(name)' >/dev/null

gcloud iam service-accounts describe "$RUNTIME_SERVICE_ACCOUNT" \
  --project="$PROJECT_ID" \
  --format='value(email)' >/dev/null

openai_secret_state="$(
  gcloud secrets versions describe "$OPENAI_SECRET_VERSION" \
    --secret=openai-api-key \
    --project="$PROJECT_ID" \
    --format='value(state)'
)"
anthropic_secret_state="$(
  gcloud secrets versions describe "$ANTHROPIC_SECRET_VERSION" \
    --secret=anthropic-api-key \
    --project="$PROJECT_ID" \
    --format='value(state)'
)"
if [ "$openai_secret_state" != "ENABLED" ]; then
  fail "OpenAI secret version $OPENAI_SECRET_VERSION is not enabled."
fi
if [ "$anthropic_secret_state" != "ENABLED" ]; then
  fail "Anthropic secret version $ANTHROPIC_SECRET_VERSION is not enabled."
fi

image_path="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}"
image_tag="${image_path}:${commit_sha}"

if gcloud artifacts docker images describe "$image_tag" \
  --project="$PROJECT_ID" \
  --format='value(image_summary.digest)' >/dev/null 2>&1; then
  echo "Reusing existing commit-tagged image $image_tag."
else
  echo "Building $image_tag with Cloud Build."
  gcloud builds submit . \
    --config=cloudbuild.yaml \
    --substitutions="_IMAGE_URI=$image_tag" \
    --region="$REGION" \
    --project="$PROJECT_ID"
fi

image_digest="$(
  gcloud artifacts docker images describe "$image_tag" \
    --project="$PROJECT_ID" \
    --format='value(image_summary.digest)'
)"
case "$image_digest" in
  sha256:????????????????????????????????????????????????????????????????) ;;
  *) fail "Artifact Registry did not return a valid sha256 image digest." ;;
esac
image_reference="${image_path}@${image_digest}"

previous_revision=""
if previous_service="$(
  gcloud run services describe "$SERVICE" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format=json 2>/dev/null
)"; then
  previous_revision="$(
    printf '%s' "$previous_service" | python3 -c '
import json
import sys

service = json.load(sys.stdin)
traffic = service.get("status", {}).get("traffic", [])
serving = [item for item in traffic if item.get("percent", 0) > 0]
if serving:
    print(max(serving, key=lambda item: item.get("percent", 0)).get("revisionName", ""))
'
  )"
fi

echo "Deploying $image_reference as a zero-traffic candidate."
gcloud run deploy "$SERVICE" \
  --image="$image_reference" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --revision-suffix="$revision_suffix" \
  --tag="$candidate_tag" \
  --no-traffic \
  --allow-unauthenticated \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
  --execution-environment=gen2 \
  --port=8080 \
  --cpu=1 \
  --memory=512Mi \
  --concurrency=4 \
  --timeout=60s \
  --min=0 \
  --max=1 \
  --cpu-throttling \
  --no-cpu-boost \
  --no-session-affinity \
  --ingress=all \
  --set-env-vars="APP_ENV=production,APP_VERSION=$commit_sha,LOG_LEVEL=INFO" \
  --set-secrets="OPENAI_API_KEY=openai-api-key:$OPENAI_SECRET_VERSION,ANTHROPIC_API_KEY=anthropic-api-key:$ANTHROPIC_SECRET_VERSION" \
  --startup-probe="httpGet.path=/health/ready,httpGet.port=8080,initialDelaySeconds=0,timeoutSeconds=2,periodSeconds=2,failureThreshold=30" \
  --readiness-probe="httpGet.path=/health/ready,httpGet.port=8080,timeoutSeconds=2,periodSeconds=5,failureThreshold=2,successThreshold=1" \
  --liveness-probe="httpGet.path=/health/live,httpGet.port=8080,initialDelaySeconds=0,timeoutSeconds=2,periodSeconds=10,failureThreshold=3" \
  --deploy-health-check \
  --labels="app=ai-learning,environment=learning,git-sha=$short_sha" \
  --description="AI Learning Week 2 Ticket Triage API" \
  --quiet

service_json="$(
  gcloud run services describe "$SERVICE" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format=json
)"
candidate_url="$(
  printf '%s' "$service_json" | python3 -c '
import json
import sys

tag = sys.argv[1]
service = json.load(sys.stdin)
for target in service.get("status", {}).get("traffic", []):
    if target.get("tag") == tag and target.get("url"):
        print(target["url"])
        raise SystemExit(0)
raise SystemExit(f"Cloud Run did not publish a URL for tag {tag}")
' "$candidate_tag"
)"
candidate_revision="$(
  printf '%s' "$service_json" | python3 -c '
import json
import sys

service = json.load(sys.stdin)
revision = service.get("status", {}).get("latestReadyRevisionName", "")
if not revision:
    raise SystemExit("Cloud Run did not report a ready candidate revision")
print(revision)
'
)"

sh scripts/smoke-cloud-run.sh "$candidate_url" "$commit_sha"

echo "Promoting candidate tag $candidate_tag to 100% traffic."
gcloud run services update-traffic "$SERVICE" \
  --to-tags="$candidate_tag=100" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --quiet

service_url="$(
  gcloud run services describe "$SERVICE" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format='value(status.url)'
)"
sh scripts/smoke-cloud-run.sh "$service_url" "$commit_sha"

echo "Cloud Run release completed."
echo "Service URL: $service_url"
echo "Candidate URL: $candidate_url"
echo "Revision: $candidate_revision"
echo "Image: $image_reference"
if [ -n "$previous_revision" ]; then
  echo "Rollback command: gcloud run services update-traffic $SERVICE --to-revisions=$previous_revision=100 --region=$REGION --project=$PROJECT_ID"
else
  echo "Rollback is unavailable until a second healthy revision has been promoted."
fi
