# 무리없이 부산 Architecture

> 이 문서는 프로젝트의 **실제 구조**를 기술합니다.
> "실제로 어떻게 생겼는가"에 대한 답을 담으며, "왜 이렇게 하는가"는 [CONSTITUTION.md](./CONSTITUTION.md)를 참고합니다.

---

## 1. 서비스 구성

단일 FastAPI 컨테이너에 정적 PWA가 마운트된 **모놀리식** 구성.

```
                        ┌──────────────────────────────┐
                        │  Docker Container (port 7860)│
                        │                              │
 Browser (PWA)  ───────▶│  FastAPI  ──▶  /api/*        │
 /index.html            │              ▶  StaticFiles  │
 /onboarding.html       │                              │
 /results.html          │  backend/routers/*           │
 /course.html           │  backend/services/*          │
 /share.html            │  backend/store.py (SQLite)   │
                        └─────────────┬────────────────┘
                                      │
       ┌──────────────┬────────────┬──┴────────┬──────────────┐
       ▼              ▼            ▼           ▼              ▼
   TourAPI       Kakao Map      Gemini      기상청           Supabase
  (관광/접근성)  (JS SDK/REST)  (google-genai) (단기예보)   (캐시/로그 적재)
```

---

## 2. 서비스 상세

| 서비스 | 상태 | 포트 | 역할 | 기술 |
|--------|------|------|------|------|
| muri-busan | 활성 | 7860 (컨테이너) / `$PORT` (호스트) | 추천 API + 정적 PWA 서빙 | FastAPI 0.115+, Uvicorn, Python 3.12 |

`backend/main.py`의 단일 `FastAPI` 앱 인스턴스에 9개 라우터를 마운트.

---

## 3. 라우팅

### 3.1 HTTP API (`backend/routers/`)

| Method | Path | 라우터 | 설명 |
|--------|------|--------|------|
| POST | `/api/recommend` | recommend.py | 코스 추천 (Rate Limit 10/min/IP) |
| GET | `/api/courses/{course_id}` | courses.py | 저장된 코스 조회 (TTL 24h) |
| POST | `/api/share` | share.py | 공유 토큰 발급 (Rate Limit 20/min/IP) |
| GET | `/api/share/{token}` | share.py | 공유 토큰으로 코스 조회 |
| GET | `/api/weather` | weather.py | 기상청 단기예보 조회 (fallback 체인) |
| GET | `/api/search-places` | search.py | 스팟 검색 |
| GET | `/api/spot-detail/{content_id}` | spot_detail.py | 스팟 상세 |
| GET | `/api/meta/busan-sigungu` | meta.py | 부산 시군구 코드 |
| GET | `/api/meta/tour-categories` | meta.py | 관광 분류 코드 |
| POST | `/api/report` | report.py | 접근성 제보 |
| GET | `/api/reports/{spot_id}` | report.py | 스팟별 제보 목록 |
| POST | `/api/log/recommend` | analytics.py | 추천 요청 로그 (Rate Limit 30/min/IP) |
| POST | `/api/log/survey` | analytics.py | 만족도 설문 (Rate Limit 10/min/IP) |
| POST | `/api/log/interaction` | analytics.py | 인터랙션 로그 |
| GET | `/runtime-config.js` | main.py | Kakao 키 주입용 런타임 설정 |

### 3.2 정적 자산

`backend/main.py` 최하단의 `app.mount("/", StaticFiles(directory=frontend, html=True))` 로 `frontend/` 전체를 루트에 서빙. API 라우터들이 먼저 등록되므로 충돌 없음.

### 3.3 미들웨어 체인 (등록 순서)

1. `CORSMiddleware` — `ALLOWED_ORIGINS` 화이트리스트
2. `security_headers_middleware` — CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
3. `rate_limit_middleware` — 경로별 IP당 분당 제한, 500요청마다 GC

---

## 4. 통신 패턴

### 4.1 동기 (현재)

- 프론트 ↔ 백엔드: `fetch` / JSON.
- 백엔드 ↔ 외부 API: `httpx.AsyncClient` (TourAPI, 기상청). `google-genai` SDK (Gemini). `supabase-py` (Supabase).
- 카카오맵: 브라우저에서 직접 Kakao JS SDK 로드 (`https://dapi.kakao.com`).

### 4.2 비동기 (계획/현재)

현재 메시지 브로커는 없음. 분석 적재는 요청-응답 내 동기적으로 Supabase에 write-through.

### 4.3 외부 API 장애 대응

| 외부 | 실패 시 동작 |
|------|-------------|
| TourAPI | 기본 목록 캐시/mock 데이터 |
| Kakao Map SDK | 리스트 뷰로 degrade, `runtime-config.js`가 null이면 지도 생략 |
| Gemini | AI 설명 생략, 기본 안내 문구 |
| 기상청 | `base_time` 폴백 체인(오늘→어제 23/20시) → 최종 실패 시 섹션 생략 |
| Supabase | 파일 캐시 → 인메모리 캐시로 다단 폴백 |

---

## 5. 데이터 아키텍처

### 5.1 저장소 구성

| 저장소 | 용도 | 위치 |
|--------|------|------|
| SQLite (`courses.db`) | 코스 캐시 (TTL 24h) | `backend/data/courses.db` |
| SQLite (`share.db`) | 공유 토큰 (TTL 24h) | `backend/data/share.db` |
| SQLite (`reports.db`) | 접근성 제보 | `backend/data/reports.db` |
| 파일 캐시 | AI 응답 캐시 | `backend/data/ai_cache/` |
| JSON | 접근성 정적 캐시 | `backend/data/accessibility_cache.json` |
| JSON | 부산 스팟 시드 | `backend/data/busan_spots.json` |
| Supabase | AI 캐시 primary + 행동 로그 | 외부 (supabase-py) |

모든 SQLite는 WAL 모드(`PRAGMA journal_mode=WAL`) + 만료 인덱스(`idx_*_expires`).

### 5.2 주요 테이블

- `courses (id TEXT PK, course_json TEXT, expires_at TIMESTAMP)` — `backend/store.py:31`
- `share` 테이블 — `backend/routers/share.py` (`init_share_db`)
- `reports` 테이블 — `backend/routers/report.py` (`init_report_db`)

> DB 스키마 변경은 [CONSTITUTION.md §6](./CONSTITUTION.md#6-문서-생성-정책)에 따라 **사용자 승인 필수**.

---

## 6. 인프라 토폴로지

### 6.1 컨테이너

```
Dockerfile
├── FROM python:3.12-slim
├── COPY requirements.txt
├── pip install -r requirements.txt
├── COPY . .
├── EXPOSE 7860
└── CMD ["./start.sh"]
         │
         └── exec python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

### 6.2 배포

- **HuggingFace Spaces**: `README.md` frontmatter가 스펙. `sdk: docker`, `app_port: 7860`.
- **Railway/기타 PaaS 호환**: `ALLOWED_ORIGINS` 환경변수로 프론트엔드 Origin 지정.

### 6.3 환경변수 (`.env.example` 참조)

| 키 | 필수 여부 | 용도 |
|----|-----------|------|
| `TOUR_API_KEY` | 필수 (lifespan 검증) | TourAPI |
| `GEMINI_API_KEY` | 필수 (lifespan 검증) | Google Gemini |
| `KAKAO_MAP_KEY` | 선택 | 지도 표시 (없으면 리스트 뷰) |
| `WEATHER_KEY` | 선택 | 기상청 (없으면 생략) |
| `ALLOWED_ORIGINS` | 선택 | CORS 화이트리스트 |
| `SUPABASE_URL` / `SUPABASE_KEY` | 선택 | 캐시/로그 (없으면 파일/메모리 폴백) {TODO: 정확한 키명 확인} |
| `PORT` | 런타임 주입 | uvicorn 바인딩 |

---

## 7. 프로젝트 디렉토리 구조

```
muri-busan/
├── Dockerfile
├── README.md                 # HuggingFace Spaces frontmatter
├── requirements.txt
├── runtime.txt               # python-3.12.0
├── start.sh
├── .env.example
│
├── backend/
│   ├── main.py               # FastAPI 앱 + 미들웨어 + 라우터 등록
│   ├── store.py              # CourseStore (SQLite + in-memory)
│   ├── routers/              # 9개 라우터 (recommend, courses, share, weather, search, spot_detail, meta, report, analytics)
│   ├── services/             # algorithm, gemini, tourapi, supabase_client
│   └── data/                 # SQLite/JSON 런타임 데이터 (gitignored except busan_spots.json)
│
├── frontend/                 # 정적 PWA
│   ├── index.html / onboarding.html / results.html / course.html / share.html
│   ├── offline.html
│   ├── manifest.json
│   ├── sw.js                 # Service Worker
│   ├── js/                   # app.js, onboarding.js, results.js, course.js, share.js
│   ├── css/style.css
│   ├── images/, icons/
│
├── tests/
│   ├── test_algorithm.py
│   ├── test_api.py
│   ├── test_frontend_fixes.py
│   └── e2e/                  # Playwright 50 persona 시나리오
│       ├── personas.json
│       ├── test_personas.py / test_personas_api.py / test_smoke.py
│       └── report_personas.{json,md}
│
├── docs/                     # 하네스 문서
│   ├── design-docs/
│   ├── exec-plans/{active,completed}/
│   ├── generated/
│   └── service-specs/
│
├── CONSTITUTION.md
├── ARCHITECTURE.md
├── AGENTS.md
└── CLAUDE.md
```

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|-----------|--------|
| 2026-04-21 | v1.0.0 | 최초 작성 (harness init) | - |
