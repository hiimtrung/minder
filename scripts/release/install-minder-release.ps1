#Requires -Version 5.1

<#
.SYNOPSIS
    Installs Minder on Windows as a headless Python server (no Docker required).
.DESCRIPTION
    Downloads and installs minder-cli via uv, then starts the Minder server.
    Placeholders __REPO_OWNER__, __REPO_NAME__, and __RELEASE_TAG__ are
    substituted at GitHub release publish time.
.NOTES
    A native Windows desktop app (MSIX/exe) is not yet included in this release.
    The headless server works via uv + Python and runs on port 8800.
#>

param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoOwner  = '__REPO_OWNER__'
$RepoName   = '__REPO_NAME__'
$ReleaseTag = '__RELEASE_TAG__'
$Version    = $ReleaseTag -replace '^v', ''

$MinderDir = Join-Path $HOME '.minder'

function Get-EnvOrDefault {
    param([string]$Name, [string]$Default)
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Error "Missing required command: $Name. Install uv from https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    }
}

$LlmModelRepo  = Get-EnvOrDefault -Name 'MINDER_LLM_MODEL_REPO'  -Default 'unsloth/Qwen3.5-2B-GGUF'
$EmbedModel    = Get-EnvOrDefault -Name 'MINDER_EMBEDDING_MODEL' -Default 'ggml-org/embeddinggemma-300M-GGUF'

# ------------------------------------------------------------------
# Step 1: Verify uv is available
# ------------------------------------------------------------------

Require-Command uv

# ------------------------------------------------------------------
# Step 2: Install minder-cli from PyPI
# ------------------------------------------------------------------

Write-Host ""
Write-Host "Installing minder-cli $Version via uv..."
& uv tool install "minder-cli==$Version" --force
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# ------------------------------------------------------------------
# Step 3: Save release metadata
# ------------------------------------------------------------------

New-Item -ItemType Directory -Force -Path $MinderDir | Out-Null

$meta = [ordered]@{
    repo_owner  = $RepoOwner
    repo_name   = $RepoName
    repository  = "https://github.com/$RepoOwner/$RepoName"
    release_tag = $ReleaseTag
}
$meta | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $MinderDir '.minder-release.json') -Encoding ASCII

# ------------------------------------------------------------------
# Step 4: Summary
# ------------------------------------------------------------------

Write-Host ""
Write-Host "Minder $ReleaseTag installed."
Write-Host ""
Write-Host "Start the server:"
Write-Host "  uv run python -m minder.server"
Write-Host ""
Write-Host "Or install dependencies and run:"
Write-Host "  uv tool install minder-cli"
Write-Host "  uv run python -m minder.server"
Write-Host ""
Write-Host "Dashboard: http://localhost:8800/dashboard/setup"
Write-Host "MCP SSE:   http://localhost:8800/sse"
Write-Host ""
Write-Host "LLM model:       $LlmModelRepo"
Write-Host "Embedding model: $EmbedModel"
Write-Host "(Models download automatically from HuggingFace on first startup.)"
