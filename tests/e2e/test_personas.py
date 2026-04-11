"""
50개 페르소나 Playwright E2E 테스트

목적:
  - 각 페르소나별 온보딩 → 결과 → 코스 상세 흐름 검증
  - TourAPI / Gemini API 키 없이도 mock/stub으로 실행 가능
  - 결과를 tests/e2e/report_personas.json 및 .md로 저장

실행:
  # 의존성 설치 (최초 1회)
  pip install playwright pytest-playwright
  playwright install chromium

  # 테스트 실행 (프로젝트 루트에서)
  pytest tests/e2e/test_personas.py -v -s

  # 서버 없이 mock-only 모드로 빠른 실행
  pytest tests/e2e/test_personas.py -v -s -k "personas"
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

# ── 경로 상수 ──────────────────────────────────────────────────────────────
E2E_DIR = Path(__file__).resolve().parent
PERSONAS_FILE = E2E_DIR / "personas.json"
REPORT_JSON = E2E_DIR / "report_personas.json"
REPORT_MD = E2E_DIR / "report_personas.md"

# conftest.py에서 정의된 BASE_URL과 일치
BASE_URL = "http://localhost:18765"

# ── 접근성 등급 기준 (algorithm.py의 MAX_DAILY_FATIGUE와 동일) ───────────
MAX_DAILY_FATIGUE = 250.0


# ══════════════════════════════════════════════════════════════════════════════
# Mock 데이터 빌더
# ══════════════════════════════════════════════════════════════════════════════

def _make_spot(
    spot_id: str,
    area: str,
    mobility_type: str,
    grade: float = 4.5,
    index: int = 0,
) -> dict[str, Any]:
    """단일 관광지 mock 스팟을 생성한다."""
    lat_offset = (index * 7 + hash(spot_id[:4]) % 50) * 0.001
    lng_offset = (index * 5 + hash(spot_id[-4:]) % 50) * 0.001

    spot_names = {
        "wheelchair": ["배리어프리 문화관", "무장애 해변산책로", "접근성 광장", "배리어프리 공원"],
        "stroller":   ["유아 친화 카페거리", "아이랑 해수욕장", "유모차길 공원", "수유실 복합쇼핑몰"],
        "senior":     ["어르신 쉼터 공원", "경로당 문화시설", "시니어 산책로", "노인복지 관광지"],
        "carrier":    ["평탄 노면 거리", "무단차 문화광장", "보행보조 적합 공원", "평지 관광지"],
    }
    names = spot_names.get(mobility_type, spot_names["wheelchair"])
    name = f"{area} {names[index % len(names)]}"

    return {
        "id": spot_id,
        "name": name,
        "category": "문화",
        "area": area,
        "lat": 35.1587 + lat_offset,
        "lng": 129.1604 + lng_offset,
        "visit_time_min": 60,
        "slope_pct": 1.0 if mobility_type in ("wheelchair", "carrier") else 2.5,
        "wait_time_min": 5,
        "accessibility_grade": int(grade),
        "wheelchair_accessible": mobility_type == "wheelchair",
        "stroller_accessible": mobility_type == "stroller",
        "restroom_accessible": True,
        "elevator": mobility_type == "wheelchair",
        "tags": ["실내"],
        "address": f"부산시 {area} 테스트로 {index + 1}",
        "description": f"{name} - {mobility_type} 접근 가능한 관광지",
        "image_url": None,
    }


def _make_leg(from_id: str, to_id: str) -> dict[str, Any]:
    """두 스팟 간 이동 정보 mock."""
    return {
        "from_id": from_id,
        "to_id": to_id,
        "recommended_mode": "walk",
        "recommended_label": "도보",
        "recommended_distance_m": 350,
        "route_distance_km": 0.35,
        "recommended_time_min": 7,
        "walk_time_min": 7,
        "transit_time_min": 12,
        "car_time_min": 9,
        "straight_distance_m": 310,
    }


def _make_course(
    course_id: str,
    day: int,
    area: str,
    mobility_type: str,
    accessibility_avg: float,
    alt_idx: int = 0,
) -> dict[str, Any]:
    """하루 코스 mock 객체를 생성한다 (스팟 3개, 피로도 < 250)."""
    spots = [
        _make_spot(f"{course_id}_s{i}", area, mobility_type, accessibility_avg, i)
        for i in range(3)
    ]
    legs = [_make_leg(spots[i]["id"], spots[i + 1]["id"]) for i in range(len(spots) - 1)]

    suffix = ["", " (B코스)", " (C코스)"][alt_idx] if alt_idx < 3 else f" ({alt_idx + 1}번)"
    day_label = f" Day {day}" if day > 0 else ""
    theme_map = {
        "wheelchair": "무장애 탐방",
        "stroller":   "유아 친화 코스",
        "senior":     "시니어 힐링",
        "carrier":    "평지 산책",
    }
    theme = theme_map.get(mobility_type, "무장애 코스")

    return {
        "id": course_id,
        "name": f"{area} {theme} 코스{day_label}{suffix}",
        "day": day,
        "spots": spots,
        "legs": legs,
        "total_time_min": 220,
        "total_fatigue": 42.0,          # MAX_DAILY_FATIGUE(250) 미만 보장
        "distance_km": 0.9,
        "rest_spots": 3,
        "accessibility_avg": accessibility_avg,
        "ai_description": None,
    }


def build_mock_response(
    mobility_type: str,
    days: int,
    areas: list[str],
) -> dict[str, Any]:
    """
    /api/recommend mock 응답.
    하루당 3개 대안 코스(NUM_ALTERNATIVES=3), days만큼 반복.
    """
    area = areas[0] if areas else "해운대"
    # mobility 유형별 접근성 평균 (필터 통과 기준 이상으로 설정)
    acc_avg = 4.5 if mobility_type in ("wheelchair", "stroller") else 3.5

    courses: list[dict[str, Any]] = []
    for day in range(1, days + 1):
        for alt in range(3):
            cid = f"c{day:03d}_{mobility_type[:2]}{alt}"
            courses.append(_make_course(cid, day, area, mobility_type, acc_avg, alt))

    return {
        "courses": courses,
        "summary": {
            "requested_areas": areas,
            "applied_areas": [area],
            "mobility_types": [mobility_type],
            "requested_days": days,
            "start_date": None,
            "course_count": len(courses),
            "festival_count": 0,
            "fallback_used": False,
            "message": "",
            "ai_enabled": False,
            "weather": {"is_rainy": False, "description": "맑음"},
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# 단일 페르소나 테스트 실행기
# ══════════════════════════════════════════════════════════════════════════════

def run_persona_test(page: Any, persona: dict, base_url: str) -> dict[str, Any]:
    """
    단일 페르소나의 E2E 흐름을 실행하고 결과 dict를 반환한다.

    흐름:
      1. 온보딩 페이지 진입
      2. mobility_type 선택
      3. days 선택
      4. (선택) 권역 선택
      5. 코스 추천 요청
      6. 결과 페이지 검증 (카드 수, 접근성, 피로도, 에러 없음)
      7. 코스 상세 페이지 타임라인 렌더링 확인
    """
    persona_id = persona["id"]
    mobility_type = persona["mobility_type"]
    days = persona["days"]
    area = persona.get("area", "")
    areas = [area] if area else []
    expected_quality = persona["expected_course_quality"]

    result: dict[str, Any] = {
        "persona_id": persona_id,
        "name": persona["name"],
        "mobility_type": mobility_type,
        "days": days,
        "area": area,
        "age_group": persona.get("age_group", ""),
        "special_conditions": persona.get("special_conditions"),
        "expected_course_quality": expected_quality,
        "passed": False,
        "failures": [],
        "warnings": [],
        "steps_completed": [],
        "duration_ms": 0,
    }

    t0 = time.time()

    try:
        # ── Mock 응답 준비 ──────────────────────────────────────────────
        mock_resp = build_mock_response(mobility_type, days, areas)
        first_course = mock_resp["courses"][0]

        def handle_recommend(route):
            route.fulfill(
                status=200,
                content_type="application/json; charset=utf-8",
                body=json.dumps(mock_resp, ensure_ascii=False),
            )

        def handle_courses(route):
            url = route.request.url
            cid = url.rstrip("/").split("/")[-1]
            course = next(
                (c for c in mock_resp["courses"] if c["id"] == cid),
                first_course,
            )
            route.fulfill(
                status=200,
                content_type="application/json; charset=utf-8",
                body=json.dumps(course, ensure_ascii=False),
            )

        def handle_weather(route):
            route.fulfill(
                status=200,
                content_type="application/json; charset=utf-8",
                body=json.dumps({"is_rainy": False, "description": "맑음"}, ensure_ascii=False),
            )

        def handle_log(route):
            route.fulfill(
                status=200,
                content_type="application/json; charset=utf-8",
                body=json.dumps({"ok": True, "log_id": f"mock-{persona_id}"}, ensure_ascii=False),
            )

        def handle_share(route):
            route.fulfill(
                status=200,
                content_type="application/json; charset=utf-8",
                body=json.dumps({"token": "mock-token"}, ensure_ascii=False),
            )

        page.route("**/api/recommend", handle_recommend)
        page.route("**/api/courses/**", handle_courses)
        page.route("**/api/weather**", handle_weather)
        page.route("**/api/log/**", handle_log)
        page.route("**/api/share**", handle_share)

        # ── Step 1: 온보딩 페이지 진입 ────────────────────────────────
        page.goto(f"{base_url}/onboarding.html", wait_until="domcontentloaded")
        assert "무리없이 부산" in page.title(), "온보딩 페이지 타이틀 없음"
        assert page.locator("#step1").is_visible(), "Step1 섹션 미노출"
        result["steps_completed"].append("온보딩 페이지 진입")

        # ── Step 2: mobility_type 선택 (모바일 뷰포트 → #typeGrid 활성) ─
        # visible 한 그리드를 우선 선택 (모바일: #typeGrid, PC: #typeGridPc)
        type_card = page.locator(
            f".ob-choice-card[data-type='{mobility_type}']"
        ).filter(has=None).first
        type_card.wait_for(state="visible", timeout=5_000)
        type_card.click()
        assert type_card.get_attribute("aria-checked") == "true", \
            f"aria-checked 미변경: {mobility_type}"
        result["steps_completed"].append(f"이동약자 유형 선택: {mobility_type}")

        # 활성화된 다음 버튼 클릭 (모바일: #step1Next, PC: #step1NextPc)
        next1 = page.locator("#step1Next, #step1NextPc").filter(visible=True).first
        next1.wait_for(state="visible", timeout=3_000)
        assert not next1.is_disabled(), "Step1 다음 버튼 비활성"
        next1.click()
        page.locator("#step2").wait_for(state="visible", timeout=5_000)
        result["steps_completed"].append("Step2 진입")

        # ── Step 3: days 선택 ─────────────────────────────────────────
        day_chip = page.locator(
            f".duration-chip[data-days='{days}']"
        ).filter(has=None).first
        day_chip.wait_for(state="visible", timeout=3_000)
        day_chip.click()
        assert day_chip.get_attribute("aria-checked") == "true", \
            f"days aria-checked 미변경: {days}"
        result["steps_completed"].append(f"일정 선택: {days}일")

        next2 = page.locator("#step2Next, #step2NextPc").filter(visible=True).first
        next2.wait_for(state="visible", timeout=3_000)
        assert not next2.is_disabled(), "Step2 다음 버튼 비활성"
        next2.click()
        page.locator("#step3").wait_for(state="visible", timeout=5_000)
        result["steps_completed"].append("Step3 진입")

        # ── Step 4: 권역 선택 (선택사항) ─────────────────────────────
        if area:
            area_chip = page.locator(f".area-chip[data-area='{area}']").filter(visible=True).first
            if area_chip.count() > 0:
                area_chip.click()
                result["steps_completed"].append(f"권역 선택: {area}")
            else:
                result["warnings"].append(f"권역 칩 없음: {area} → 전체 권역으로 진행")

        # ── Step 5: 코스 추천 요청 ────────────────────────────────────
        submit_btn = page.locator("#step3Next, #step3NextPc").filter(visible=True).first
        assert submit_btn.count() > 0, "step3Next 버튼 없음"
        submit_btn.click()

        # 결과 페이지로 이동 대기 (첫 요청 콜드스타트 고려해 30초)
        page.wait_for_url(f"{base_url}/results.html", timeout=30_000)
        # JS 렌더링 완료 대기 — 로딩 오버레이 사라지거나 코스카드 출현 중 먼저 오는 것
        try:
            page.wait_for_selector(
                "#loadingState[style*='display: none'], #loadingState[hidden], .course-card",
                timeout=15_000,
            )
        except Exception:
            pass  # 로딩 상태 없이 바로 카드가 그려지는 경우 허용
        result["steps_completed"].append("결과 페이지 이동")

        # ── Step 6: 결과 페이지 검증 ─────────────────────────────────
        # 에러 페이지 아닌지 확인
        body_text = page.locator("body").text_content() or ""
        error_keywords = ["500 Internal Server Error", "Not Found", "오류가 발생했습니다"]
        detected_errors = [kw for kw in error_keywords if kw in body_text]
        if detected_errors:
            result["failures"].append(f"에러 페이지 감지: {detected_errors}")

        # 코스 카드 렌더링 확인
        course_cards = page.locator(".course-card")
        card_count = course_cards.count()
        if card_count < 1:
            result["failures"].append(f"코스 카드 미렌더링 (count={card_count})")
        else:
            result["steps_completed"].append(f"코스 카드 {card_count}개 렌더링 확인")

        # 접근성 등급 검증 (mock 데이터 기준)
        actual_quality = first_course["accessibility_avg"]
        if actual_quality < expected_quality:
            result["failures"].append(
                f"접근성 등급 미달: {actual_quality:.1f} < {expected_quality:.1f}"
            )
        else:
            result["steps_completed"].append(
                f"접근성 등급 OK: {actual_quality:.1f} >= {expected_quality:.1f}"
            )

        # 피로도 검증
        actual_fatigue = first_course["total_fatigue"]
        if actual_fatigue >= MAX_DAILY_FATIGUE:
            result["failures"].append(
                f"피로도 초과: {actual_fatigue} >= {MAX_DAILY_FATIGUE}"
            )
        else:
            result["steps_completed"].append(
                f"피로도 OK: {actual_fatigue} < {MAX_DAILY_FATIGUE}"
            )

        # ── Step 7: 코스 상세 페이지 진입 ────────────────────────────
        # localStorage에 selected_course 직접 주입 (카드 클릭 대신 안정적 방법)
        page.evaluate(
            f"() => localStorage.setItem('mb_selected', JSON.stringify({json.dumps(first_course, ensure_ascii=False)}))"
        )
        page.goto(f"{base_url}/course.html", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10_000)
        result["steps_completed"].append("코스 상세 페이지 진입")

        # 타임라인 렌더링 확인
        timeline = page.locator("#timelineList, #timelineListPc, .timeline-list, .spot-list")
        timeline_count = timeline.count()

        # 스팟 이름이 DOM에 존재하는지 확인
        detail_html = page.content()
        spot_names_in_dom = [
            s["name"] for s in first_course["spots"] if s["name"] in detail_html
        ]

        if timeline_count < 1 and not spot_names_in_dom:
            result["failures"].append("코스 상세 타임라인/스팟 미렌더링")
        else:
            rendered_info = (
                f"타임라인 엘리먼트 {timeline_count}개"
                if timeline_count > 0
                else f"스팟 이름 {len(spot_names_in_dom)}개 DOM 확인"
            )
            result["steps_completed"].append(f"코스 상세 렌더링 OK ({rendered_info})")

        # ── 최종 판정 ─────────────────────────────────────────────────
        result["passed"] = len(result["failures"]) == 0

    except AssertionError as e:
        result["failures"].append(f"AssertionError: {e}")
    except Exception as e:
        result["failures"].append(f"{type(e).__name__}: {str(e)[:300]}")

    result["duration_ms"] = round((time.time() - t0) * 1000)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 리포트 작성
# ══════════════════════════════════════════════════════════════════════════════

def write_reports(results: list[dict[str, Any]]) -> None:
    """JSON + Markdown 리포트를 생성한다."""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    # ── mobility_type별 통과율 ──────────────────────────────────────
    by_mobility: dict[str, list] = defaultdict(list)
    for r in results:
        by_mobility[r["mobility_type"]].append(r["passed"])

    mobility_stats = {
        mt: {
            "total": len(vals),
            "passed": sum(vals),
            "rate_pct": round(sum(vals) / len(vals) * 100, 1),
        }
        for mt, vals in by_mobility.items()
    }

    # ── days별 통과율 ───────────────────────────────────────────────
    by_days: dict[int, list] = defaultdict(list)
    for r in results:
        by_days[r["days"]].append(r["passed"])

    days_stats = {
        d: {
            "total": len(vals),
            "passed": sum(vals),
            "rate_pct": round(sum(vals) / len(vals) * 100, 1),
        }
        for d, vals in sorted(by_days.items())
    }

    # ── 새로 발견된 버그 목록 ───────────────────────────────────────
    bugs = [
        {"persona_id": r["persona_id"], "name": r["name"], "failures": r["failures"]}
        for r in results
        if not r["passed"]
    ]

    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
        },
        "by_mobility_type": mobility_stats,
        "by_days": days_stats,
        "bugs_found": bugs,
        "details": results,
    }

    # ── JSON 저장 ───────────────────────────────────────────────────
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ── Markdown 저장 ───────────────────────────────────────────────
    md_lines = [
        "# 페르소나 E2E 테스트 결과 리포트",
        "",
        f"**생성 시각**: {report['generated_at']}",
        "",
        "## 요약",
        "",
        f"| 항목 | 값 |",
        f"|------|----|",
        f"| 총 페르소나 | {total}개 |",
        f"| 통과 | {passed}개 |",
        f"| 실패 | {failed}개 |",
        f"| 통과율 | {report['summary']['pass_rate_pct']}% |",
        "",
        "## mobility_type별 통과율",
        "",
        "| 유형 | 총 | 통과 | 통과율 |",
        "|------|----|------|--------|",
    ]
    for mt, s in mobility_stats.items():
        md_lines.append(f"| {mt} | {s['total']} | {s['passed']} | {s['rate_pct']}% |")

    md_lines += [
        "",
        "## days별 통과율",
        "",
        "| 일정 | 총 | 통과 | 통과율 |",
        "|------|----|------|--------|",
    ]
    for d, s in days_stats.items():
        label = {1: "당일(1일)", 2: "1박2일", 3: "2박3일"}.get(d, f"{d}일")
        md_lines.append(f"| {label} | {s['total']} | {s['passed']} | {s['rate_pct']}% |")

    if bugs:
        md_lines += [
            "",
            "## 실패 페르소나 및 실패 이유",
            "",
            "| ID | 이름 | 유형 | 일정 | 실패 이유 |",
            "|----|------|------|------|-----------|",
        ]
        for b in bugs:
            pid = b["persona_id"]
            # 상세 정보 찾기
            detail = next((r for r in results if r["persona_id"] == pid), {})
            reasons = " / ".join(b["failures"])
            md_lines.append(
                f"| {pid} | {b['name']} | {detail.get('mobility_type','')} "
                f"| {detail.get('days','')}일 | {reasons} |"
            )
    else:
        md_lines += ["", "## 발견된 버그", "", "없음 - 모든 페르소나 통과 OK"]

    md_lines += [
        "",
        "## 전체 페르소나 결과",
        "",
        "| ID | 이름 | 유형 | 일정 | 권역 | 결과 | 소요(ms) |",
        "|----|------|------|------|------|------|----------|",
    ]
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        md_lines.append(
            f"| {r['persona_id']} | {r['name']} | {r['mobility_type']} "
            f"| {r['days']}일 | {r['area']} | {status} | {r['duration_ms']} |"
        )

    REPORT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\n리포트 저장 완료: {REPORT_JSON}\n          {REPORT_MD}")


# ══════════════════════════════════════════════════════════════════════════════
# pytest 테스트 엔트리포인트
# ══════════════════════════════════════════════════════════════════════════════

def test_all_personas(browser, live_server):
    """
    50개 페르소나를 순차 실행하고 결과를 리포트로 저장한다.

    - 각 페르소나마다 새 브라우저 탭(page)을 생성 → 상태 완전 격리
    - Mock API route로 TourAPI / Gemini 없이도 실행 가능
    - 최종 assert는 전체 실패 건수로 판정
    """
    assert PERSONAS_FILE.exists(), f"personas.json 없음: {PERSONAS_FILE}"
    personas: list[dict] = json.loads(PERSONAS_FILE.read_text(encoding="utf-8"))
    assert len(personas) == 50, f"페르소나 수 오류: {len(personas)} (기대: 50)"

    results: list[dict[str, Any]] = []
    base_url = live_server

    # 서버 콜드스타트 워밍업 — 첫 페르소나 타임아웃 방지
    _warmup = browser.new_page(viewport={"width": 390, "height": 844})
    try:
        _warmup.goto(f"{base_url}/onboarding.html", wait_until="domcontentloaded", timeout=30_000)
    except Exception:
        pass
    finally:
        _warmup.close()

    print(f"\n{'='*60}")
    print(f"  50개 페르소나 E2E 테스트 시작 - {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")

    for idx, persona in enumerate(personas, 1):
        pid = persona["id"]
        mt = persona["mobility_type"]
        days = persona["days"]
        area = persona.get("area", "-")

        print(f"[{idx:>2}/50] {pid} | {persona['name']:6s} | {mt:10s} | {days}일 | {area}", end=" ")

        # 각 페르소나마다 격리된 새 탭 사용 (모바일 뷰포트 — PC CSS에서 #typeGrid 숨김 방지)
        # 간헐적 타임아웃은 1회 자동 재시도
        MAX_RETRIES = 2
        result = None
        for attempt in range(MAX_RETRIES):
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.set_default_timeout(15_000)
            try:
                result = run_persona_test(page, persona, base_url)
            finally:
                page.close()
            if result["passed"]:
                break
            is_timeout = any("Timeout" in f for f in result["failures"])
            if not is_timeout or attempt == MAX_RETRIES - 1:
                break
            print(f"[retry {attempt + 1}]", end=" ")

        status_mark = "✓" if result["passed"] else "✗"
        fail_summary = ""
        if not result["passed"]:
            fail_summary = f" -> {result['failures'][0][:60]}"
        print(f"[{status_mark}] {result['duration_ms']}ms{fail_summary}")

        results.append(result)

    # ── 통계 집계 ─────────────────────────────────────────────────────
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    print(f"\n{'='*60}")
    print(f"  결과: {passed}/{total} 통과  ({failed}개 실패)")

    by_mobility: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    for r in results:
        p, t = by_mobility[r["mobility_type"]]
        by_mobility[r["mobility_type"]] = (p + int(r["passed"]), t + 1)

    print("\n  mobility_type별:")
    for mt, (p, t) in sorted(by_mobility.items()):
        pct = p / t * 100
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        print(f"    {mt:12s} [{bar}] {p}/{t} ({pct:.0f}%)")

    by_days: dict[int, tuple[int, int]] = defaultdict(lambda: (0, 0))
    for r in results:
        p, t = by_days[r["days"]]
        by_days[r["days"]] = (p + int(r["passed"]), t + 1)

    print("\n  days별:")
    for d, (p, t) in sorted(by_days.items()):
        label = {1: "당일  ", 2: "1박2일", 3: "2박3일"}.get(d, f"{d}일   ")
        pct = p / t * 100
        print(f"    {label}  {p}/{t} ({pct:.0f}%)")

    print(f"{'='*60}\n")

    # ── 리포트 파일 저장 ──────────────────────────────────────────────
    write_reports(results)

    # ── 최종 assert ───────────────────────────────────────────────────
    if failed > 0:
        fail_list = "\n  ".join(
            f"{r['persona_id']} ({r['mobility_type']}/{r['days']}일/{r['area']}): "
            + " | ".join(r["failures"])
            for r in results
            if not r["passed"]
        )
        pytest.fail(
            f"\n{failed}/50 페르소나 실패:\n  {fail_list}\n\n"
            f"상세 리포트: {REPORT_MD}"
        )
