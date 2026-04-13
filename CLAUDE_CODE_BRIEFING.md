# Retrix - Project Briefing (Claude Code Handoff)

## 프로젝트 개요
AI 프로젝트 오케스트레이터. 기획서를 던지면 PM AI(Haiku 4.5)가 분석 → 태스크 분해 → 모델 선택 → 워커 배분 → 결과 검증까지 자동으로 처리.
동시 10개 프로젝트 병렬 운영 가능. 게임 5개(Unity/Cocos/Godot), 웹 3개, 모바일 2개 비중.

## 기술 스택
- **Backend**: FastAPI + LangGraph + SQLAlchemy (MySQL 8) + Redis
- **Frontend**: React + Vite + Tailwind
- **PM 오케스트레이터**: Claude Haiku 4.5 (매 단계마다 모델 풀에서 최적 모델 동적 선택)
- **모델 풀**: Haiku, DeepSeek V3.2, DeepSeek V4, GPT-4o-mini, GPT-4o, MiniMax M2.7
- **워커**: Claude Code, Cursor, Codex, Gemini CLI, Antigravity

## 환경
- **OS**: Windows
- **MySQL**: D:\MySQL\MySQL Server 8.0\bin, port 13306, user=root, pw=roh8966, db=retrix
- **Redis**: 127.0.0.1:6379, no password
- **Caddy**: D:\SelfHosted\caddy, 이미 서비스로 실행 중
- **도메인**: retrix.rebitgames.com (Caddy SSL)
- **워크스페이스 루트**: D:\Projects

## 아키텍처 흐름
```
기획서 → [PM 오케스트레이터: Haiku 4.5]
              │
              │ (매 단계마다 모델 풀에서 최적 모델 선택)
              │
              ├─ 1. 기획서 분석 → Haiku가 모델 선택
              ├─ 2. 태스크 분해 + 의존성 → Haiku가 모델 선택
              ├─ 3. 워커 지시서 생성 → Haiku가 모델 선택
              ├─ 4. 워커에 디스패치 → 실제 CLI 호출
              ├─ 5. 결과 검증 → Haiku 자체 처리
              └─ 6. 실패 시 Fallback → Haiku가 전략 결정
                   (retry/fallback worker/escalate/hold)
                   3회 연속 실패 → 대시보드 알림 + hold

워커 Fallback 체인:
  claude_code ←→ cursor
  codex ←→ gemini_cli
  antigravity → claude_code
```

## 현재 완료된 것
- ✅ 전체 프로젝트 구조 (47개 파일)
- ✅ FastAPI 백엔드 (REST API + WebSocket)
- ✅ JWT 인증 (로그인/토큰), 기본 admin/retrix2024!
- ✅ LangGraph 오케스트레이션 그래프 (analyze→decompose→instruct→dispatch→review→fallback)
- ✅ PM 시스템 프롬프트 + 절대원칙 (rules.py)
- ✅ 모델 풀 (Haiku/DeepSeek/GPT/MiniMax 통합 API 클라이언트)
- ✅ 비용 트래킹 (Redis 실시간 + MySQL 로그)
- ✅ GitHub 연동 (repo 생성/clone)
- ✅ React 대시보드 (Dashboard, ProjectDetail, NewProject, CostTracker, Settings, Login)
- ✅ WebSocket 실시간 업데이트 (토큰 인증 포함)
- ✅ 워크스페이스 경로 설정 (프로젝트 생성 시 D:\Projects\{name})
- ✅ Windows 스크립트 (start.ps1, stop.ps1, restart.ps1, start.bat)

## TODO (우선순위 순)
1. **워커 실제 연동** ← 핵심! dispatch_workers 노드에서 Claude Code/Cursor/Codex CLI를 실제로 subprocess로 호출
   - Claude Code: `claude -p "instruction" --output-dir {workspace_path}`
   - Codex: `codex -q "instruction"` 
   - 각 워커별 CLI 명령어 매핑 + 결과 수집
   - 워커가 git feature branch에서 작업하도록

2. **프로젝트 기획서 파일 업로드** - .md/.pdf/.docx 업로드 → 텍스트 파싱

3. **비용 히스토리 차트** - 일별 추이 그래프 (현재 오늘 비용만)

4. **Settings 백엔드 연결** - 예산/워커/모델 설정이 DB에 실제 저장

5. **PM 룰 대시보드 편집** - rules.py를 대시보드에서 수정 가능하게

## PM 절대원칙 요약
1. 일일 예산 초과 금지, gpt_4o 하루 5회 제한
2. 테스트 없는 코드 승인 금지, 하드코딩 시크릿 즉시 거부
3. main 브랜치 직접 커밋 금지, feature branch + conventional commits
4. 4시간 초과 태스크 분할 필수, 의존성 있는 태스크 병렬 실행 금지
5. API키/비밀번호 코드 포함 금지, 패키지 버전 명시
6. 모든 결정에 이유 기록, 에러 시 대시보드 알림
7. 기존 프로젝트 구조 존중, README 유지, .gitignore 필수
8. 게임→엔진별 전문 워커, 웹→프론트/백 병렬, 모바일→플랫폼별 배정

## 주요 파일 위치
- 백엔드 진입점: backend/app/main.py
- LangGraph 그래프: backend/app/graph/orchestrator.py
- PM 프롬프트: backend/app/graph/prompts.py
- PM 절대원칙: backend/app/graph/rules.py
- 모델 풀 API: backend/app/services/model_pool.py
- GitHub 연동: backend/app/services/github.py
- DB 모델: backend/app/models/models.py
- 설정: backend/app/core/config.py + backend/.env
- 인증: backend/app/core/auth.py
- 프론트 앱: frontend/src/App.jsx
- API 클라이언트: frontend/src/lib/api.js
