# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**무리없이 부산 (Muri Busan)** — 이동약자(휠체어/유아차/시니어)를 위한 부산 관광 코스 추천 PWA.
FastAPI 모놀리스(Python 3.12) + Vanilla JS 정적 PWA. TourAPI·Kakao Map·Gemini·기상청·Supabase 연동. HuggingFace Spaces Docker 배포.

## Build & Run

### 로컬 개발

```bash
# 의존성 설치 (가상환경 권장)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 환경변수 준비
cp .env.example .env   # 실제 키로 교체

# 개발 서버 (reload)
python -m uvicorn backend.main:app --reload --port 8000
# 접속: http://localhost:8000
```

### Docker

```bash
docker build -t muri-busan .
docker run --rm -p 7860:7860 --env-file .env -e PORT=7860 muri-busan
```

### 테스트

```bash
pytest tests/                       # 단위 + API 테스트
pytest tests/e2e/test_smoke.py      # 스모크
pytest tests/e2e/test_personas.py   # 50 페르소나 E2E (Playwright 필요)
```

## Tech Stack

- **Backend**: Python 3.12, FastAPI 0.115+, Uvicorn (standard), httpx, python-dotenv, google-genai, supabase-py, stdlib sqlite3
- **Frontend**: Vanilla JS (ES Modules), HTML5, 단일 CSS 파일, PWA (Service Worker + manifest)
- **외부 API**: TourAPI, Kakao Map JS SDK, Google Gemini, 기상청 단기예보, Supabase
- **테스트**: pytest, Playwright (E2E)
- **배포**: Dockerfile (python:3.12-slim) → HuggingFace Spaces / Railway

## Architecture

- 단일 FastAPI 앱(`backend/main.py`)이 9개 라우터를 마운트하고, 프론트엔드(`frontend/`)를 정적 서빙.
- 미들웨어: CORS → Security Headers (CSP/XFO/nosniff/Referrer-Policy/Permissions-Policy) → Rate Limit (경로별 IP당 분당).
- 데이터: SQLite 3종(`courses.db`, `share.db`, `reports.db`) + JSON 시드 + Supabase(캐시/로그).
- 외부 API는 각각 개별 fallback을 가짐. 장애가 전파되지 않도록 `try/except + logger.warning + 기본값` 패턴.

상세는 [ARCHITECTURE.md](./ARCHITECTURE.md) 참고.

## Key Conventions

- **커밋 메시지**: Conventional Commits 한국어 변형 (`feat:`, `fix:`, `refactor:`, `test:` + 한국어 요약). scope 선택.
- **API 설계**: 모든 HTTP API는 `/api/` 접두사. 조회는 `GET /api/{resource}/{id}`, 동작은 `POST /api/{action}`. 응답은 `response_model` 지정.
- **Python 스타일**: `from __future__ import annotations`, PEP 604 union(`X | None`), 모듈별 `logger = logging.getLogger(__name__)`.
- **외부 I/O**: 반드시 try/except로 감싸고 warning 로깅 + fallback. 예외가 라우터 밖으로 새지 않게.
- **환경변수**: `main.py` 상단 `load_dotenv()` 1회. 필수 키(`TOUR_API_KEY`, `GEMINI_API_KEY`)는 lifespan에서 검증.
- **프론트 지도 키**: 하드코딩 금지. `/runtime-config.js`를 통해 서버가 주입.

상세 원칙은 [CONSTITUTION.md](./CONSTITUTION.md) 참고.

## Execution Plans

실행 계획은 `docs/exec-plans/`에서 관리.
- 진행 중인 계획: `docs/exec-plans/active/`에 마크다운 파일로 작성하고, `docs/exec-plans/active/index.md`에 기록할 것.
- **완료된 계획은 반드시 `docs/exec-plans/completed/`로 이동하고, `docs/exec-plans/completed/index.md`에 기록할 것.**

## Critical Rules

- **DB 스키마 변경은 반드시 사용자 승인 필요.** (`backend/store.py`, `share.py`, `report.py` 내 `CREATE TABLE` / 컬럼/인덱스 변경 포함)
- **의존성 추가/변경 시 사용자 승인 필요.** (`requirements.txt` 수정)
- **`.env`, 시크릿 값은 읽거나 기록하지 않음.** `.env.example`만 참조.
- **접근성 데이터는 보수적으로.** "미확인"을 "가능"으로 바꾸거나 기본값을 긍정으로 잡지 않음.
- **외부 API 호출은 항상 fallback을 가진다.** 신규 외부 연동 시 실패 경로를 같이 구현.
- **파괴적 git/셸 명령은 사용자 승인 후에만.** (`git push --force`, `git reset --hard`, `rm -rf` 등)
- **프로덕션 외부 시스템(HF Spaces, Railway, Supabase 콘솔 등)은 직접 조작하지 않음.**

## Documentation Structure

- [CONSTITUTION.md](./CONSTITUTION.md) — 원칙, 컨벤션, 배포 규칙 ("왜")
- [ARCHITECTURE.md](./ARCHITECTURE.md) — 실제 구조, API 라우팅, 데이터 ("어떻게")
- [AGENTS.md](./AGENTS.md) — 역할 정의, 권한, CI/CD 흐름 ("누가")
- `docs/design-docs/` — 기술적 신념, 설계 문서
- `docs/exec-plans/{active,completed}/` — 실행 계획 (진행중/완료)
- `docs/generated/` — 자동 생성 문서 (API 스펙, DB 스키마, harness 리포트)
- `docs/service-specs/` — 서비스별 상세 스펙
