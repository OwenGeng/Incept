# =============================================================================
# NBSpark -- Cloud Run deploy script (Windows PowerShell)
#
# Services:
#   nbs-api     -- Unified FastAPI backend (InterSight + Incept)
#   nbs-portal  -- Next.js web app (unified portal)
#
# Usage:
#   .\deploy.ps1          # deploy nbs-api + nbs-portal  (default)
#   .\deploy.ps1 api      # deploy nbs-api only
#   .\deploy.ps1 web      # deploy nbs-portal only
#   .\deploy.ps1 all      # deploy both (same as default)
#
# Requires: gcloud CLI, Docker Desktop running, .env.deploy filled in.
# =============================================================================

param(
    [string]$Target = "both"
)

# -- Load .env.deploy ----------------------------------------------------------
$EnvFile = Join-Path $PSScriptRoot ".env.deploy"
if (-not (Test-Path $EnvFile)) {
    Write-Error ".env.deploy not found. Please create it from .env.deploy.example"
    exit 1
}

$EnvVars = @{}
Get-Content $EnvFile | Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' } | ForEach-Object {
    $parts = $_ -split '=', 2
    if ($parts.Length -eq 2) {
        $EnvVars[$parts[0].Trim()] = $parts[1].Trim()
    }
}

foreach ($kv in $EnvVars.GetEnumerator()) {
    Set-Item -Path "Env:$($kv.Key)" -Value $kv.Value
}

# -- Validate required vars ----------------------------------------------------
$Required = @(
    "DEPLOY_SA_EMAIL", "GCP_PROJECT_DEPLOY", "INTERSIGHT_INTERNAL_API_KEY",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "AUTH_SECRET"
)
foreach ($v in $Required) {
    if (-not $EnvVars.ContainsKey($v) -or [string]::IsNullOrWhiteSpace($EnvVars[$v])) {
        Write-Error "Missing required variable: $v -- check .env.deploy"
        exit 1
    }
}

# -- Config --------------------------------------------------------------------
$PROJECT_ID        = $EnvVars["GCP_PROJECT_DEPLOY"]
$REGION            = if ($EnvVars.ContainsKey("REGION")) { $EnvVars["REGION"] } else { "asia-northeast1" }
$REPO              = "intersight"
$AR_HOST           = "$REGION-docker.pkg.dev"

$API_SERVICE       = "nbs-api"
$WEB_SERVICE       = "nbs-portal"
$API_IMAGE         = "$AR_HOST/$PROJECT_ID/$REPO/nbs-api"
$WEB_IMAGE         = "$AR_HOST/$PROJECT_ID/$REPO/web"

$SA          = $EnvVars["DEPLOY_SA_EMAIL"]
$API_KEY     = $EnvVars["INTERSIGHT_INTERNAL_API_KEY"]
$BQ_WRITE    = $EnvVars["BQ_WRITE_PROJECT"]
$BQ_READ     = $EnvVars["BQ_READ_PROJECT"]
$BQ_DATA     = $EnvVars["GCP_PROJECT_DATA"]
$GC_ID       = $EnvVars["GOOGLE_CLIENT_ID"]
$GC_SECRET   = $EnvVars["GOOGLE_CLIENT_SECRET"]
$AUTH_SEC    = $EnvVars["AUTH_SECRET"]

$TmpApiUrl         = Join-Path $PSScriptRoot ".api-url.tmp"

# -- Helpers -------------------------------------------------------------------
function Log  { param($msg) Write-Host "`n>>  $msg" -ForegroundColor Blue }
function Ok   { param($msg) Write-Host "OK  $msg" -ForegroundColor Green }
function Err  { param($msg) Write-Host "ERR $msg" -ForegroundColor Red; exit 1 }

function Invoke-Gcloud {
    param([string[]]$Cmd)
    & gcloud @Cmd
    if ($LASTEXITCODE -ne 0) { Err "gcloud failed (exit $LASTEXITCODE)" }
}

function Invoke-Docker {
    param([string[]]$Cmd)
    & docker @Cmd
    if ($LASTEXITCODE -ne 0) { Err "docker failed (exit $LASTEXITCODE)" }
}

# -- Ensure Artifact Registry repo exists -------------------------------------
function Ensure-ArRepo {
    Log "Checking Artifact Registry repo '$REPO'..."

    # Suppress ALL output (stdout + stderr) so gcloud NOT_FOUND doesn't crash PS
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    gcloud artifacts repositories describe $REPO `
        --project=$PROJECT_ID --location=$REGION 2>&1 | Out-Null
    $found = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev

    if (-not $found) {
        Log "Repo not found -- creating '$REPO'..."
        Invoke-Gcloud @(
            "artifacts", "repositories", "create", $REPO,
            "--project=$PROJECT_ID", "--location=$REGION",
            "--repository-format=docker", "--description=InterSight images"
        )
    }
    Invoke-Gcloud @("auth", "configure-docker", $AR_HOST, "--quiet")
    Ok "Artifact Registry ready: $AR_HOST/$PROJECT_ID/$REPO"
}

# =============================================================================
# Deploy NBS API (unified FastAPI — InterSight + Incept)
# =============================================================================
function Deploy-Api {
    Log "Building NBS API image (context: repo root, Dockerfile: Dockerfile.nbs-api)..."
    Invoke-Docker @(
        "build", "--platform", "linux/amd64",
        "-f", (Join-Path $PSScriptRoot "Dockerfile.nbs-api"),
        "-t", "${API_IMAGE}:latest",
        $PSScriptRoot
    )

    Log "Pushing NBS API image..."
    Invoke-Docker @("push", "${API_IMAGE}:latest")

    Log "Deploying NBS API to Cloud Run ($REGION)..."

    # Read OPENAI_API_KEY from .env.deploy (optional — Incept may use Gemini only)
    $openaiKey = if ($EnvVars.ContainsKey("OPENAI_API_KEY")) { $EnvVars["OPENAI_API_KEY"] } else { "" }

    $envVarStr = (
        "INTERSIGHT_ENV=production,INTERSIGHT_API_MODE=live," +
        "INCEPT_ENV=production,AUTH_MODE=iap," +
        "GCP_PROJECT_DEPLOY=$PROJECT_ID,GOOGLE_CLOUD_PROJECT=$PROJECT_ID," +
        "GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_ENTERPRISE=true," +
        "GCP_PROJECT_ID=$PROJECT_ID,GCP_LOCATION=us-central1," +
        "GEMINI_MODEL=gemini-3.6-flash," +
        "VERTEX_GEMINI_ENABLED=true,VERTEX_AI_ENABLED=true," +
        "DEFAULT_IMAGE_PROVIDER=gemini," +
        "BQ_WRITE_PROJECT=$BQ_WRITE,BQ_READ_PROJECT=$BQ_READ," +
        "GCP_PROJECT_DATA=$BQ_DATA," +
        "INTERSIGHT_INTERNAL_API_KEY=$API_KEY," +
        "INTERSIGHT_PROJECT_ROOT=/app," +
        "OPENAI_API_KEY=$openaiKey," +
        "CORS_ALLOW_ORIGINS=http://localhost:3000"
    )

    Invoke-Gcloud @(
        "run", "deploy", $API_SERVICE,
        "--image=${API_IMAGE}:latest",
        "--project=$PROJECT_ID", "--region=$REGION",
        "--platform=managed", "--service-account=$SA",
        "--no-allow-unauthenticated",
        "--min-instances=1", "--max-instances=3",
        "--memory=2Gi", "--cpu=1",
        "--timeout=300", "--concurrency=40",
        "--set-env-vars=$envVarStr"
    )

    $apiUrl = (gcloud run services describe $API_SERVICE `
        --project=$PROJECT_ID --region=$REGION `
        --format="value(status.url)").Trim()

    Ok "NBS API live --> $apiUrl"
    Write-Host ""
    Write-Host "  NOTE: Ask a GCP admin to run this once to make API callable by the web service:" -ForegroundColor Yellow
    Write-Host "  gcloud run services add-iam-policy-binding nbs-api --region=$REGION --project=$PROJECT_ID --member=serviceAccount:$SA --role=roles/run.invoker" -ForegroundColor Yellow
    $apiUrl | Out-File -FilePath $TmpApiUrl -Encoding utf8 -NoNewline
}

# =============================================================================
# Deploy Web (Next.js)
# =============================================================================
function Deploy-Web {
    # Resolve API URL
    if (Test-Path $TmpApiUrl) {
        $apiUrl = (Get-Content $TmpApiUrl -Raw).Trim()
    } else {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        $apiUrl = (gcloud run services describe $API_SERVICE `
            --project=$PROJECT_ID --region=$REGION `
            --format="value(status.url)" 2>&1) -join "" | ForEach-Object { $_.Trim() }
        $ErrorActionPreference = $prev
        if ($LASTEXITCODE -ne 0) { $apiUrl = "" }
    }
    if ([string]::IsNullOrWhiteSpace($apiUrl)) {
        Err "API service not found. Deploy API first: .\deploy.ps1 api"
    }

    Log "Building Web image (context: repo root, Dockerfile: Dockerfile.web)..."
    Invoke-Docker @(
        "build", "--platform", "linux/amd64",
        "-f", (Join-Path $PSScriptRoot "Dockerfile.web"),
        "-t", "${WEB_IMAGE}:latest",
        $PSScriptRoot
    )

    Log "Pushing Web image..."
    Invoke-Docker @("push", "${WEB_IMAGE}:latest")

    Log "Deploying Web (nbs-portal) to Cloud Run ($REGION)..."
    $envVarStr = (
        "NODE_ENV=production,NEXT_TELEMETRY_DISABLED=1," +
        "API_BASE_URL=$apiUrl," +
        "INCEPT_API_BASE_URL=$apiUrl," +
        "INTERSIGHT_INTERNAL_API_KEY=$API_KEY," +
        "GOOGLE_CLIENT_ID=$GC_ID," +
        "GOOGLE_CLIENT_SECRET=$GC_SECRET," +
        "AUTH_SECRET=$AUTH_SEC," +
        "NEXTAUTH_URL=https://placeholder.example.com"
    )

    Invoke-Gcloud @(
        "run", "deploy", $WEB_SERVICE,
        "--image=${WEB_IMAGE}:latest",
        "--project=$PROJECT_ID", "--region=$REGION",
        "--platform=managed", "--service-account=$SA",
        "--allow-unauthenticated",
        "--min-instances=0", "--max-instances=5",
        "--memory=512Mi", "--cpu=1",
        "--timeout=30", "--concurrency=100",
        "--set-env-vars=$envVarStr"
    )

    $webUrl = (gcloud run services describe $WEB_SERVICE `
        --project=$PROJECT_ID --region=$REGION `
        --format="value(status.url)").Trim()

    Ok "Web deployed (pass 1) --> $webUrl"

    # Patch NEXTAUTH_URL with real URL
    Log "Patching NEXTAUTH_URL..."
    Invoke-Gcloud @(
        "run", "services", "update", $WEB_SERVICE,
        "--project=$PROJECT_ID", "--region=$REGION",
        "--update-env-vars=NEXTAUTH_URL=$webUrl", "--quiet"
    )

    # Update nbs-api CORS (allow both production URL and localhost)
    Log "Updating nbs-api CORS_ALLOW_ORIGINS..."
    Invoke-Gcloud @(
        "run", "services", "update", $API_SERVICE,
        "--project=$PROJECT_ID", "--region=$REGION",
        # ^|^ changes the key=value pair delimiter from comma to pipe,
        # allowing commas inside the value (the list of allowed origins).
        "--update-env-vars=^|^CORS_ALLOW_ORIGINS=$webUrl,http://localhost:3000", "--quiet"
    )

    # Write real NEXTAUTH_URL back to .env.deploy for future redeploys
    $content = Get-Content $EnvFile -Raw
    $content = $content -replace 'NEXTAUTH_URL=.*', "NEXTAUTH_URL=$webUrl"
    [System.IO.File]::WriteAllText($EnvFile, $content, [System.Text.Encoding]::UTF8)

    # Cleanup
    if (Test-Path $TmpApiUrl) { Remove-Item $TmpApiUrl }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  NBSpark is live!" -ForegroundColor Green
    Write-Host "  nbs-api    : $apiUrl" -ForegroundColor Green
    Write-Host "  nbs-portal : $webUrl" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  ACTION REQUIRED -- add this to Google OAuth redirect URIs:" -ForegroundColor Yellow
    Write-Host "  $webUrl/api/auth/callback/google" -ForegroundColor Yellow
    Write-Host ""
}

# -- Main ----------------------------------------------------------------------
Ensure-ArRepo

switch ($Target.ToLower()) {
    "api"    { Deploy-Api }
    "web"    { Deploy-Web }
    "both"   { Deploy-Api; Deploy-Web }
    "all"    { Deploy-Api; Deploy-Web }
    default  { Err "Unknown target '$Target'. Use: api / web / both / all" }
}
