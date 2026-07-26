# ==============================================================================
# VCC - Direct PC to Raspberry Pi Sync Script (No GitHub Required)
# ==============================================================================
param (
    [Parameter(Mandatory=$true)]
    [string]$PiIP,

    [string]$PiUser = "pi",
    
    [string]$PiPath = "/home/pi/VCC"
)

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " Syncing VCC Project directly to Raspberry Pi ($PiUser@$PiIP:$PiPath)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Create remote target directory if it doesn't exist
Write-Host "[1/3] Ensuring target directory exists on Raspberry Pi..." -ForegroundColor Yellow
ssh "${PiUser}@${PiIP}" "mkdir -p ${PiPath}"

# 2. Exclude pattern for tar archive transfer
$Excludes = @(
    "--exclude=.git",
    "--exclude=node_modules",
    "--exclude=venv",
    "--exclude=.venv",
    "--exclude=__pycache__",
    "--exclude=*.pyc",
    "--exclude=*.db",
    "--exclude=*.db-wal",
    "--exclude=*.db-shm",
    "--exclude=dist"
)

# 3. Create a temporary tarball of the current folder and stream directly via SSH
Write-Host "[2/3] Packing and transferring project files to Raspberry Pi..." -ForegroundColor Yellow
$TarCmd = "tar -czf - $Excludes ."

# Stream tar from local Windows tar.exe straight to SSH on the Pi
& tar -czf - --exclude=.git --exclude=node_modules --exclude=venv --exclude=__pycache__ --exclude=*.db --exclude=dist . | ssh "${PiUser}@${PiIP}" "tar -xzf - -C ${PiPath}"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[3/3] Files synced successfully!" -ForegroundColor Green
    Write-Host "Rebuilding and restarting Docker container on Raspberry Pi..." -ForegroundColor Yellow
    ssh "${PiUser}@${PiIP}" "cd ${PiPath} && docker compose up -d --build"
    Write-Host "======================================================================" -ForegroundColor Green
    Write-Host " SUCCESS! VCC is updated and running on Raspberry Pi at http://${PiIP}/" -ForegroundColor Green
    Write-Host "======================================================================" -ForegroundColor Green
} else {
    Write-Host "[!] Sync failed. Please verify SSH connectivity to ${PiUser}@${PiIP}." -ForegroundColor Red
}
