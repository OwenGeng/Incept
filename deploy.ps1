# LinglongLab release entry point for PowerShell.
#
# Deployment policy and implementation live in deploy.sh so Windows and Unix
# operators cannot drift onto different product profiles, model sets, image
# tags, or authentication settings. Git for Windows and WSL both provide bash.

param(
    [ValidateSet("api", "web", "both")]
    [string]$Target = "both",

    [Parameter(Mandatory = $true)]
    [string]$Manifest
)

$ErrorActionPreference = "Stop"
$Bash = Get-Command bash -ErrorAction SilentlyContinue
if (-not $Bash) {
    Write-Error "bash is required. Run this from Git Bash/WSL, or use deploy.sh directly."
    exit 1
}

$DeployScript = Join-Path $PSScriptRoot "deploy.sh"
if (-not (Test-Path $DeployScript)) {
    Write-Error "deploy.sh was not found at $DeployScript"
    exit 1
}

& $Bash.Source $DeployScript $Target "--manifest" $Manifest
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
