@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0
set PIDFILE=!ROOT!logs\backend.pid

echo === Stopping Retrix ===

set OLD_PID=
if exist "!PIDFILE!" (
    for /f "usebackq tokens=* delims=" %%i in ("!PIDFILE!") do set OLD_PID=%%i
)

if defined OLD_PID (
    taskkill /PID !OLD_PID! /F /T >nul 2>&1
    echo Backend stopped (PID: !OLD_PID!)
    del "!PIDFILE!" >nul 2>&1
)

powershell -NoProfile -Command "Get-WmiObject Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('Killed PID ' + $_.ProcessId) }"

echo Done.
endlocal
