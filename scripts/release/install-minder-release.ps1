#Requires -Version 5.1

<#
.SYNOPSIS
    Installs or upgrades a Minder release on Windows using Docker Desktop.
.DESCRIPTION
    Deploys Minder via Docker Compose.
    GGUF models for llama.cpp are downloaded automatically from Hugging Face on first startup.
    No manual model download required.
    Placeholders __REPO_OWNER__, __REPO_NAME__, and __RELEASE_TAG__ are
    substituted at GitHub release publish time.
#>

param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoOwner  = '__REPO_OWNER__'
$RepoName   = '__REPO_NAME__'
$ReleaseTag = '__RELEASE_TAG__'

function Get-EnvOrDefault {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Default
    )
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

function Require-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Error "Missing required command: $Name"
        exit 1
    }
}

$InstallDir    = Get-EnvOrDefault -Name 'MINDER_INSTALL_DIR'      -Default (Join-Path $HOME ".minder\releases\$ReleaseTag")
$CurrentLink   = Get-EnvOrDefault -Name 'MINDER_CURRENT_LINK'     -Default (Join-Path $HOME '.minder\current')
$ModelsDir     = Get-EnvOrDefault -Name 'MINDER_MODELS_DIR'       -Default (Join-Path $HOME '.minder\models')
$PublicPort    = Get-EnvOrDefault -Name 'MINDER_PORT'             -Default '8800'
$OpenAiKey     = Get-EnvOrDefault -Name 'OPENAI_API_KEY'          -Default ''
$LlmModelRepo  = Get-EnvOrDefault -Name 'MINDER_LLM_MODEL_REPO'   -Default 'ggml-org/gemma-4-E2B-it-GGUF'
$EmbedModel    = Get-EnvOrDefault -Name 'MINDER_EMBEDDING_MODEL'  -Default 'ggml-org/embeddinggemma-300M-GGUF'

$ApiImage       = "ghcr.io/$RepoOwner/minder-api:$ReleaseTag"
$DashboardImage = "ghcr.io/$RepoOwner/minder-dashboard:$ReleaseTag"
$ReleaseBaseUrl = "https://github.com/$RepoOwner/$RepoName/releases/download/$ReleaseTag"

# ------------------------------------------------------------------
# Step 1: Verify Docker
# ------------------------------------------------------------------

Require-Command docker

try {
    docker compose version | Out-Null
} catch {
    Write-Error 'docker compose plugin is required.'
    exit 1
}

# ------------------------------------------------------------------
# Step 2: Prepare models directory
# ------------------------------------------------------------------

New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

Write-Host "GGUF models will be downloaded automatically by llama-cpp-python on first startup."
Write-Host "  LLM repo:       $LlmModelRepo"
Write-Host "  Embedding repo: $EmbedModel"

# ------------------------------------------------------------------
# Step 3: Pre-flight summary
# ------------------------------------------------------------------

Write-Host ""
Write-Host "Pre-flight checks:"
Write-Host "  [OK] Docker with Compose plugin"
Write-Host "  [OK] LLM model repo (llama.cpp/GGUF, auto-download): $LlmModelRepo"
Write-Host "  [OK] Embedding model repo (llama.cpp/GGUF, auto-download): $EmbedModel"
Write-Host ""

# ------------------------------------------------------------------
# Step 4: Download release assets and start Docker Compose
# ------------------------------------------------------------------

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$CurrentLinkParent = Split-Path -Parent $CurrentLink
New-Item -ItemType Directory -Force -Path $CurrentLinkParent | Out-Null

Invoke-WebRequest -Uri "$ReleaseBaseUrl/docker-compose.yml" -OutFile (Join-Path $InstallDir 'docker-compose.yml') -UseBasicParsing
Invoke-WebRequest -Uri "$ReleaseBaseUrl/Caddyfile"          -OutFile (Join-Path $InstallDir 'Caddyfile')          -UseBasicParsing

$envContent = @"
MINDER_PORT=$PublicPort
MINDER_API_IMAGE=$ApiImage
MINDER_DASHBOARD_IMAGE=$DashboardImage
MINDER_MODELS_DIR=$ModelsDir
MINDER_LLM_MODEL_REPO=$LlmModelRepo
MINDER_EMBEDDING_MODEL=$EmbedModel
OPENAI_API_KEY=$OpenAiKey
"@
Set-Content -Path (Join-Path $InstallDir '.env') -Value $envContent -Encoding ASCII

$releaseMetadata = [ordered]@{
    repo_owner  = $RepoOwner
    repo_name   = $RepoName
    repository  = "https://github.com/$RepoOwner/$RepoName"
    release_tag = $ReleaseTag
}
$releaseMetadata | ConvertTo-Json -Depth 4 |
    Set-Content -Path (Join-Path $InstallDir '.minder-release.json') -Encoding ASCII

$composeArgs = @(
    'compose',
    '--env-file', (Join-Path $InstallDir '.env'),
    '-f',         (Join-Path $InstallDir 'docker-compose.yml')
)

& docker @composeArgs pull
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& docker @composeArgs up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path $CurrentLink) {
    $existing = Get-Item -LiteralPath $CurrentLink -Force
    if ($existing.LinkType -in @('SymbolicLink', 'Junction')) {
        Remove-Item -LiteralPath $CurrentLink -Force
    } else {
        Write-Warning "Skipping current-link update because $CurrentLink already exists and is not a link."
    }
}
if (-not (Test-Path $CurrentLink)) {
    New-Item -ItemType Junction -Path $CurrentLink -Target $InstallDir | Out-Null
}

Write-Host ""
Write-Host "Minder release $ReleaseTag is starting."
Write-Host ""
Write-Host "Deployment directory: $InstallDir"
Write-Host "Current release link: $CurrentLink"
Write-Host "API image: $ApiImage"
Write-Host "Dashboard image: $DashboardImage"
Write-Host "LLM model repo (llama.cpp/GGUF): $LlmModelRepo"
Write-Host "Embedding model repo (llama.cpp/GGUF): $EmbedModel"
Write-Host ""
Write-Host "Open:"
Write-Host "  http://localhost:$PublicPort/dashboard/setup"
Write-Host "  http://localhost:$PublicPort/sse"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  docker compose --env-file `"$(Join-Path $InstallDir '.env')`" -f `"$(Join-Path $InstallDir 'docker-compose.yml')`" ps"
Write-Host "  docker compose --env-file `"$(Join-Path $InstallDir '.env')`" -f `"$(Join-Path $InstallDir 'docker-compose.yml')`" logs -f gateway"
