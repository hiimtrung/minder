#Requires -Version 5.1

<#
.SYNOPSIS
    Updates a Minder Windows installation to the latest (or a specific) release.
.DESCRIPTION
    Reads the current installed version from ~/.minder/.minder-release.json,
    downloads the target release installer, and runs it.
.PARAMETER Tag
    Optional. Update to a specific release tag (e.g. v0.7.0).
    If omitted, fetches the latest release from GitHub.
.EXAMPLE
    .\update-minder.ps1
.EXAMPLE
    .\update-minder.ps1 -Tag v0.7.0
#>

param(
    [string]$Tag = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$MinderDir   = Join-Path $HOME '.minder'
$ReleaseMeta = Join-Path $MinderDir '.minder-release.json'

# ------------------------------------------------------------------
# Step 1: Read current installation metadata
# ------------------------------------------------------------------

if (-not (Test-Path $ReleaseMeta)) {
    Write-Error "No Minder installation found at $MinderDir.`nRun the install script first."
    exit 1
}

$meta       = Get-Content $ReleaseMeta -Raw | ConvertFrom-Json
$CurrentTag = $meta.release_tag
$RepoOwner  = $meta.repo_owner
$RepoName   = $meta.repo_name

# ------------------------------------------------------------------
# Step 2: Determine target version
# ------------------------------------------------------------------

if ([string]::IsNullOrWhiteSpace($Tag)) {
    Write-Host "Checking for latest release..."
    $apiUrl = "https://api.github.com/repos/$RepoOwner/$RepoName/releases/latest"
    $latest = Invoke-RestMethod -Uri $apiUrl -UseBasicParsing
    $Tag    = $latest.tag_name
}

if ($CurrentTag -eq $Tag) {
    Write-Host "Already on the latest version: $CurrentTag"
    exit 0
}

Write-Host "Current version: $CurrentTag"
Write-Host "Target version:  $Tag"
Write-Host ""

# ------------------------------------------------------------------
# Step 3: Download and run the new installer
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

Write-Host ""
Write-Host "Update complete: $CurrentTag → $Tag"
