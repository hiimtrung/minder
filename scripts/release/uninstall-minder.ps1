#Requires -Version 5.1

<#
.SYNOPSIS
    Uninstalls Minder from Windows.
.DESCRIPTION
    Stops all Minder Docker containers and removes release directories.
    With -KeepData, preserves downloaded models and Docker volumes.
.PARAMETER KeepData
    Keep downloaded models, Docker volumes, and config files.
    Only removes containers and release directories.
.EXAMPLE
    .\uninstall-minder.ps1
.EXAMPLE
    .\uninstall-minder.ps1 -KeepData
#>

param(
    [switch]$KeepData
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$MinderDir   = Join-Path $HOME '.minder'
$CurrentLink = Join-Path $MinderDir 'current'
$ReleasesDir = Join-Path $MinderDir 'releases'

# ------------------------------------------------------------------
# Step 1: Stop and remove Minder Docker containers
# ------------------------------------------------------------------

Write-Host "Stopping Minder containers..."

if (Test-Path $CurrentLink) {
    $installDir  = (Get-Item -LiteralPath $CurrentLink -Force).Target
    $composeFile = Join-Path $installDir 'docker-compose.yml'
    if (Test-Path $composeFile) {
        $envFile     = Join-Path $installDir '.env'
        $composeArgs = @('compose', '--env-file', $envFile, '-f', $composeFile, 'down')
        & docker @composeArgs 2>$null
    }
}

# Also sweep all release directories in case the symlink is broken
if (Test-Path $ReleasesDir) {
    Get-ChildItem -Path $ReleasesDir -Directory | ForEach-Object {
        $composeFile = Join-Path $_.FullName 'docker-compose.yml'
        if (Test-Path $composeFile) {
            $envFile     = Join-Path $_.FullName '.env'
            $composeArgs = @('compose', '--env-file', $envFile, '-f', $composeFile, 'down')
            & docker @composeArgs 2>$null
        }
    }
}

Write-Host "Minder containers stopped."

# ------------------------------------------------------------------
# Step 2: Remove release directories and current link
# ------------------------------------------------------------------

Write-Host "Removing release directories..."

if (Test-Path $ReleasesDir) { Remove-Item -Recurse -Force $ReleasesDir }
if (Test-Path $CurrentLink) { Remove-Item -LiteralPath $CurrentLink -Force }

if ($KeepData) {
    Write-Host ""
    Write-Host "Uninstall complete (-KeepData mode)."
    Write-Host ""
    Write-Host "Kept:"
    Write-Host "  - Downloaded models"
    Write-Host "  - Docker volumes (mongodb-data, redis-data, milvus-data, etc.)"
    Write-Host "  - Config files in $MinderDir\"
    Write-Host ""
    Write-Host "To remove Docker volumes manually:"
    Write-Host "  docker volume ls | Select-String 'minder|mongodb|redis|milvus'"
    Write-Host "  docker volume rm <volume-name>"
    exit 0
}

# ------------------------------------------------------------------
# Step 3: Full cleanup (only when -KeepData is NOT set)
# ------------------------------------------------------------------

Write-Host "Removing Docker volumes..."
$volumes = docker volume ls -q 2>$null | Where-Object { $_ -match 'mongodb|redis|milvus|etcd|minio' }
foreach ($vol in $volumes) {
    Write-Host "  Removing volume: $vol"
    docker volume rm $vol 2>$null
}

Write-Host "Removing Minder config directory..."
if (Test-Path $MinderDir) { Remove-Item -Recurse -Force $MinderDir }

Write-Host ""
Write-Host "Minder has been fully uninstalled."
Write-Host "  - All containers stopped and removed"
Write-Host "  - Docker volumes removed"
Write-Host "  - Config directory removed: $MinderDir"
