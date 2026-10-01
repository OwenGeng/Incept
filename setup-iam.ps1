# =============================================================================
# LinglongLab -- Grant IAM roles to Service Account (run once)
# Usage: .\setup-iam.ps1 your-sa@ads-bpd-guard-sandbox.iam.gserviceaccount.com
# =============================================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$SaEmail
)

$PROJECT_ID   = "ads-bpd-guard-sandbox"
$DATA_PROJECT = "ads-bpd-guard-china"

function Grant {
    param($Project, $Role)
    Write-Host "  Granting $Role on $Project" -ForegroundColor Cyan
    gcloud projects add-iam-policy-binding $Project `
        --member="serviceAccount:$SaEmail" `
        --role=$Role --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Grant may have failed or already exists: $Role @ $Project"
    }
}

Write-Host ""
Write-Host "Granting IAM roles to: $SaEmail" -ForegroundColor Blue
Write-Host ""

# ads-bpd-guard-sandbox: write config.users + run BQ jobs
Grant $PROJECT_ID "roles/bigquery.dataEditor"
Grant $PROJECT_ID "roles/bigquery.jobUser"

# ads-bpd-guard-china: read application data
Grant $DATA_PROJECT "roles/bigquery.dataViewer"
Grant $DATA_PROJECT "roles/bigquery.jobUser"

# Vertex AI / Gemini
Grant $PROJECT_ID "roles/aiplatform.user"

Write-Host ""
Write-Host "Done. Roles granted to $SaEmail" -ForegroundColor Green
Write-Host "Next: run .\deploy.ps1"
