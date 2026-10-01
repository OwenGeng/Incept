#!/usr/bin/env bash
# =============================================================================
# LinglongLab -- Grant IAM roles to an existing Service Account (run once)
# Usage: ./setup-iam.sh your-sa@ads-bpd-guard-sandbox.iam.gserviceaccount.com
# =============================================================================
set -euo pipefail

SA_EMAIL="${1:?Usage: ./setup-iam.sh SA_EMAIL}"
PROJECT_ID="ads-bpd-guard-sandbox"
DATA_PROJECT="ads-bpd-guard-china"

log() { echo -e "\n\033[1;34m▶ $*\033[0m"; }
ok()  { echo -e "\033[1;32m✓ $*\033[0m"; }

log "Granting roles to ${SA_EMAIL}…"

# BigQuery — write config.users, run query jobs
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.dataEditor" --quiet

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.jobUser" --quiet

# BigQuery — read data from ads-bpd-guard-china
gcloud projects add-iam-policy-binding "${DATA_PROJECT}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.dataViewer" --quiet

gcloud projects add-iam-policy-binding "${DATA_PROJECT}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.jobUser" --quiet

# Vertex AI / Gemini
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/aiplatform.user" --quiet

ok "Done. ${SA_EMAIL} is ready for deploy."
echo ""
echo "Next: fill in DEPLOY_SA_EMAIL in .env.deploy, then run:"
echo "  ./deploy.sh"
