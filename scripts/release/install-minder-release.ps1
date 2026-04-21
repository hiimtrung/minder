#Requires -Version 5.1

<#
.SYNOPSIS
    Installs or upgrades a Minder release on Windows using Docker Desktop.
.DESCRIPTION
    Installs Ollama (via winget), pulls required models, then deploys
    Minder via Docker Compose. Placeholders __REPO_OWNER__, __REPO_NAME__,
    and __RELEASE_TAG__ are substituted at GitHub release publish time.
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

$InstallDir  = Get-EnvOrDefault -Name 'MINDER_INSTALL_DIR' -Default (Join-Path $HOME ".minder\releases\$ReleaseTag")
$CurrentLink = Get-EnvOrDefault -Name 'MINDER_CURRENT_LINK' -Default (Join-Path $HOME '.minder\current')
$PublicPort  = Get-EnvOrDefault -Name 'MINDER_PORT'        -Default '8800'
$MilvusPort  = Get-EnvOrDefault -Name 'MILVUS_PORT'        -Default '19530'
$OpenAiKey   = Get-EnvOrDefault -Name 'OPENAI_API_KEY'     -Default ''
$LlmModel    = Get-EnvOrDefault -Name 'MINDER_LLM_MODEL'   -Default 'gemma3:4b'
$EmbedModel  = Get-EnvOrDefault -Name 'MINDER_EMBEDDING_MODEL' -Default 'embeddinggemma'

$ApiImage        = "ghcr.io/$RepoOwner/minder-api:$ReleaseTag"
$DashboardImage  = "ghcr.io/$RepoOwner/minder-dashboard:$ReleaseTag"
$ReleaseBaseUrl  = "https://github.com/$RepoOwner/$RepoName/releases/download/$ReleaseTag"

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
# Step 2: Install Ollama if missing
# ------------------------------------------------------------------

if (-not (Get-Command 'ollama' -ErrorAction SilentlyContinue)) {
    Write-Host "Ollama not found. Installing via winget..."
    if (Get-Command 'winget' -ErrorAction SilentlyContinue) {
        & winget install Ollama.Ollama --accept-package-agreements --accept-source-agreements
    } else {
        Write-Error "Please install Ollama manually from https://ollama.com/download"
        exit 1
    }
}

# Wait for Ollama to be ready
Write-Host "Waiting for Ollama to start..."
$ollamaReady = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 3 | Out-Null
        $ollamaReady = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $ollamaReady) {
    Write-Host "Starting Ollama..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 5
    for ($i = 1; $i -le 30; $i++) {
        try {
            Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 3 | Out-Null
            $ollamaReady = $true
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
}

if (-not $ollamaReady) {
    Write-Error "Ollama did not start within 30 seconds."
    exit 1
}

Write-Host "Ollama is running."

# ------------------------------------------------------------------
# Step 3: Pull required models
# ------------------------------------------------------------------

function Pull-OllamaModel {
    param([Parameter(Mandatory = $true)][string]$ModelName)
    Write-Host "Checking model: $ModelName"
    $models = & ollama list 2>$null
    if ($models -match "^$ModelName") {
        Write-Host "  Model $ModelName is already available."
    } else {
        Write-Host "  Pulling $ModelName (this may take a few minutes)..."
        & ollama pull $ModelName
    }
}

Pull-OllamaModel $LlmModel
Pull-OllamaModel $EmbedModel

Write-Host ""
Write-Host "Pre-flight checks:"
Write-Host "  [OK] Docker with Compose plugin"
Write-Host "  [OK] Ollama running at http://localhost:11434"
Write-Host "  [OK] LLM model: $LlmModel"
Write-Host "  [OK] Embedding model: $EmbedModel"
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
MINDER_OLLAMA_URL=http://host.docker.internal:11434
MINDER_LLM_MODEL=$LlmModel
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
Write-Host "Ollama: http://localhost:11434"
Write-Host "LLM model: $LlmModel"
Write-Host "Embedding model: $EmbedModel"
Write-Host ""
Write-Host "Open:"
Write-Host "  http://localhost:$PublicPort/dashboard/setup"
Write-Host "  http://localhost:$PublicPort/sse"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  docker compose --env-file `"$(Join-Path $InstallDir '.env')`" -f `"$(Join-Path $InstallDir 'docker-compose.yml')`" ps"
Write-Host "  docker compose --env-file `"$(Join-Path $InstallDir '.env')`" -f `"$(Join-Path $InstallDir 'docker-compose.yml')`" logs -f gateway"
