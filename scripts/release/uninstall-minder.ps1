#Requires -Version 5.1

<#
.SYNOPSIS
    Uninstalls Minder from Windows.
.DESCRIPTION
    Removes the minder-cli uv tool installation and optionally the data directory.
.PARAMETER KeepData
    Keep downloaded models and config files in ~/.minder/.
    Only removes the minder-cli tool installation.
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

$MinderDir = Join-Path $HOME '.minder'

# ------------------------------------------------------------------
# Step 1: Remove Minder Desktop App (NSIS installer) if exists
# ------------------------------------------------------------------

$Uninstaller = Join-Path $env:LOCALAPPDATA "Programs\Minder\Uninstall.exe"
if (-not (Test-Path $Uninstaller)) {
    $Uninstaller = Join-Path $env:ProgramFiles "Minder\Uninstall.exe"
}

if (Test-Path $Uninstaller) {
    Write-Host "Minder Desktop App detected. Launching uninstaller..."
    Start-Process -FilePath $Uninstaller -Wait
    Write-Host "Desktop App uninstallation completed."
} else {
    Write-Host "Minder Desktop App uninstaller not found (skipping)."
}

# ------------------------------------------------------------------
# Step 2: Remove minder-cli uv tool
# ------------------------------------------------------------------

Write-Host "Removing minder-cli..."

if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv tool uninstall minder-cli 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "minder-cli removed."
    } else {
        Write-Host "minder-cli was not installed via uv (skipping)."
    }
} else {
    Write-Host "uv not found — skipping minder-cli removal."
}

# ------------------------------------------------------------------
# Step 3: Handle data directory
# ------------------------------------------------------------------

if ($KeepData) {
    Write-Host ""
    Write-Host "Minder uninstalled (-KeepData mode)."
    Write-Host ""
    Write-Host "Kept:"
    Write-Host "  - Downloaded models and data in $MinderDir\"
    Write-Host ""
    Write-Host "To remove data later:"
    Write-Host "  Remove-Item -Recurse -Force `"$MinderDir`""
    exit 0
}

if (Test-Path $MinderDir) {
    Write-Host "Removing Minder data directory: $MinderDir..."
    Remove-Item -Recurse -Force $MinderDir
}

Write-Host ""
Write-Host "Minder fully uninstalled."
Write-Host "  - minder-cli removed"
Write-Host "  - Data directory removed: $MinderDir"
