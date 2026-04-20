#Requires -Version 5.1

<#
.SYNOPSIS
    Installs or upgrades a Minder release on Windows using Docker Desktop.
.DESCRIPTION
    PowerShell counterpart to install-minder-release.sh. Placeholders
    __REPO_OWNER__, __REPO_NAME__, and __RELEASE_TAG__ are substituted at
    GitHub release publish time by the workflow in
    .github/workflows/release.yml.
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
$ModelsDir   = Get-EnvOrDefault -Name 'MINDER_MODELS_DIR'  -Default (Join-Path $HOME '.minder\models')
$PublicPort  = Get-EnvOrDefault -Name 'MINDER_PORT'        -Default '8800'
$MilvusPort  = Get-EnvOrDefault -Name 'MILVUS_PORT'        -Default '19530'
$OpenAiKey   = Get-EnvOrDefault -Name 'OPENAI_API_KEY'     -Default ''

$ApiImage        = "ghcr.io/$RepoOwner/minder-api:$ReleaseTag"
$DashboardImage  = "ghcr.io/$RepoOwner/minder-dashboard:$ReleaseTag"
$ReleaseBaseUrl  = "https://github.com/$RepoOwner/$RepoName/releases/download/$ReleaseTag"

Require-Command docker

try {
    docker compose version | Out-Null
} catch {
    Write-Error 'docker compose plugin is required.'
    exit 1
}

if (-not (Test-Path $ModelsDir)) {
    Write-Error "Model directory not found: $ModelsDir"
    Write-Error 'Populate ~/.minder/models or set MINDER_MODELS_DIR before running this installer.'
    exit 1
}

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
Write-Host ""
Write-Host "Open:"
Write-Host "  http://localhost:$PublicPort/dashboard/setup"
Write-Host "  http://localhost:$PublicPort/sse"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  docker compose --env-file `"$(Join-Path $InstallDir '.env')`" -f `"$(Join-Path $InstallDir 'docker-compose.yml')`" ps"
Write-Host "  docker compose --env-file `"$(Join-Path $InstallDir '.env')`" -f `"$(Join-Path $InstallDir 'docker-compose.yml')`" logs -f gateway"
