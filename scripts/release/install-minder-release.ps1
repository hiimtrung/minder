#Requires -Version 5.1

<#
.SYNOPSIS
    Installs or upgrades a Minder release on Windows using Docker Desktop.
.DESCRIPTION
    Downloads the LiteRT-LM model, then deploys Minder via Docker Compose.
    The embedding model (mixedbread-ai/mxbai-embed-large-v1) is downloaded automatically
    by FastEmbed — no host-native or Docker Ollama installation required.
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
$MilvusPort    = Get-EnvOrDefault -Name 'MILVUS_PORT'             -Default '19530'
$OpenAiKey     = Get-EnvOrDefault -Name 'OPENAI_API_KEY'          -Default ''
$EmbedModel    = Get-EnvOrDefault -Name 'MINDER_EMBEDDING_MODEL'  -Default 'mixedbread-ai/mxbai-embed-large-v1'
$LiteRTModelUrl = Get-EnvOrDefault -Name 'MINDER_LITERT_MODEL_URL' `
    -Default 'https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it.litertlm?download=true'
$LiteRTModelFile = 'gemma-4-E2B-it.litertlm'

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
# Step 2: Download LiteRT-LM model
# ------------------------------------------------------------------

New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
$LiteRTModelPath = Join-Path $ModelsDir $LiteRTModelFile

if (Test-Path $LiteRTModelPath) {
    Write-Host "LiteRT-LM model already exists: $LiteRTModelPath"
} else {
    Write-Host "Downloading LiteRT-LM model (this may take a few minutes)..."
    Invoke-WebRequest -Uri $LiteRTModelUrl -OutFile $LiteRTModelPath -UseBasicParsing
}

Write-Host "LiteRT-LM model ready."

# ------------------------------------------------------------------
# Step 3: Pre-flight summary
# ------------------------------------------------------------------

Write-Host ""
Write-Host "Pre-flight checks:"
Write-Host "  [OK] Docker with Compose plugin"
Write-Host "  [OK] LiteRT-LM model: $LiteRTModelFile"
Write-Host "  [OK] Embedding model (FastEmbed): $EmbedModel"
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
MILVUS_PORT=$MilvusPort
MINDER_API_IMAGE=$ApiImage
MINDER_DASHBOARD_IMAGE=$DashboardImage
MINDER_MODELS_DIR=$ModelsDir
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
Write-Host "LiteRT-LM model: $LiteRTModelPath"
Write-Host "Embedding: FastEmbed ($EmbedModel)"
Write-Host ""
Write-Host "Open:"
Write-Host "  http://localhost:$PublicPort/dashboard/setup"
Write-Host "  http://localhost:$PublicPort/sse"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  docker compose --env-file `"$(Join-Path $InstallDir '.env')`" -f `"$(Join-Path $InstallDir 'docker-compose.yml')`" ps"
Write-Host "  docker compose --env-file `"$(Join-Path $InstallDir '.env')`" -f `"$(Join-Path $InstallDir 'docker-compose.yml')`" logs -f gateway"
