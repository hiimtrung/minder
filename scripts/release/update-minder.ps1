#Requires -Version 5.1

<#
.SYNOPSIS
    Updates a running Minder deployment to the latest (or a specific) release.
.DESCRIPTION
    Reads the current installed version, downloads the target release installer,
    runs it (which replaces containers in-place via docker compose up -d), then
    notes the old release directory for manual cleanup.
.PARAMETER Tag
    Optional. Update to a specific release tag (e.g. v0.4.0).
    If omitted, fetches the latest release from GitHub.
.EXAMPLE
    .\update-minder.ps1
.EXAMPLE
    .\update-minder.ps1 -Tag v0.4.0
#>

param(
    [string]$Tag = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$MinderDir   = Join-Path $HOME '.minder'
$CurrentLink = Join-Path $MinderDir 'current'

# ------------------------------------------------------------------
# Step 1: Determine current and target versions
# ------------------------------------------------------------------

$CurrentTag = ''
if (Test-Path $CurrentLink) {
    $resolvedCurrent = (Get-Item -LiteralPath $CurrentLink -Force).Target
    $releaseJson = Join-Path $resolvedCurrent '.minder-release.json'
    if (Test-Path $releaseJson) {
        $meta = Get-Content $releaseJson -Raw | ConvertFrom-Json
        $CurrentTag = $meta.release_tag
    }
}

if ([string]::IsNullOrWhiteSpace($CurrentTag)) {
    Write-Error "No current Minder installation found at $CurrentLink`nRun the install script first."
    exit 1
}

$meta      = Get-Content (Join-Path (Get-Item -LiteralPath $CurrentLink -Force).Target '.minder-release.json') -Raw | ConvertFrom-Json
$RepoOwner = $meta.repo_owner
$RepoName  = $meta.repo_name

if ([string]::IsNullOrWhiteSpace($Tag)) {
    Write-Host "Checking for latest release..."
    $apiUrl = "https://api.github.com/repos/$RepoOwner/$RepoName/releases/latest"
    $latest = Invoke-RestMethod -Uri $apiUrl -UseBasicParsing
    $Tag = $latest.tag_name
}

if ($CurrentTag -eq $Tag) {
    Write-Host "Already running the latest version: $CurrentTag"
    exit 0
}

Write-Host "Current version: $CurrentTag"
Write-Host "Target version:  $Tag"
Write-Host ""

# ------------------------------------------------------------------
# Step 2: Download and run the new installer
# ------------------------------------------------------------------

$installerUrl  = "https://github.com/$RepoOwner/$RepoName/releases/download/$Tag/install-minder-$Tag.ps1"
$tempInstaller = Join-Path ([System.IO.Path]::GetTempPath()) "install-minder-$Tag.ps1"

Write-Host "Downloading installer for $Tag..."
Invoke-WebRequest -Uri $installerUrl -OutFile $tempInstaller -UseBasicParsing

Write-Host "Running installer..."
& powershell -ExecutionPolicy Bypass -File $tempInstaller
$exitCode = $LASTEXITCODE
Remove-Item -LiteralPath $tempInstaller -Force -ErrorAction SilentlyContinue
if ($exitCode -ne 0) { exit $exitCode }

# ------------------------------------------------------------------
# Step 3: Note old release directory — do NOT docker compose down
# ------------------------------------------------------------------
#
# docker-compose.yml uses `name: minder` as the project name, so both the
# old and new releases share the same Compose project. The installer already
# ran `docker compose up -d` which recreated containers in-place with the new
# images. Running `down` on the old compose file would tear down those same
# new containers.

$OldDir = Join-Path $MinderDir "releases\$CurrentTag"
if (Test-Path $OldDir) {
    $currentResolved = (Get-Item -LiteralPath $CurrentLink -Force).Target
    if ($OldDir -ne $currentResolved) {
        Write-Host ""
        Write-Host "Old release files kept at: $OldDir"
        Write-Host "To remove them: Remove-Item -Recurse -Force `"$OldDir`""
    }
}

Write-Host ""
Write-Host "Update complete: $CurrentTag -> $Tag"
