# Retrix - Restart backend (PowerShell)
# Usage: .\restart.ps1

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== Restarting Retrix ===" -ForegroundColor Yellow

# Stop
& "$ProjectRoot\stop.ps1"

Start-Sleep -Seconds 2

# Start
& "$ProjectRoot\start.ps1"
