# Retrix - AI Project Orchestrator

## Prerequisites
- Python 3.11+
- Node.js 18+
- MySQL 8 (`D:\MySQL\MySQL Server 8.0\bin`) — port 13306
- Redis — port 6379
- Caddy (`D:\SelfHosted\caddy`) — already running as service

## Setup

```powershell
cd retrix

# 1. API 키 채우기
notepad backend\.env

# 2. Backend
cd backend
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt

# 3. DB 생성 + 테이블
& "D:\MySQL\MySQL Server 8.0\bin\mysql.exe" -h 127.0.0.1 -P 13306 -u root -proh8966 -e "CREATE DATABASE IF NOT EXISTS retrix CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
python -c "from app.core.database import engine, Base; from app.models.models import *; Base.metadata.create_all(bind=engine)"

# 4. Frontend
cd ..\frontend
npm install
npm run build

# 5. Caddy 설정 추가
#    retrix-caddy.conf 내용을 D:\SelfHosted\caddy\Caddyfile에 추가
#    경로(root *)를 실제 frontend\dist 위치로 수정
& "D:\SelfHosted\caddy\caddy.exe" reload --config D:\SelfHosted\caddy\Caddyfile

# 6. 시작
cd ..
.\start.ps1
```

## 시작 / 중지
```powershell
.\start.ps1    # backend 시작
.\stop.ps1     # backend 중지
```

## URL
- https://retrix.rebitgames.com
