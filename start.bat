@echo off
REM Retrix - Windows Startup (CMD)
REM For PowerShell: use start.ps1

set MYSQL_BIN=D:\MySQL\MySQL Server 8.0\bin\mysql.exe

echo === Retrix Orchestrator ===

if not exist logs mkdir logs

REM Database
echo Setting up database...
"%MYSQL_BIN%" -h 127.0.0.1 -P 13306 -u root -proh8966 -e "CREATE DATABASE IF NOT EXISTS retrix CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

REM Backend
echo Setting up backend...
cd backend
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
python -c "from app.core.database import engine, Base; from app.models.models import *; Base.metadata.create_all(bind=engine); print('Tables created.')"

echo Starting backend...
start /B "" venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > ..\logs\backend.log 2>&1
cd ..

echo.
echo ===================================
echo   Retrix backend running!
echo   API: http://localhost:8000/api
echo   Dashboard: https://retrix.rebitgames.com
echo ===================================
echo.
echo Caddy: already running as service.
echo If not configured, add retrix-caddy.conf to your Caddyfile and reload.
