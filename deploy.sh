#!/usr/bin/env bash
# =============================================================================
# LinglongLab — Cloud Run deploy script
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
    api|web|both) TARGET="$1" ;;
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
: "${INCEPT_INTERNAL_API_KEY_SECRET:?Set INCEPT_INTERNAL_API_KEY_SECRET in .env.deploy}"
: "${INCEPT_INTERNAL_API_KEY_SECRET_VERSION:?Set INCEPT_INTERNAL_API_KEY_SECRET_VERSION in .env.deploy}"
: "${GOOGLE_CLIENT_SECRET_SECRET:?Set GOOGLE_CLIENT_SECRET_SECRET in .env.deploy}"
: "${GOOGLE_CLIENT_SECRET_SECRET_VERSION:?Set GOOGLE_CLIENT_SECRET_SECRET_VERSION in .env.deploy}"
: "${AUTH_SECRET_SECRET:?Set AUTH_SECRET_SECRET in .env.deploy}"
: "${AUTH_SECRET_SECRET_VERSION:?Set AUTH_SECRET_SECRET_VERSION in .env.deploy}"
: "${BQ_WRITE_PROJECT:?Set BQ_WRITE_PROJECT in .env.deploy}"
: "${BQ_READ_PROJECT:?Set BQ_READ_PROJECT in .env.deploy}"
: "${BQ_DATASET_CONFIG:?Set BQ_DATASET_CONFIG in .env.deploy}"
: "${BIGQUERY_DATASET:?Set BIGQUERY_DATASET in .env.deploy}"
: "${GCP_PROJECT_DATA:?Set GCP_PROJECT_DATA in .env.deploy}"
: "${INCEPT_ADMIN_EMAILS:?Set INCEPT_ADMIN_EMAILS in .env.deploy}"

# The production release contains the LinglongLab Image and Video workspaces.
PRODUCT_RELEASE_PROFILE="${PRODUCT_RELEASE_PROFILE:-image-video}"
case "${PRODUCT_RELEASE_PROFILE}" in
  image-video) ;;
  *) echo "✗ Unknown PRODUCT_RELEASE_PROFILE '${PRODUCT_RELEASE_PROFILE}'. Use: image-video" >&2; exit 1 ;;
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
BUILD_BACKEND="${BUILD_BACKEND:-local}"
case "${BUILD_BACKEND}" in
  local|cloud-build) ;;
  *) echo "✗ BUILD_BACKEND must be local or cloud-build" >&2; exit 1 ;;
esac

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

validate_cloud_resources() {
  log "Validating deployment-owned cloud resources…"
  gcloud iam service-accounts describe "${DEPLOY_SA_EMAIL}" \
    --project="${PROJECT_ID}" --quiet >/dev/null

  local secret_specs=(
    "${DATABASE_CONFIG_SECRET}:${DATABASE_CONFIG_SECRET_VERSION}"
    "${INCEPT_INTERNAL_API_KEY_SECRET}:${INCEPT_INTERNAL_API_KEY_SECRET_VERSION}"
    "${GOOGLE_CLIENT_SECRET_SECRET}:${GOOGLE_CLIENT_SECRET_SECRET_VERSION}"
    "${AUTH_SECRET_SECRET}:${AUTH_SECRET_SECRET_VERSION}"
  )
  if has_value OPENAI_API_KEY_SECRET || has_value OPENAI_API_KEY_SECRET_VERSION; then
    : "${OPENAI_API_KEY_SECRET:?Set both OPENAI secret fields, or neither}"
    : "${OPENAI_API_KEY_SECRET_VERSION:?Set both OPENAI secret fields, or neither}"
    secret_specs+=("${OPENAI_API_KEY_SECRET}:${OPENAI_API_KEY_SECRET_VERSION}")
  fi
  if has_value ANTHROPIC_API_KEY_SECRET || has_value ANTHROPIC_API_KEY_SECRET_VERSION; then
    : "${ANTHROPIC_API_KEY_SECRET:?Set both Anthropic secret fields, or neither}"
    : "${ANTHROPIC_API_KEY_SECRET_VERSION:?Set both Anthropic secret fields, or neither}"
    secret_specs+=("${ANTHROPIC_API_KEY_SECRET}:${ANTHROPIC_API_KEY_SECRET_VERSION}")
  fi
  local secret_spec secret_name secret_version
  for secret_spec in "${secret_specs[@]}"; do
    secret_name="${secret_spec%%:*}"
    secret_version="${secret_spec#*:}"
    gcloud secrets versions describe "${secret_version}" \
      --secret="${secret_name}" --project="${PROJECT_ID}" --quiet >/dev/null
  done

  local sql_project sql_region sql_instance
  IFS=: read -r sql_project sql_region sql_instance <<< "${CLOUD_SQL_INSTANCE_CONNECTION_NAME}"
  [[ -n "${sql_project}" && -n "${sql_region}" && -n "${sql_instance}" ]] \
    || err "CLOUD_SQL_INSTANCE_CONNECTION_NAME must be project:region:instance"
  gcloud sql instances describe "${sql_instance}" \
    --project="${sql_project}" --quiet >/dev/null

  gcloud storage buckets describe "gs://${INCEPT_ASSET_BUCKET}" \
    --project="${PROJECT_ID}" --quiet >/dev/null
  if [[ -n "${VIDEO_STUDIO_BUCKET:-}" && "${VIDEO_STUDIO_BUCKET}" != "${INCEPT_ASSET_BUCKET}" ]]; then
    gcloud storage buckets describe "gs://${VIDEO_STUDIO_BUCKET}" \
      --project="${PROJECT_ID}" --quiet >/dev/null
  fi
  ok "Cloud resource references are valid"
}

# ── One-time setup: Artifact Registry repo ───────────────────────────────────
ensure_ar_repo() {
  log "Checking Artifact Registry repo '${REPO}'…"
  gcloud artifacts repositories describe "${REPO}" \
    --project="${PROJECT_ID}" --location="${REGION}" &>/dev/null \
  || gcloud artifacts repositories create "${REPO}" \
       --project="${PROJECT_ID}" --location="${REGION}" \
       --repository-format=docker \
       --description="LinglongLab container images"
  if [[ "${BUILD_BACKEND}" == "local" ]]; then
    gcloud auth configure-docker "${AR_HOST}" --quiet
  fi
  ok "Artifact Registry ready (${AR_HOST}/${PROJECT_ID}/${REPO})"
}

assert_release_image_absent() {
  local image="$1"
  if gcloud artifacts docker images describe "${image}" --project="${PROJECT_ID}" &>/dev/null; then
    err "Release image already exists: ${image}. Release tags are immutable; create a new release ID."
  fi
}

assert_service_ready() {
  local service="$1"
  local ready
  ready="$(gcloud run services describe "${service}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --format='value(status.conditions[0].status)')"
  [[ "${ready}" == "True" ]] || err "Cloud Run service '${service}' is not Ready (status: ${ready:-unknown})."
}

# IAM changes are opt-in. Deployers usually cannot edit IAM policies, and the
# runtime service account already holds the roles below, so by default this
# script only verifies them (read-only). Set GRANT_IAM=true, as someone who can
# edit IAM policies, to apply missing bindings.
GRANT_IAM="${GRANT_IAM:-false}"
warn() { echo -e "\033[1;33m!  $*\033[0m" >&2; }

has_secret_accessor() {
  local out
  out="$(gcloud secrets get-iam-policy "$1" --project="${PROJECT_ID}" \
    --flatten="bindings[].members" \
    --filter="bindings.role=roles/secretmanager.secretAccessor AND bindings.members=serviceAccount:${DEPLOY_SA_EMAIL}" \
    --format="value(bindings.role)")"
  [[ -n "${out}" ]]
}

# A new revision cannot start if it cannot read its secrets, so fail before
# spending a build on it.
verify_secret_access() {
  local missing=() secret_name
  for secret_name in "$@"; do
    has_secret_accessor "${secret_name}" || missing+=("${secret_name}")
  done
  if (( ${#missing[@]} )); then
    err "${DEPLOY_SA_EMAIL} cannot read secret(s): ${missing[*]}. Ask an IAM admin to grant roles/secretmanager.secretAccessor on them, or re-run with GRANT_IAM=true if you can edit IAM policies."
  fi
}

verify_project_roles() {
  local policy role missing=()
  policy="$(gcloud projects get-iam-policy "${PROJECT_ID}" \
    --flatten="bindings[].members" \
    --filter="bindings.members=serviceAccount:${DEPLOY_SA_EMAIL}" \
    --format="value(bindings.role)")" || { warn "Could not read the project IAM policy; skipping the role check"; return 0; }
  for role in "$@"; do
    grep -qx "${role}" <<< "${policy}" || missing+=("${role}")
  done
  if (( ${#missing[@]} )); then
    warn "${DEPLOY_SA_EMAIL} is missing project role(s): ${missing[*]}. Continuing; ask an IAM admin if the service misbehaves."
  fi
}

assert_api_private() {
  local public
  public="$(gcloud run services get-iam-policy "${API_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --flatten="bindings[].members" \
    --filter="bindings.role=roles/run.invoker AND (bindings.members=allUsers OR bindings.members=allAuthenticatedUsers)" \
    --format="value(bindings.members)")"
  [[ -z "${public}" ]] || err "${API_SERVICE} is publicly invokable (${public}). Remove that run.invoker grant, or re-run with GRANT_IAM=true."
}

ensure_asset_bucket_access() {
  if [[ "${GRANT_IAM}" != "true" ]]; then
    info "Skipping bucket IAM changes (GRANT_IAM=false); assuming ${DEPLOY_SA_EMAIL} already has access to gs://${INCEPT_ASSET_BUCKET}"
    return
  fi
  log "Granting the API runtime access to gs://${INCEPT_ASSET_BUCKET}…"
  gcloud storage buckets add-iam-policy-binding "gs://${INCEPT_ASSET_BUCKET}" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/storage.objectUser" --quiet
  ok "Asset bucket write/read access ready"
}

ensure_api_runtime_access() {
  local secret_names=("${DATABASE_CONFIG_SECRET}" "${INCEPT_INTERNAL_API_KEY_SECRET}")
  [[ -n "${OPENAI_API_KEY_SECRET:-}" ]] && secret_names+=("${OPENAI_API_KEY_SECRET}")
  [[ -n "${ANTHROPIC_API_KEY_SECRET:-}" ]] && secret_names+=("${ANTHROPIC_API_KEY_SECRET}")
  if [[ "${GRANT_IAM}" != "true" ]]; then
    log "Verifying API runtime access (read-only, GRANT_IAM=false)…"
    verify_project_roles roles/aiplatform.user roles/serviceusage.serviceUsageConsumer roles/cloudsql.client
    verify_secret_access "${secret_names[@]}"
    ok "API runtime can read its secrets"
    return
  fi
  log "Granting the API runtime Vertex AI and secret access…"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/aiplatform.user" --quiet
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/serviceusage.serviceUsageConsumer" --quiet
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/cloudsql.client" --quiet
  for secret_name in "${secret_names[@]}"; do
    gcloud secrets add-iam-policy-binding "${secret_name}" \
      --project="${PROJECT_ID}" --member="serviceAccount:${DEPLOY_SA_EMAIL}" \
      --role="roles/secretmanager.secretAccessor" --quiet
  done
  ok "API runtime model and secret access ready"
}

ensure_web_runtime_access() {
  local secret_names=("${INCEPT_INTERNAL_API_KEY_SECRET}" "${GOOGLE_CLIENT_SECRET_SECRET}" "${AUTH_SECRET_SECRET}")
  if [[ "${GRANT_IAM}" != "true" ]]; then
    log "Verifying web runtime secret access (read-only, GRANT_IAM=false)…"
    verify_secret_access "${secret_names[@]}"
    ok "Web runtime can read its secrets"
    return
  fi
  log "Granting the web runtime secret access…"
  for secret_name in "${secret_names[@]}"; do
    gcloud secrets add-iam-policy-binding "${secret_name}" \
      --project="${PROJECT_ID}" --member="serviceAccount:${DEPLOY_SA_EMAIL}" \
      --role="roles/secretmanager.secretAccessor" --quiet
  done
  ok "Web runtime secret access ready"
}

# =============================================================================
# API — FastAPI / uvicorn
# =============================================================================
deploy_api() {
  validate_secret_migration_config
  # The new Cloud Run revision reads these secrets during startup, so grant
  # access before asking Cloud Run to create that revision.
  ensure_api_runtime_access
  ensure_asset_bucket_access
  API_SECRET_BINDINGS="DATABASE_CONFIG_JSON=${DATABASE_CONFIG_SECRET}:${DATABASE_CONFIG_SECRET_VERSION}"
  API_SECRET_BINDINGS+=",INCEPT_INTERNAL_API_KEY=${INCEPT_INTERNAL_API_KEY_SECRET}:${INCEPT_INTERNAL_API_KEY_SECRET_VERSION}"
  if has_value OPENAI_API_KEY_SECRET || has_value OPENAI_API_KEY_SECRET_VERSION; then
    : "${OPENAI_API_KEY_SECRET:?Set both OPENAI secret fields, or neither}"
    : "${OPENAI_API_KEY_SECRET_VERSION:?Set both OPENAI secret fields, or neither}"
    API_SECRET_BINDINGS+=",OPENAI_API_KEY=${OPENAI_API_KEY_SECRET}:${OPENAI_API_KEY_SECRET_VERSION}"
  fi
  if has_value ANTHROPIC_API_KEY_SECRET || has_value ANTHROPIC_API_KEY_SECRET_VERSION; then
    : "${ANTHROPIC_API_KEY_SECRET:?Set both Anthropic secret fields, or neither}"
    : "${ANTHROPIC_API_KEY_SECRET_VERSION:?Set both Anthropic secret fields, or neither}"
    API_SECRET_BINDINGS+=",ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY_SECRET}:${ANTHROPIC_API_KEY_SECRET_VERSION}"
  fi
  # These values used to be plain environment variables. Cloud Run cannot switch
  # a variable between plain and secret in place, so remove the plain one in the
  # same update (removing a name that is already secret-backed is harmless).
  API_REMOVE_ENV="INCEPT_INTERNAL_API_KEY"
  has_value OPENAI_API_KEY_SECRET && API_REMOVE_ENV+=",OPENAI_API_KEY"
  has_value ANTHROPIC_API_KEY_SECRET && API_REMOVE_ENV+=",ANTHROPIC_API_KEY"
  log "Building unified Image + Video FastAPI image (${BUILD_BACKEND})…"
  assert_release_image_absent "${API_IMAGE}"
  if [[ "${BUILD_BACKEND}" == "cloud-build" ]]; then
    gcloud builds submit "${SCRIPT_DIR}" \
      --project="${PROJECT_ID}" \
      --config="${SCRIPT_DIR}/cloudbuild.api.yaml" \
      --substitutions="_IMAGE=${API_IMAGE}" \
      --quiet
  else
    docker build \
      --platform linux/amd64 \
      -f "${SCRIPT_DIR}/Dockerfile.nbs-api" \
      -t "${API_IMAGE}" \
      "${SCRIPT_DIR}"
    log "Pushing API image…"
    docker push "${API_IMAGE}"
  fi

  log "Deploying API to Cloud Run (${REGION})…"
  gcloud run deploy "${API_SERVICE}" \
    --image="${API_IMAGE}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --platform=managed \
    --execution-environment=gen2 \
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
    --add-volume="mount-path=/app/video-data,type=cloud-storage,bucket=${VIDEO_STUDIO_BUCKET:-${INCEPT_ASSET_BUCKET}},readonly=false" \
    --update-env-vars="^|^\
INCEPT_ENV=production|\
INCEPT_API_MODE=live|\
AUTH_MODE=internal_key_only|\
INCEPT_ENABLE_GAMING_PLAYABLE=${INCEPT_ENABLE_GAMING_PLAYABLE:-false}|\
GCP_PROJECT_DEPLOY=${PROJECT_ID}|\
GOOGLE_CLOUD_PROJECT=${PROJECT_ID}|\
GCP_LOCATION=global|\
VERTEX_GEMINI_MODEL=gemini-3.8-flash|\
VERTEX_PLAYABLE_FLASH_MODEL=gemini-3.8-flash|\
VERTEX_PLAYABLE_PRO_MODEL=gemini-3.1-pro-preview|\
VERTEX_VIDEO_ANALYSIS_MODEL=gemini-3.8-flash|\
OPENAI_TEXT_MODEL=${OPENAI_TEXT_MODEL:-gpt-6.1-sol}|\
VERTEX_GEMINI_IMAGE_MODEL=gemini-3.1-flash-image|\
OPENAI_IMAGE_MODEL=gpt-image-2.5-flare|\
VERTEX_VEO_FAST_MODEL=gemini-omni-1.1-flash-preview|\
VERTEX_VEO_LOCATION=global|\
OPENAI_TTS_MODEL=gpt-4o-mini-tts-2025-12-15|\
GOOGLE_TTS_MODEL=gemini-3.1-flash-tts-preview|\
ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-claude-sonnet-5-5}|\
VERTEX_AI_ENABLED=true|\
GCP_PROJECT_ID=${PROJECT_ID}|\
BQ_WRITE_PROJECT=${BQ_WRITE_PROJECT}|\
BQ_READ_PROJECT=${BQ_READ_PROJECT}|\
BQ_DATASET_APP_WRITE=${BQ_DATASET_APP_WRITE:-Incept}|\
BQ_DATASET_CONFIG=${BQ_DATASET_CONFIG}|\
BIGQUERY_DATASET=${BIGQUERY_DATASET}|\
BIGQUERY_ENABLED=${BIGQUERY_ENABLED:-true}|\
GCP_PROJECT_DATA=${GCP_PROJECT_DATA}|\
INCEPT_ASSET_BUCKET=${INCEPT_ASSET_BUCKET}|\
VIDEO_STUDIO_DATA_DIR=/app/video-data/video-studio|\
INCEPT_REQUIRE_GCS_UPLOAD=true|\
INCEPT_ADMIN_EMAILS=${INCEPT_ADMIN_EMAILS}|\
CORS_ALLOW_ORIGINS=http://localhost:3000" \
    --remove-env-vars="${API_REMOVE_ENV}" \
    --update-secrets="${API_SECRET_BINDINGS}"

  # incept-api must NOT be publicly invokable: the Next.js web service is the
  # only intended caller, and it authenticates with X-Internal-API-Key. Only
  # the deploy service account gets run.invoker.
  if [[ "${GRANT_IAM}" == "true" ]]; then
    gcloud run services add-iam-policy-binding "${API_SERVICE}" \
      --project="${PROJECT_ID}" --region="${REGION}" \
      --member="serviceAccount:${DEPLOY_SA_EMAIL}" --role="roles/run.invoker" \
      --quiet
    # Remove legacy broad invoker grants if an older revision was public.
    for public_member in allUsers allAuthenticatedUsers; do
      gcloud run services remove-iam-policy-binding "${API_SERVICE}" \
        --project="${PROJECT_ID}" --region="${REGION}" \
        --member="${public_member}" --role="roles/run.invoker" \
        --quiet 2>/dev/null || true
    done
  else
    assert_api_private
  fi

  API_URL="$(gcloud run services describe "${API_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --format='value(status.url)')"
  assert_service_ready "${API_SERVICE}"

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
      "--remove-env-vars=INCEPT_INTERNAL_API_KEY,GOOGLE_CLIENT_SECRET,AUTH_SECRET"
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
  log "Building Web image (${BUILD_BACKEND})…"
  assert_release_image_absent "${WEB_IMAGE}"
  if [[ "${BUILD_BACKEND}" == "cloud-build" ]]; then
    gcloud builds submit "${SCRIPT_DIR}" \
      --project="${PROJECT_ID}" \
      --config="${SCRIPT_DIR}/cloudbuild.web.yaml" \
      --substitutions="_IMAGE=${WEB_IMAGE},_INCEPT_ENABLE_GAMING_PLAYABLE=${INCEPT_ENABLE_GAMING_PLAYABLE:-false}" \
      --quiet
  else
    docker build \
      --platform linux/amd64 \
      --build-arg "INCEPT_ENABLE_GAMING_PLAYABLE=${INCEPT_ENABLE_GAMING_PLAYABLE:-false}" \
      -f "${SCRIPT_DIR}/Dockerfile.web" \
      -t "${WEB_IMAGE}" \
      "${SCRIPT_DIR}"
    log "Pushing Web image…"
    docker push "${WEB_IMAGE}"
  fi

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
    --timeout=900 \
    --concurrency=100 \
    --update-env-vars="\
NODE_ENV=production,\
NEXT_TELEMETRY_DISABLED=1,\
API_BASE_URL=${API_URL},\
INCEPT_ENABLE_GAMING_PLAYABLE=${INCEPT_ENABLE_GAMING_PLAYABLE:-false},\
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},\
NEXTAUTH_URL=https://placeholder.example.com" \
    "${WEB_SECRET_ARGS[@]}"

  WEB_URL="$(gcloud run services describe "${WEB_SERVICE}" \
    --project="${PROJECT_ID}" --region="${REGION}" \
    --format='value(status.url)')"
  assert_service_ready "${WEB_SERVICE}"

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
  assert_service_ready "${WEB_SERVICE}"

  # ── Patch API CORS to allow web origin ───────────────────────────────────
  log "Updating API CORS_ALLOW_ORIGINS…"
  # Use ^|^ delimiter: | never appears in URLs, so commas and colons in the value are safe
  gcloud run services update "${API_SERVICE}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --update-env-vars="^|^CORS_ALLOW_ORIGINS=${PUBLIC_WEB_URL},${WEB_URL},http://localhost:3000" \
    --quiet
  assert_service_ready "${API_SERVICE}"

  # ── Persist URLs to .env.deploy for future re-deploys ────────────────────
  sed -i.bak "s|NEXTAUTH_URL=.*|NEXTAUTH_URL=${PUBLIC_WEB_URL}|" "${ENV_FILE}"
  rm -f "${SCRIPT_DIR}/.api-url.tmp" "${ENV_FILE}.bak"

  echo ""
  echo "╔══════════════════════════════════════════════════════════════════╗"
  echo "║  🎉 LinglongLab is live!                                         ║"
  echo "╠══════════════════════════════════════════════════════════════════╣"
  printf "║  API  %-58s ║\n" "${API_URL}"
  printf "║  Web  %-58s ║\n" "${WEB_URL}"
  echo "╠══════════════════════════════════════════════════════════════════╣"
  echo "║  ⚠ One manual step remaining:                                   ║"
  echo "║  Add this to Google OAuth → Authorized redirect URIs:           ║"
  printf "║  %-64s ║\n" "${PUBLIC_WEB_URL}/api/auth/callback/google"
  echo "╚══════════════════════════════════════════════════════════════════╝"
}

# ── Main ──────────────────────────────────────────────────────────────────────
validate_cloud_resources
ensure_ar_repo

case "${TARGET}" in
  api)  deploy_api ;;
  web)  deploy_web ;;
  both) deploy_api && deploy_web ;;
  *)    err "Unknown target '${TARGET}'. Use: api | web | both" ;;
esac
