# Retrix - Windows Startup Script (PowerShell)
# Usage: .\start.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$LogDir = Join-Path $ProjectRoot "logs"

# ─── Tool Paths (edit if different) ───
$MySqlBin = "D:\MySQL\MySQL Server 8.0\bin\mysql.exe"
$CaddyBin = "D:\SelfHosted\caddy\caddy.exe"

Write-Host "=== Retrix Orchestrator ===" -ForegroundColor Green

if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# ─── Prerequisites ───
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

if (!(Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "  [FAIL] Python not found" -ForegroundColor Red; exit 1
}
if (!(Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Host "  [FAIL] Node.js not found" -ForegroundColor Red; exit 1
}
if (!(Test-Path $MySqlBin)) {
    Write-Host "  [FAIL] MySQL not found at $MySqlBin" -ForegroundColor Red; exit 1
}

# MySQL connection
$mysqlTest = & $MySqlBin -h 127.0.0.1 -P 13306 -u root -proh8966 --batch -e "SELECT 1" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] MySQL not reachable at 127.0.0.1:13306" -ForegroundColor Red; exit 1
}
Write-Host "  [OK] MySQL" -ForegroundColor Green

# Redis
$redisPing = redis-cli -h 127.0.0.1 -p 6379 ping 2>$null
if ($redisPing -ne "PONG") {
    Write-Host "  [FAIL] Redis not reachable at 127.0.0.1:6379" -ForegroundColor Red; exit 1
}
Write-Host "  [OK] Redis" -ForegroundColor Green

# Caddy service
$caddyService = Get-Service -Name "caddy" -ErrorAction SilentlyContinue
if ($caddyService -and $caddyService.Status -eq "Running") {
    Write-Host "  [OK] Caddy service running" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Caddy service not detected - make sure it's running" -ForegroundColor Yellow
}

# ─── Database ───
Write-Host "Setting up database..." -ForegroundColor Yellow
& $MySqlBin -h 127.0.0.1 -P 13306 -u root -proh8966 -e "CREATE DATABASE IF NOT EXISTS retrix CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
Write-Host "Database ready" -ForegroundColor Green

# ─── Backend ───
Write-Host "Setting up backend..." -ForegroundColor Yellow
Set-Location $BackendDir

if (!(Test-Path "venv")) {
    python -m venv venv
}
cmd /c "$BackendDir\venv\Scripts\activate.bat && pip install -r requirements.txt -q"
cmd /c "$BackendDir\venv\Scripts\activate.bat && python -c `"from app.core.database import engine, Base; from app.models.models import *; Base.metadata.create_all(bind=engine); print('Tables created.')`""
Write-Host "Backend ready" -ForegroundColor Green

# ─── Frontend ───
Write-Host "Building frontend..." -ForegroundColor Yellow
Set-Location $FrontendDir

if (!(Test-Path "node_modules")) {
    npm install
}
npm run build
Write-Host "Frontend built" -ForegroundColor Green

# ─── Start Backend ───
Write-Host "Starting backend..." -ForegroundColor Yellow
Set-Location $BackendDir

$backendProcess = Start-Process -FilePath "$BackendDir\venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" `
    -WorkingDirectory $BackendDir `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput "$LogDir\backend.log" `
    -RedirectStandardError "$LogDir\backend-error.log"
$backendProcess.Id | Out-File "$LogDir\backend.pid" -Encoding ascii -Force

Set-Location $ProjectRoot

Write-Host ""
Write-Host "===================================" -ForegroundColor Green
Write-Host "  Retrix backend running!" -ForegroundColor Green
Write-Host "  PID: $($backendProcess.Id)" -ForegroundColor Gray
Write-Host "  API: http://localhost:8000/api" -ForegroundColor Cyan
Write-Host "  Dashboard: https://retrix.rebitgames.com" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Green
Write-Host ""
Write-Host "Caddy: Already running as service." -ForegroundColor Gray
Write-Host "If you haven't added retrix config yet:" -ForegroundColor Yellow
Write-Host "  1. Copy retrix-caddy.conf content into your main Caddyfile" -ForegroundColor Yellow
Write-Host "  2. Reload: & '$CaddyBin' reload --config D:\SelfHosted\caddy\Caddyfile" -ForegroundColor Yellow
