#!/usr/bin/env bash
# =============================================================================
# Incept — Cloud Run deploy script
#
# Usage:
#   ./deploy.sh --manifest releases/<release>.json
#   ./deploy.sh api --manifest releases/<release>.json
#   ./deploy.sh web --manifest releases/<release>.json
#
# Requires: gcloud CLI, Docker Desktop running, .env.deploy filled in.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Load .env.deploy ──────────────────────────────────────────────────────────
ENV_FILE="${SCRIPT_DIR}/.env.deploy"
[[ ! -f "${ENV_FILE}" ]] && { echo "✗ .env.deploy not found"; exit 1; }
set -a; source "${ENV_FILE}"; set +a

# Every production deployment is pinned to a reviewed, committed manifest.
TARGET="both"
RELEASE_MANIFEST="${RELEASE_MANIFEST:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    api|web|both|migrate) TARGET="$1" ;;
    --manifest)
      [[ $# -ge 2 ]] || { echo "✗ --manifest requires a path" >&2; exit 1; }
      RELEASE_MANIFEST="$2"
      shift
      ;;
    *) echo "✗ Unknown deploy argument '$1'" >&2; exit 1 ;;
  esac
  shift
done
[[ -n "${RELEASE_MANIFEST}" ]] || { echo "✗ A reviewed release manifest is required: ./deploy.sh --manifest releases/<release>.json" >&2; exit 1; }
# The release module validates profile/product parity, approval records, the
# exact Git SHA and a clean checkout before emitting shell-safe exports.
eval "$(node "${SCRIPT_DIR}/scripts/release-manifest.mjs" env "${RELEASE_MANIFEST}")"

# ── Validate required vars ────────────────────────────────────────────────────
: "${DEPLOY_SA_EMAIL:?Set DEPLOY_SA_EMAIL in .env.deploy}"
: "${GCP_PROJECT_DEPLOY:?Set GCP_PROJECT_DEPLOY in .env.deploy}"
: "${GOOGLE_CLIENT_ID:?}"
: "${CLOUD_SQL_INSTANCE_CONNECTION_NAME:?Set CLOUD_SQL_INSTANCE_CONNECTION_NAME in .env.deploy}"
: "${DATABASE_CONFIG_SECRET:?Set DATABASE_CONFIG_SECRET in .env.deploy}"
: "${DATABASE_CONFIG_SECRET_VERSION:?Set DATABASE_CONFIG_SECRET_VERSION in .env.deploy}"
: "${INCEPT_ASSET_BUCKET:?Set INCEPT_ASSET_BUCKET in .env.deploy}"

# The default release deliberately publishes only Image + AI Video. Set
# PRODUCT_RELEASE_PROFILE=full only when Video Production and Gaming Playable
# are intentionally ready to be deployed again.
PRODUCT_RELEASE_PROFILE="${PRODUCT_RELEASE_PROFILE:-image-ai-video}"
case "${PRODUCT_RELEASE_PROFILE}" in
  image-ai-video) ;;
  full)
    : "${CREATIVE_CORE_BUILD_CONTEXT:?Set CREATIVE_CORE_BUILD_CONTEXT for PRODUCT_RELEASE_PROFILE=full}"
    [[ -f "${CREATIVE_CORE_BUILD_CONTEXT}/package.json" ]] || { echo "✗ CREATIVE_CORE_BUILD_CONTEXT must point to a prepared Creative Core installation" >&2; exit 1; }
    [[ -f "${CREATIVE_CORE_BUILD_CONTEXT}/scripts/cr-agent-core.sh" ]] || { echo "✗ CREATIVE_CORE_BUILD_CONTEXT is missing scripts/cr-agent-core.sh" >&2; exit 1; }
    [[ -f "${CREATIVE_CORE_BUILD_CONTEXT}/pnpm-lock.yaml" ]] || { echo "✗ CREATIVE_CORE_BUILD_CONTEXT is missing pnpm-lock.yaml" >&2; exit 1; }
    ;;
  *) echo "✗ Unknown PRODUCT_RELEASE_PROFILE '${PRODUCT_RELEASE_PROFILE}'. Use: image-ai-video | full" >&2; exit 1 ;;
esac

# ── Derived config ────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_DEPLOY}"
REGION="${REGION:-asia-northeast1}"
REPO="incept"

API_SERVICE="incept-api"
WEB_SERVICE="incept-web"

AR_HOST="${REGION}-docker.pkg.dev"
API_IMAGE="${AR_HOST}/${PROJECT_ID}/${REPO}/api"
WEB_IMAGE="${AR_HOST}/${PROJECT_ID}/${REPO}/web"
API_IMAGE="${API_IMAGE}:${RELEASE_ID}"
WEB_IMAGE="${WEB_IMAGE}:${RELEASE_ID}"

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo -e "\n\033[1;34m▶  $*\033[0m"; }
ok()   { echo -e "\033[1;32m✓  $*\033[0m"; }
info() { echo -e "   $*"; }
err()  { echo -e "\033[1;31m✗  $*\033[0m" >&2; exit 1; }

has_value() { [[ -n "${!1:-}" ]]; }

secret_migration_requested() {
  has_value INCEPT_INTERNAL_API_KEY_SECRET || has_value INCEPT_INTERNAL_API_KEY_SECRET_VERSION || \
  has_value GOOGLE_CLIENT_SECRET_SECRET || has_value GOOGLE_CLIENT_SECRET_SECRET_VERSION || \
  has_value AUTH_SECRET_SECRET || has_value AUTH_SECRET_SECRET_VERSION
}

validate_secret_migration_config() {
  if ! secret_migration_requested; then
    return
  fi
  : "${INCEPT_INTERNAL_API_KEY_SECRET:?Set all three Secret Manager mappings, or none}"
  : "${INCEPT_INTERNAL_API_KEY_SECRET_VERSION:?Set all three Secret Manager mappings, or none}"
  : "${GOOGLE_CLIENT_SECRET_SECRET:?Set all three Secret Manager mappings, or none}"
  : "${GOOGLE_CLIENT_SECRET_SECRET_VERSION:?Set all three Secret Manager mappings, or none}"
  : "${AUTH_SECRET_SECRET:?Set all three Secret Manager mappings, or none}"
  : "${AUTH_SECRET_SECRET_VERSION:?Set all three Secret Manager mappings, or none}"
}

validate_ai_video_production_config() {
  # Cloud Run has no persistent Celery worker. Real AI Video generation must
  # dispatch durable work through a user-owned Cloud Tasks queue.
  : "${INCEPT_INTERNAL_API_KEY_SECRET:?Set INCEPT_INTERNAL_API_KEY_SECRET for AI Video task dispatch}"
  : "${INCEPT_INTERNAL_API_KEY_SECRET_VERSION:?Set INCEPT_INTERNAL_API_KEY_SECRET_VERSION for AI Video task dispatch}"
  : "${CLOUD_TASKS_LOCATION:?Set CLOUD_TASKS_LOCATION in .env.deploy}"
  : "${CLOUD_TASKS_QUEUE:?Set CLOUD_TASKS_QUEUE in .env.deploy}"
  : "${TASK_RUNNER_SERVICE_ACCOUNT_EMAIL:?Set TASK_RUNNER_SERVICE_ACCOUNT_EMAIL in .env.deploy}"
}

# ── One-time setup: Artifact Registry repo ───────────────────────────────────
ensure_ar_repo() {
  log "Checking Artifact Registry repo '${REPO}'…"
  gcloud artifacts repositories describe "${REPO}" \
    --project="${PROJECT_ID}" --location="${REGION}" &>/dev/null \
  || gcloud artifacts repositories create "${REPO}" \
       --project="${PROJECT_ID}" --location="${REGION}" \
       --repository-format=docker \
       --description="Incept container images"
  gcloud auth configure-docker "${AR_HOST}" --quiet
  ok "Artifact Registry ready (${AR_HOST}/${PROJECT_ID}/${REPO})"
}

assert_release_image_absent() {
  local image="$1"
  if gcloud artifacts docker images describe "${image}" --project="${PROJECT_ID}" &>/dev/null; then
    err "Release image already exists: ${image}. Release tags are immutable; create a new release ID."
  fi
}

ensure_ai_video_task_queue() {
  local tasks_project="${CLOUD_TASKS_PROJECT_ID:-${PROJECT_ID}}"
  local tasks_project_number
  tasks_project_number="$(gcloud projects describe "${tasks_project}" --format='value(projectNumber)')"

  log "Checking Cloud Tasks queue '${CLOUD_TASKS_QUEUE}'…"
  gcloud tasks queues describe "${CLOUD_TASKS_QUEUE}" \
    --project="${tasks_project}" --location="${CLOUD_TASKS_LOCATION}" &>/dev/null \
  || gcloud tasks queues create "${CLOUD_TASKS_QUEUE}" \
       --project="${tasks_project}" --location="${CLOUD_TASKS_LOCATION}"

  # The API service creates tasks; the Cloud Tasks service agent mints the OIDC
  # token used by each task to call the same private Cloud Run service.
  gcloud projects add-iam-policy-binding "${tasks_project}" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/cloudtasks.enqueuer" --quiet
  gcloud iam service-accounts add-iam-policy-binding "${TASK_RUNNER_SERVICE_ACCOUNT_EMAIL}" \
    --member="serviceAccount:service-${tasks_project_number}@gcp-sa-cloudtasks.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountTokenCreator" --quiet
  ok "Cloud Tasks queue and task identity ready"
}

ensure_asset_bucket_access() {
  log "Granting the API runtime access to gs://${INCEPT_ASSET_BUCKET}…"
  gcloud storage buckets add-iam-policy-binding "gs://${INCEPT_ASSET_BUCKET}" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/storage.objectUser" --quiet
  ok "Asset bucket write/read access ready"
}

ensure_api_runtime_access() {
  log "Granting the API runtime Vertex AI and secret access…"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/aiplatform.user" --quiet
  for secret_name in "${DATABASE_CONFIG_SECRET}" "${INCEPT_INTERNAL_API_KEY_SECRET}"; do
    gcloud secrets add-iam-policy-binding "${secret_name}" \
      --project="${PROJECT_ID}" --member="serviceAccount:${DEPLOY_SA_EMAIL}" \
      --role="roles/secretmanager.secretAccessor" --quiet
  done
  ok "API runtime model and secret access ready"
}

ensure_web_runtime_access() {
  log "Granting the web runtime secret access…"
  for secret_name in "${INCEPT_INTERNAL_API_KEY_SECRET}" "${GOOGLE_CLIENT_SECRET_SECRET}" "${AUTH_SECRET_SECRET}"; do
    gcloud secrets add-iam-policy-binding "${secret_name}" \
      --project="${PROJECT_ID}" --member="serviceAccount:${DEPLOY_SA_EMAIL}" \
      --role="roles/secretmanager.secretAccessor" --quiet
  done
  ok "Web runtime secret access ready"
}

run_ai_video_schema_migration() {
  local migration_job="${AI_VIDEO_SCHEMA_MIGRATION_JOB:-incept-ai-video-schema}"

  log "Deploying AI Video Cloud SQL schema job…"
  gcloud run jobs deploy "${migration_job}" \
    --image="${API_IMAGE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --service-account="${DEPLOY_SA_EMAIL}" \
    --add-cloudsql-instances="${CLOUD_SQL_INSTANCE_CONNECTION_NAME}" \
    --command="python" --args="scripts/init_ai_video_schema.py" \
    --tasks=1 --max-retries=0 \
    --set-env-vars="INCEPT_ENV=production" \
    --set-secrets="DATABASE_CONFIG_JSON=${DATABASE_CONFIG_SECRET}:${DATABASE_CONFIG_SECRET_VERSION}" \
    --quiet
  gcloud run jobs execute "${migration_job}" \
    --project="${PROJECT_ID}" --region="${REGION}" --wait --quiet
  ok "AI Video schema is current"
}

# =============================================================================
# API — FastAPI / uvicorn
# =============================================================================
deploy_api() {
  validate_secret_migration_config
  validate_ai_video_production_config
  # The new Cloud Run revision reads these secrets during startup, so grant
  # access before asking Cloud Run to create that revision.
  ensure_api_runtime_access
  API_SECRET_BINDINGS="DATABASE_CONFIG_JSON=${DATABASE_CONFIG_SECRET}:${DATABASE_CONFIG_SECRET_VERSION}"
  API_SECRET_BINDINGS+=",INCEPT_INTERNAL_API_KEY=${INCEPT_INTERNAL_API_KEY_SECRET}:${INCEPT_INTERNAL_API_KEY_SECRET_VERSION}"
  if [[ "${PRODUCT_RELEASE_PROFILE}" == "full" ]]; then
    log "Building full API image (Creative Core enabled)…"
    assert_release_image_absent "${API_IMAGE}"
    docker build \
      --platform linux/amd64 \
      --build-context creative-core="${CREATIVE_CORE_BUILD_CONTEXT}" \
      -f "${SCRIPT_DIR}/Dockerfile.api" \
      -t "${API_IMAGE}" \
      "${SCRIPT_DIR}"
  else
    log "Building Image + AI Video API image (no Creative Core runtime)…"
    assert_release_image_absent "${API_IMAGE}"
    docker build \
      --platform linux/amd64 \
      -f "${SCRIPT_DIR}/Dockerfile.api.image-ai-video" \
      -t "${API_IMAGE}" \
      "${SCRIPT_DIR}"
  fi

  log "Pushing API image…"
  docker push "${API_IMAGE}"

  log "Deploying API to Cloud Run (${REGION})…"
  gcloud run deploy "${API_SERVICE}" \
    --image="${API_IMAGE}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --platform=managed \
    --service-account="${DEPLOY_SA_EMAIL}" \
    --add-cloudsql-instances="${CLOUD_SQL_INSTANCE_CONNECTION_NAME}" \
    --no-allow-unauthenticated \
    --min-instances=1 \
    --max-instances=1 \
    --memory=4Gi \
    --cpu=2 \
    --timeout=900 \
    --concurrency=20 \
    --no-cpu-throttling \
    --update-env-vars="\
INCEPT_ENV=production,\
INCEPT_API_MODE=live,\
AUTH_MODE=internal_key_only,\
INCEPT_ENABLE_VIDEO_PRODUCTION=${INCEPT_ENABLE_VIDEO_PRODUCTION:-false},\
INCEPT_ENABLE_GAMING_PLAYABLE=${INCEPT_ENABLE_GAMING_PLAYABLE:-false},\
GCP_PROJECT_DEPLOY=${PROJECT_ID},\
GOOGLE_CLOUD_PROJECT=${PROJECT_ID},\
GOOGLE_CLOUD_LOCATION=global,\
GCP_LOCATION=global,\
GOOGLE_GENAI_USE_ENTERPRISE=true,\
GEMINI_MODEL=gemini-3.6-flash,\
VERTEX_AI_ENABLED=true,\
GCP_PROJECT_ID=${PROJECT_ID},\
TASK_EXECUTOR_BACKEND=cloud_tasks,\
CLOUD_TASKS_PROJECT_ID=${CLOUD_TASKS_PROJECT_ID:-${PROJECT_ID}},\
CLOUD_TASKS_LOCATION=${CLOUD_TASKS_LOCATION},\
CLOUD_TASKS_QUEUE=${CLOUD_TASKS_QUEUE},\
TASK_RUNNER_SERVICE_ACCOUNT_EMAIL=${TASK_RUNNER_SERVICE_ACCOUNT_EMAIL},\
TASK_RUNNER_DISPATCH_DEADLINE_SECONDS=${TASK_RUNNER_DISPATCH_DEADLINE_SECONDS:-900},\
BQ_WRITE_PROJECT=${BQ_WRITE_PROJECT},\
BQ_READ_PROJECT=${BQ_READ_PROJECT},\
BQ_DATASET_SUPPLY_SMB_WRITE=${BQ_DATASET_SUPPLY_SMB_WRITE},\
BQ_DATASET_CONFIG=${BQ_DATASET_CONFIG},\
BIGQUERY_DATASET=${BIGQUERY_DATASET},\
BIGQUERY_ENABLED=${BIGQUERY_ENABLED:-true},\
GCP_PROJECT_DATA=${GCP_PROJECT_DATA},\
INCEPT_ASSET_BUCKET=${INCEPT_ASSET_BUCKET},\
INCEPT_REQUIRE_GCS_UPLOAD=true,\
INCEPT_ADMIN_EMAILS=${INCEPT_ADMIN_EMAILS},\
CORS_ALLOW_ORIGINS=http://localhost:3000" \
    --update-secrets="${API_SECRET_BINDINGS}"

  # incept-api must NOT be publicly invokable: the Next.js web service is the
  # only intended caller, and it authenticates with X-Internal-API-Key. Only
  # the deploy service account gets run.invoker.
  gcloud run services add-iam-policy-binding "${API_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/run.invoker" \
    --quiet

  # Cloud Tasks calls the private API using this exact runtime identity.
  gcloud run services add-iam-policy-binding "${API_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --member="serviceAccount:${TASK_RUNNER_SERVICE_ACCOUNT_EMAIL}" --role="roles/run.invoker" \
    --quiet

  API_URL="$(gcloud run services describe "${API_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --format='value(status.url)')"

  # The API URL is assigned by Cloud Run, so bind it only after the first
  # deployment. Cloud Tasks then targets /ai-video/... on this same service.
  gcloud run services update "${API_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --update-env-vars="TASK_RUNNER_URL=${API_URL}" \
    --quiet

  ensure_ai_video_task_queue
  ensure_asset_bucket_access
  run_ai_video_schema_migration

  ok "API live → ${API_URL}"
  echo "${API_URL}" > "${SCRIPT_DIR}/.api-url.tmp"
}

# =============================================================================
# Web — Next.js standalone
# =============================================================================
deploy_web() {
  validate_secret_migration_config
  ensure_web_runtime_access
  WEB_SECRET_ARGS=()
  if secret_migration_requested; then
    WEB_SECRET_ARGS=(
      "--update-secrets=INCEPT_INTERNAL_API_KEY=${INCEPT_INTERNAL_API_KEY_SECRET}:${INCEPT_INTERNAL_API_KEY_SECRET_VERSION},GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET_SECRET}:${GOOGLE_CLIENT_SECRET_SECRET_VERSION},AUTH_SECRET=${AUTH_SECRET_SECRET}:${AUTH_SECRET_SECRET_VERSION}"
    )
  fi
  # Get API URL (from temp file written by deploy_api, or from Cloud Run)
  if [[ -f "${SCRIPT_DIR}/.api-url.tmp" ]]; then
    API_URL="$(cat "${SCRIPT_DIR}/.api-url.tmp")"
  else
    API_URL="$(gcloud run services describe "${API_SERVICE}" \
      --project="${PROJECT_ID}" --region="${REGION}" \
      --format='value(status.url)' 2>/dev/null || true)"
  fi
  [[ -z "${API_URL}" ]] && err "API service not deployed yet. Run: ./deploy.sh api"

  log "Building Web image (context: repo root, Dockerfile: Dockerfile.web)…"
  assert_release_image_absent "${WEB_IMAGE}"
  docker build \
    --platform linux/amd64 \
    --build-arg "INCEPT_ENABLE_VIDEO_PRODUCTION=${INCEPT_ENABLE_VIDEO_PRODUCTION:-false}" \
    --build-arg "INCEPT_ENABLE_GAMING_PLAYABLE=${INCEPT_ENABLE_GAMING_PLAYABLE:-false}" \
    -f "${SCRIPT_DIR}/Dockerfile.web" \
    -t "${WEB_IMAGE}" \
    "${SCRIPT_DIR}"

  log "Pushing Web image…"
  docker push "${WEB_IMAGE}"

  log "Deploying Web to Cloud Run (${REGION})…"
  gcloud run deploy "${WEB_SERVICE}" \
    --image="${WEB_IMAGE}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --platform=managed \
    --service-account="${DEPLOY_SA_EMAIL}" \
    --no-allow-unauthenticated \
    --min-instances=0 \
    --max-instances=5 \
    --memory=512Mi \
    --cpu=1 \
    --timeout=30 \
    --concurrency=100 \
    --update-env-vars="\
NODE_ENV=production,\
NEXT_TELEMETRY_DISABLED=1,\
API_BASE_URL=${API_URL},\
INCEPT_ENABLE_VIDEO_PRODUCTION=${INCEPT_ENABLE_VIDEO_PRODUCTION:-false},\
INCEPT_ENABLE_GAMING_PLAYABLE=${INCEPT_ENABLE_GAMING_PLAYABLE:-false},\
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},\
NEXTAUTH_URL=https://placeholder.example.com" \
    "${WEB_SECRET_ARGS[@]}"

  WEB_URL="$(gcloud run services describe "${WEB_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --format='value(status.url)')"

  ok "Web deployed (first pass) → ${WEB_URL}"

  # If a custom domain is mapped (e.g. linglonglab.moloco.cloud), use it for
  # NEXTAUTH_URL / CORS instead of the raw .run.app URL — otherwise every
  # deploy resets auth redirects back to the .run.app address.
  PUBLIC_WEB_URL="${CUSTOM_DOMAIN:-${WEB_URL}}"

  # ── Grant public access to web service ───────────────────────────────────
  gcloud run services add-iam-policy-binding "${WEB_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --member="allUsers" --role="roles/run.invoker" \
    --quiet 2>/dev/null || \
    echo "   ℹ  Could not set allUsers invoker — will need manual IAM grant (see deploy notes)."

  # ── Patch NEXTAUTH_URL now that we know the real URL ──────────────────────
  log "Patching NEXTAUTH_URL to ${PUBLIC_WEB_URL}…"
  gcloud run services update "${WEB_SERVICE}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --update-env-vars="NEXTAUTH_URL=${PUBLIC_WEB_URL}" \
    --quiet

  # ── Patch API CORS to allow web origin ───────────────────────────────────
  log "Updating API CORS_ALLOW_ORIGINS…"
  # Use ^|^ delimiter: | never appears in URLs, so commas and colons in the value are safe
  gcloud run services update "${API_SERVICE}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --update-env-vars="^|^CORS_ALLOW_ORIGINS=${PUBLIC_WEB_URL},${WEB_URL},http://localhost:3000" \
    --quiet

  # ── Persist URLs to .env.deploy for future re-deploys ────────────────────
  sed -i.bak "s|NEXTAUTH_URL=.*|NEXTAUTH_URL=${PUBLIC_WEB_URL}|" "${ENV_FILE}"
  rm -f "${SCRIPT_DIR}/.api-url.tmp" "${ENV_FILE}.bak"

  echo ""
  echo "╔══════════════════════════════════════════════════════════════════╗"
  echo "║  🎉 Incept is live!                                         ║"
  echo "╠══════════════════════════════════════════════════════════════════╣"
  printf "║  API  %-58s ║\n" "${API_URL}"
  printf "║  Web  %-58s ║\n" "${WEB_URL}"
  echo "╠══════════════════════════════════════════════════════════════════╣"
  echo "║  ⚠ One manual step remaining:                                   ║"
  echo "║  Add this to Google OAuth → Authorized redirect URIs:           ║"
  printf "║  %-64s ║\n" "${WEB_URL}/api/auth/callback/google"
  echo "╚══════════════════════════════════════════════════════════════════╝"
}

# ── Main ──────────────────────────────────────────────────────────────────────
ensure_ar_repo

case "${TARGET}" in
  api)  deploy_api ;;
  web)  deploy_web ;;
  both) deploy_api && deploy_web ;;
  migrate) run_ai_video_schema_migration ;;
  *)    err "Unknown target '${TARGET}'. Use: api | web | both | migrate" ;;
esac
