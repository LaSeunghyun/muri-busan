# 무리없이 부산 Agents

> 이 문서는 프로젝트의 에이전트(역할) 정의, 책임 범위, CI/CD 파이프라인에서의 권한을 정의합니다.
> 모든 행동과 결정은 [CONSTITUTION.md](./CONSTITUTION.md)의 원칙을 따릅니다.

---

## 운영 모드

**1~2인 프로젝트** (공모전 출품 준비 중).

커밋 작성자는 현재 `LaSeunghyun`, `무리없이부산` 두 명으로 관측되며 실질적으로 소규모 운영이다.
따라서 아래 역할 분리는 **프로세스 학습 및 체크리스트 용도**로 둔다. 한 사람이 여러 역할을 겸임해도 되지만, 역할을 바꿀 때마다 그 역할의 체크리스트를 재확인한다.

---

## 에이전트 구성

| 에이전트 | 식별자 | 역할 한줄 요약 |
|----------|--------|----------------|
| CEO | @owner | 최종 의사결정, 출품/릴리스 승인, 환경변수/시크릿 관리 |
| Developer | @dev | FastAPI/프론트 구현, 외부 API 연동, 테스트 작성 |
| Planner | @planner | UX 기준 수립, 이동약자 요구 정의, 알고리즘 우선순위 결정 |
| QA | @qa | E2E 페르소나 검증, 회귀 테스트, 배포 전 승인 |
| AI Assistant | Claude Code | 코드 제안 및 문서화 보조 (아래 제약 준수) |

---

## 에이전트 상세 정의

### CEO (@owner)

- **책임**: 공모전 출품 여부, 프로덕션 배포 승인, 외부 키 발급/교체 (TourAPI, Kakao, Gemini, 기상청, Supabase), 비용이 발생하는 계정/서비스 전환.
- **권한**: `main.py`의 필수 env 목록, HF Spaces 설정, 도메인/CORS 원본 결정.
- **에스컬레이션 수신**: 의존성 업그레이드, DB 스키마 변경, 새로운 외부 API 도입.

### Developer (@dev)

- **책임**: 라우터/서비스 구현, 알고리즘 튜닝(`services/algorithm.py`), 프론트엔드 UX, 보안 헤더/Rate Limit 조정.
- **권한**: `backend/`, `frontend/`, `tests/` 자유 수정. `requirements.txt` 수정 시 CEO 승인.
- **의무**: 변경 전 관련 테스트 실행 (`pytest tests/`). 외부 API 변경 시 fallback 경로 함께 갱신.

### Planner (@planner)

- **책임**: 이동약자 페르소나 정의(`tests/e2e/personas.json`), 접근성 라벨 정책, 만족도 설문 문항 설계.
- **권한**: `docs/design-docs/`, `docs/exec-plans/active/` 작성/수정.
- **의무**: 알고리즘/UX 변경 제안 시 수용 기준을 먼저 문서화.

### QA (@qa)

- **책임**: E2E 50 페르소나 통과 유지, PR 머지 전 스모크 테스트, 회귀 방지.
- **권한**: PR 머지 차단/승인 (체크리스트 기반).
- **의무**: 실패 시 `tests/e2e/report_personas.md`에 결과 기록.

### AI Assistant (Claude Code)

- **허용 범위**: 코드 작성/리팩터, 라우터/서비스 추가, 테스트 작성, 문서 초안 작성, `docs/**` 생성/갱신.
- **제약** (CLAUDE.md에도 동일 명시):
  - DB 스키마(테이블/컬럼/인덱스) 변경은 **반드시 사용자 승인**.
  - `requirements.txt` 의존성 추가/버전 변경은 **반드시 사용자 승인**.
  - `.env`, 시크릿 값은 읽거나 기록하지 않음.
  - 프로덕션 외부 시스템(HF Spaces, Railway, Supabase, Kakao 콘솔 등)을 직접 조작하지 않음.
  - `rm -rf`, `git push --force`, `git reset --hard` 등 파괴적 명령은 사전 승인 없이 사용하지 않음.
- **자유롭게 수행 가능**: 로컬 파일 편집, 테스트 실행, git 로컬 커밋 초안 준비, 하네스 문서 생성/갱신.

---

## CI/CD 전체 흐름 요약

현재 리포에 `.github/workflows/` 등 CI 설정은 **없음** {TODO: 필요 시 추가}. HuggingFace Spaces의 git push-to-deploy에 의존.

```
 로컬 개발
   │
   ▼
 git push → master / PR 브랜치
   │
   ├── (현재 없음) CI: pytest + Playwright E2E  {TODO}
   │
   ▼
 PR 리뷰 (QA 체크)
   │
   ▼
 master 머지
   │
   ▼
 HF Spaces Docker 자동 빌드 (Dockerfile)
   │
   ▼
 uvicorn backend.main:app 기동
   │
   └── lifespan: 필수 env 검증 → SQLite init → TourAPI 예열
```

**권장 개선** ({TODO: CEO 승인 후 도입}):
1. GitHub Actions: PR 시 `pytest tests/` + 린트
2. E2E는 별도 잡으로 분리 (headless Chromium)
3. Dockerfile 빌드 체크 (로컬/CI에서 `docker build . --no-cache`)

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|-----------|--------|
| 2026-04-21 | v1.0.0 | 최초 작성 (harness init) | - |
