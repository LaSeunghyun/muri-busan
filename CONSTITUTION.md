# 무리없이 부산 Constitution

> 이 문서는 프로젝트의 **원칙, 컨벤션, 배포 규칙**을 정의합니다.
> "왜 이렇게 하는가"에 대한 답을 담으며, "실제로 어떻게 생겼는가"는 [ARCHITECTURE.md](./ARCHITECTURE.md)를 참고합니다.

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | 무리없이 부산 (Muri Busan) |
| 목적 | 이동약자(휠체어/유아차/시니어)를 위한 부산 관광 코스 추천 PWA |
| 아키텍처 | FastAPI 모놀리스 + 정적 PWA 프론트엔드 |
| 주요 기능 | 조건 기반 코스 추천, 카카오맵 시각화, 코스 공유(24h), 접근성 제보, 만족도 로깅 |
| 언어/프레임워크 | Python 3.12 / FastAPI 0.115+ / Uvicorn + Vanilla JS (ES Modules) |
| 런타임 | Docker (python:3.12-slim, 컨테이너 포트 7860) |
| 외부 의존 | TourAPI, Kakao Map JS SDK, Google Gemini (google-genai), 기상청 단기예보, Supabase |
| 배포 타겟 | HuggingFace Spaces (frontmatter 설정) · Railway 호환 (`ALLOWED_ORIGINS` env) |

---

## 2. 핵심 원칙

자세한 신념은 [docs/design-docs/core-beliefs.md](./docs/design-docs/core-beliefs.md) 참조.

1. **접근성 정보는 보수적으로 표현한다.** `확인`/`미확인`/`부적합` 3단계. "미확인"을 "가능"으로 취급하지 않는다.
2. **외부 API 장애는 정상 상태로 설계한다.** 개별 fallback을 가진다. 하나가 죽어도 서비스는 살아 있다.
3. **환경변수 누락은 부팅 단계에서 판별한다.** `main.py` lifespan이 `TOUR_API_KEY`, `GEMINI_API_KEY`를 요구한다. 선택 키(`KAKAO_MAP_KEY`, `WEATHER_KEY`)는 fallback이 있다.
4. **라우터는 얇게, 서비스는 테스트 가능하게.** 라우터는 HTTP 계약만, 로직은 `backend/services/`로.
5. **보안 헤더·Rate Limit은 기본값이다.** CSP/XFO/nosniff/Referrer-Policy + 경로별 IP 분당 Rate Limit.
6. **로그를 통해 학습한다.** `/api/log/{recommend,interaction,survey}`로 행동 로그 수집.
7. **PWA 우선.** 오프라인 fallback과 설치 가능한 manifest를 유지한다.

---

## 3. 브랜치 전략

실측 패턴(`git branch -a`):
- `master` — 기본 브랜치 (프로덕션)
- `fix/*` — 버그/UX 개선용 작업 브랜치 (예: `fix/map-sdk-and-ux-issues`)

### 브랜치 규칙

- `master` 직접 push 금지. PR + 리뷰/셀프리뷰 후 머지.
- 피처: `feat/<scope>`, 버그: `fix/<scope>`, 리팩터: `refactor/<scope>`, 테스트: `test/<scope>` 프리픽스 권장.
- 머지는 기본 Merge commit (`Merge pull request #N` 패턴 관측). Squash/Rebase는 선택.

---

## 4. 코딩 컨벤션

### 4.1 커밋 메시지

실측 패턴은 **Conventional Commits 한국어 변형**이다. 최근 20개 커밋에서 모두 준수:

```
<type>[(scope)]: <한국어 요약>
```

| type | 의미 | 예시 |
|------|------|------|
| `feat` | 기능 추가 | `feat: UX 개선 - 부산 이미지·사용자 친화적 텍스트·지역 지도·fallback 이미지` |
| `fix` | 버그 수정 | `fix(weather): base_time 폴백 체인 (오늘→어제 23/20시)` |
| `refactor` | 리팩터링 | `refactor: responsive design improvements` |
| `test` | 테스트 | `test: Playwright 50 페르소나 E2E 50/50 PASS 달성` |

본문이 있다면 "무엇을"보다 "왜"를 쓴다.

### 4.2 API 설계 원칙

- 모든 HTTP API는 `/api/` 접두사. 정적 자산과 구분.
- 리소스 조회: `GET /api/{resource}/{id}` — `courses`, `spot-detail`, `share`, `reports`.
- 동작 트리거: `POST /api/{action}` — `recommend`, `share`, `report`, `log/*`.
- 리소스/액션 이름은 kebab-case.
- 응답은 Pydantic 모델 기반 `response_model` 지정. 에러는 `JSONResponse(status_code, {"detail": ...})`.
- Rate Limit 대상 엔드포인트는 `backend/main.py`의 `_RATE_LIMITS`에 등록.

### 4.3 Python 컨벤션

- Python 3.12 타겟. `from __future__ import annotations` 사용, PEP 604 union (`X | None`) 권장.
- 모듈/패키지 경로는 `backend.routers.*`, `backend.services.*` 로 고정.
- 로깅은 모듈별 `logger = logging.getLogger(__name__)`. 루트 설정은 `main.py`에서 `basicConfig`.
- 외부 I/O(HTTPX, Supabase, SQLite)는 **try/except로 감싸고 warning 로깅 후 fallback**. 예외가 라우터 바깥으로 새어나가지 않도록 한다.
- `.env` 로딩은 `main.py` 상단 `load_dotenv()` 한 번. 라우터는 `os.getenv()` 직접 조회.

### 4.4 프론트엔드 컨벤션

- Vanilla JS (ES2020+). 번들러/프레임워크 없음.
- 카카오맵 키는 서버가 `/runtime-config.js`로 주입. 하드코딩 금지.
- 서비스 워커(`sw.js`) 캐시 전략 변경 시 버전 문자열을 올려 구버전 무효화.
- CSS는 단일 파일(`frontend/css/style.css`) 유지. 스크롤이 길어져도 섹션 주석으로 분할.

---

## 5. 배포 원칙

- **단일 컨테이너 배포**: `Dockerfile` → `start.sh` → `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
- **HuggingFace Spaces**: `README.md` frontmatter(`sdk: docker`, `app_port: 7860`)가 스펙.
- **환경변수 주입**: `.env.example` 기준. 프로덕션 필수는 `TOUR_API_KEY`, `GEMINI_API_KEY`.
- **CORS**: `ALLOWED_ORIGINS` 콤마 구분. 로컬은 `http://localhost:8000,http://127.0.0.1:8000` 기본.
- **데이터 영속성**: 컨테이너 내부 SQLite(`backend/data/*.db`). Spaces 재시작 시 휘발될 수 있으므로 공유/리포트는 24h TTL로 설계.

---

## 6. 문서 생성 정책

| 대상 | 정책 | 비고 |
|------|------|------|
| DB 스키마 변경 | **사용자 승인 필수** | `backend/store.py` 및 `share`/`report` init 함수의 CREATE TABLE 변경 포함 |
| 의존성 추가/변경 | **사용자 승인 필수** | `requirements.txt` 수정 |
| 외부 API 엔드포인트/키 스펙 | 자동 문서화 가능 | `docs/generated/api-spec.md` |
| Constitution/Architecture 변경 | PR로 제출, 변경 이력에 기록 | 본 문서 하단 표 |
| 하네스 check 리포트 | 자동 생성 (`/harness check`) | `docs/generated/harness-check-report.md` |

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|-----------|--------|
| 2026-04-21 | v1.0.0 | 최초 작성 (harness init) | - |
