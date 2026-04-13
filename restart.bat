@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0
set BACKEND_DIR=!ROOT!backend
set FRONTEND_DIR=!ROOT!frontend
set LOG_DIR=!ROOT!logs
set PIDFILE=!LOG_DIR!\backend.pid

echo === Retrix Restart ===

REM --- [1/5] Stop backend ---
echo [1/5] Stopping backend...

set OLD_PID=
if exist "!PIDFILE!" (
    for /f "usebackq tokens=* delims=" %%i in ("!PIDFILE!") do set OLD_PID=%%i
)

if defined OLD_PID (
    taskkill /PID !OLD_PID! /F /T >nul 2>&1
    echo      Stopped PID !OLD_PID!
    del "!PIDFILE!" >nul 2>&1
)

powershell -NoProfile -Command "Get-WmiObject Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('  Killed PID ' + $_.ProcessId) }"

powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 0 } | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue; Write-Host ('  Freed port 8000 from PID ' + $_) }"

timeout /t 2 /nobreak >nul
echo      Done.

REM --- [2/5] Build frontend ---
echo [2/5] Building frontend...
cd /d "!FRONTEND_DIR!"
if not exist "node_modules" (
    echo      Running npm install...
    call npm install
)
call npm run build
set BUILD_ERR=!ERRORLEVEL!
echo      Build exit code: !BUILD_ERR!
if !BUILD_ERR! NEQ 0 ( echo [FAIL] Frontend build failed & exit /b 1 )
echo      Frontend built OK

REM --- [3/5] Install backend deps ---
echo [3/5] Installing backend dependencies...
cd /d "!BACKEND_DIR!"
if not exist "venv" (
    echo      Creating venv...
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
if !ERRORLEVEL! NEQ 0 ( echo [FAIL] pip install failed & exit /b 1 )
echo      Backend deps OK

REM --- [4/5] DB migration ---
echo [4/5] Running DB migration...
python -c "from app.core.database import engine, Base; from app.models.models import *; Base.metadata.create_all(bind=engine); print('     Tables OK')"
if !ERRORLEVEL! NEQ 0 ( echo [FAIL] DB migration failed & exit /b 1 )

REM --- [5/5] Start backend ---
echo [5/5] Starting backend...
if not exist "!LOG_DIR!" mkdir "!LOG_DIR!"

powershell -NoProfile -ExecutionPolicy Bypass -File "!ROOT!start_backend.ps1" -BackendDir "!BACKEND_DIR!" -LogDir "!LOG_DIR!"

if !ERRORLEVEL! NEQ 0 ( echo [FAIL] Backend failed to start & exit /b 1 )

timeout /t 3 /nobreak >nul

set NEW_PID=
if exist "!PIDFILE!" (
    for /f "usebackq tokens=* delims=" %%i in ("!PIDFILE!") do set NEW_PID=%%i
)

if not defined NEW_PID (
    echo [FAIL] Backend did not write PID file. Check logs\backend-error.log
    exit /b 1
)

echo      Backend started (PID: !NEW_PID!)

cd /d "!ROOT!"
echo.
echo === Retrix is running ===
echo   PID  : !NEW_PID!
echo   API  : http://localhost:8000/api
echo   Logs : !LOG_DIR!\backend-error.log

endlocal
