#!/usr/bin/env bash
# =============================================================================
# Incept — Cloud Run deploy script
#
# Usage:
#   ./deploy.sh         → build + deploy api then web (full)
#   ./deploy.sh api     → deploy API only
#   ./deploy.sh web     → deploy Web only
#
# Requires: gcloud CLI, Docker Desktop running, .env.deploy filled in.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Load .env.deploy ──────────────────────────────────────────────────────────
ENV_FILE="${SCRIPT_DIR}/.env.deploy"
[[ ! -f "${ENV_FILE}" ]] && { echo "✗ .env.deploy not found"; exit 1; }
set -a; source "${ENV_FILE}"; set +a

# ── Validate required vars ────────────────────────────────────────────────────
: "${DEPLOY_SA_EMAIL:?Set DEPLOY_SA_EMAIL in .env.deploy}"
: "${GCP_PROJECT_DEPLOY:?Set GCP_PROJECT_DEPLOY in .env.deploy}"
: "${INCEPT_INTERNAL_API_KEY:?}"
: "${GOOGLE_CLIENT_ID:?}"
: "${GOOGLE_CLIENT_SECRET:?}"
: "${AUTH_SECRET:?}"
: "${CREATIVE_CORE_BUILD_CONTEXT:?Set CREATIVE_CORE_BUILD_CONTEXT in .env.deploy}"
[[ -f "${CREATIVE_CORE_BUILD_CONTEXT}/package.json" ]] || { echo "✗ CREATIVE_CORE_BUILD_CONTEXT must point to a prepared Creative Core installation" >&2; exit 1; }
[[ -f "${CREATIVE_CORE_BUILD_CONTEXT}/scripts/cr-agent-core.sh" ]] || { echo "✗ CREATIVE_CORE_BUILD_CONTEXT is missing scripts/cr-agent-core.sh" >&2; exit 1; }
[[ -f "${CREATIVE_CORE_BUILD_CONTEXT}/pnpm-lock.yaml" ]] || { echo "✗ CREATIVE_CORE_BUILD_CONTEXT is missing pnpm-lock.yaml" >&2; exit 1; }

# ── Derived config ────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_DEPLOY}"
REGION="${REGION:-asia-northeast1}"
REPO="incept"

API_SERVICE="incept-api"
WEB_SERVICE="incept-web"

AR_HOST="${REGION}-docker.pkg.dev"
API_IMAGE="${AR_HOST}/${PROJECT_ID}/${REPO}/api"
WEB_IMAGE="${AR_HOST}/${PROJECT_ID}/${REPO}/web"

TARGET="${1:-both}"

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo -e "\n\033[1;34m▶  $*\033[0m"; }
ok()   { echo -e "\033[1;32m✓  $*\033[0m"; }
info() { echo -e "   $*"; }
err()  { echo -e "\033[1;31m✗  $*\033[0m" >&2; exit 1; }

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

# =============================================================================
# API — FastAPI / uvicorn
# =============================================================================
deploy_api() {
  # The API Dockerfile lives at the repo root — it copies both apps/api/ and sql/
  log "Building API image (context: repo root, Dockerfile: Dockerfile.api)…"
  docker build \
    --platform linux/amd64 \
    --build-context creative-core="${CREATIVE_CORE_BUILD_CONTEXT}" \
    -f "${SCRIPT_DIR}/Dockerfile.api" \
    -t "${API_IMAGE}:latest" \
    "${SCRIPT_DIR}"

  log "Pushing API image…"
  docker push "${API_IMAGE}:latest"

  log "Deploying API to Cloud Run (${REGION})…"
  gcloud run deploy "${API_SERVICE}" \
    --image="${API_IMAGE}:latest" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --platform=managed \
    --service-account="${DEPLOY_SA_EMAIL}" \
    --no-allow-unauthenticated \
    --min-instances=1 \
    --max-instances=1 \
    --memory=4Gi \
    --cpu=2 \
    --timeout=900 \
    --concurrency=1 \
    --no-cpu-throttling \
    --set-env-vars="\
INCEPT_ENV=production,\
INCEPT_API_MODE=live,\
AUTH_MODE=production,\
GCP_PROJECT_DEPLOY=${PROJECT_ID},\
GOOGLE_CLOUD_PROJECT=${PROJECT_ID},\
GOOGLE_CLOUD_LOCATION=global,\
GCP_LOCATION=global,\
GOOGLE_GENAI_USE_ENTERPRISE=true,\
GEMINI_MODEL=gemini-3.1-flash-lite,\
VERTEX_VEO_FAST_MODEL=${VERTEX_VEO_FAST_MODEL:-veo-3.1-fast-generate-001},\
VERTEX_VEO_LOCATION=${VERTEX_VEO_LOCATION:-us-central1},\
VERTEX_PLAYABLE_MODEL=${VERTEX_PLAYABLE_MODEL:-gemini-3.6-flash},\
STUDIO_USER_BUDGET_USD=${STUDIO_USER_BUDGET_USD:-500},\
VEO_FAST_ESTIMATED_COST_PER_SECOND_USD=${VEO_FAST_ESTIMATED_COST_PER_SECOND_USD:-0.08},\
CREATIVE_CORE_HOME=/opt/creative-core,\
PLAYABLE_CAPTURE_CHROME_PATH=/usr/local/bin/incept-chromium,\
PLAYABLE_CAPTURE_FFMPEG_PATH=/usr/bin/ffmpeg,\
BQ_WRITE_PROJECT=${BQ_WRITE_PROJECT},\
BQ_READ_PROJECT=${BQ_READ_PROJECT},\
BQ_DATASET_SUPPLY_SMB_WRITE=${BQ_DATASET_SUPPLY_SMB_WRITE},\
BQ_DATASET_CONFIG=${BQ_DATASET_CONFIG},\
BIGQUERY_DATASET=${BIGQUERY_DATASET},\
BIGQUERY_ENABLED=${BIGQUERY_ENABLED:-true},\
GCP_PROJECT_DATA=${GCP_PROJECT_DATA},\
INCEPT_ASSET_BUCKET=${INCEPT_ASSET_BUCKET},\
INCEPT_REQUIRE_GCS_UPLOAD=${INCEPT_REQUIRE_GCS_UPLOAD:-false},\
INCEPT_INTERNAL_API_KEY=${INCEPT_INTERNAL_API_KEY},\
INCEPT_ADMIN_EMAILS=${INCEPT_ADMIN_EMAILS},\
CORS_ALLOW_ORIGINS=http://localhost:3000"

  # Grant public access (may fail if org policy blocks allUsers — OK to ignore,
  # the Next.js web service calls the API with the internal key anyway)
  gcloud run services add-iam-policy-binding "${API_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --member="allUsers" --role="roles/run.invoker" \
    --quiet 2>/dev/null || \
    echo "   ℹ  Could not set allUsers invoker — org policy may block it. API still works via internal key."

  gcloud run services add-iam-policy-binding "${API_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/run.invoker" \
    --quiet

  API_URL="$(gcloud run services describe "${API_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --format='value(status.url)')"

  ok "API live → ${API_URL}"
  echo "${API_URL}" > "${SCRIPT_DIR}/.api-url.tmp"
}

# =============================================================================
# Web — Next.js standalone
# =============================================================================
deploy_web() {
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
  docker build \
    --platform linux/amd64 \
    -f "${SCRIPT_DIR}/Dockerfile.web" \
    -t "${WEB_IMAGE}:latest" \
    "${SCRIPT_DIR}"

  log "Pushing Web image…"
  docker push "${WEB_IMAGE}:latest"

  log "Deploying Web to Cloud Run (${REGION})…"
  gcloud run deploy "${WEB_SERVICE}" \
    --image="${WEB_IMAGE}:latest" \
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
    --set-env-vars="\
NODE_ENV=production,\
NEXT_TELEMETRY_DISABLED=1,\
API_BASE_URL=${API_URL},\
INCEPT_INTERNAL_API_KEY=${INCEPT_INTERNAL_API_KEY},\
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},\
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET},\
AUTH_SECRET=${AUTH_SECRET},\
NEXTAUTH_URL=https://placeholder.example.com"

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
  *)    err "Unknown target '${TARGET}'. Use: api | web | both" ;;
esac
