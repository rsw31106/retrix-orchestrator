# Retrix - Stop backend (PowerShell)
# Caddy runs as a service, not managed here.
# Usage: .\stop.ps1

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ProjectRoot "logs"

Write-Host "Stopping Retrix backend..." -ForegroundColor Red

$pidFile = Join-Path $LogDir "backend.pid"
if (Test-Path $pidFile) {
    $pid = (Get-Content $pidFile).Trim()
    try {
        Stop-Process -Id $pid -Force -ErrorAction Stop
        Write-Host "Backend stopped (PID: $pid)" -ForegroundColor Green
    } catch {
        Write-Host "Backend process already stopped" -ForegroundColor Yellow
    }
    Remove-Item $pidFile
} else {
    Write-Host "No PID file found. Trying to find uvicorn..." -ForegroundColor Yellow
    $procs = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*uvicorn*app.main*"
    }
    if ($procs) {
        $procs | Stop-Process -Force
        Write-Host "Killed uvicorn processes" -ForegroundColor Green
    } else {
        Write-Host "No running backend found" -ForegroundColor Yellow
    }
}

Write-Host "Done" -ForegroundColor Green
