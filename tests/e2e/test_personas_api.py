"""
50개 페르소나 - 알고리즘 직접 호출 기반 테스트 (브라우저 불필요)

목적:
  - Playwright 브라우저 없이 추천 알고리즘을 직접 임포트해 검증
  - 각 페르소나별: courses >= 1, fatigue < 250, accessibility_avg >= expected_quality
  - tests/e2e/report_personas.json + .md 저장

실행:
  pytest tests/e2e/test_personas_api.py -v -s
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

# ── 경로 ──────────────────────────────────────────────────────────────────
E2E_DIR = Path(__file__).resolve().parent
PERSONAS_FILE = E2E_DIR / "personas.json"
REPORT_JSON = E2E_DIR / "report_personas.json"
REPORT_MD = E2E_DIR / "report_personas.md"

MAX_DAILY_FATIGUE = 250.0   # algorithm.py 와 동일


# ══════════════════════════════════════════════════════════════════════════════
# Mock 스팟 풀 생성
#   - 6개 권역 × 6개 카테고리 × 5개씩 = 180개 스팟
#   - 모든 mobility_type 필터를 동시 충족 (worst-case 조건)
# ══════════════════════════════════════════════════════════════════════════════

AREAS = ["해운대", "수영", "남포", "남구", "기장", "서구"]
CATEGORIES = ["문화", "공원", "쇼핑", "해수욕장", "전망", "음식"]

# 기장 권역 좌표 기준 (위경도)
AREA_COORDS: dict[str, tuple[float, float]] = {
    "해운대": (35.1587, 129.1604),
    "수영":   (35.1435, 129.1133),
    "남포":   (35.0979, 129.0300),
    "남구":   (35.1365, 129.0862),
    "기장":   (35.2447, 129.2163),
    "서구":   (35.1073, 129.0210),
}


def _make_spot_pool() -> list[dict[str, Any]]:
    """모든 mobility_type 필터를 통과하는 스팟 풀."""
    pool = []
    for area in AREAS:
        base_lat, base_lng = AREA_COORDS[area]
        for cat_idx, category in enumerate(CATEGORIES):
            for i in range(5):
                sid = f"mock_{area}_{cat_idx}_{i}"
                pool.append({
                    "id": sid,
                    "name": f"{area} {category} {i + 1}",
                    "category": category,
                    "area": area,
                    "lat": base_lat + (cat_idx * 5 + i) * 0.002,
                    "lng": base_lng + (cat_idx * 5 + i) * 0.002,
                    # ── 접근성 (모든 타입 통과 조건) ──
                    "wheelchair_accessible": True,
                    "stroller_accessible": True,
                    "accessibility_grade": 4,       # senior/carrier: >= 3
                    "slope_pct": 2.0,               # carrier: <= 5, senior: <= 8
                    "restroom_accessible": True,
                    "elevator": True,
                    "tags": ["실내"],
                    # ── 시간/피로도 ──
                    "visit_time_min": 60,
                    "wait_time_min": 5,
                    "_festival": False,
                })
    return pool


SPOT_POOL = _make_spot_pool()   # 180개 스팟, 세션 내 공유


# ══════════════════════════════════════════════════════════════════════════════
# 단일 페르소나 검증
# ══════════════════════════════════════════════════════════════════════════════

def validate_persona(persona: dict[str, Any]) -> dict[str, Any]:
    """
    알고리즘을 직접 호출해 페르소나 조건을 검증한다.

    반환:
      passed        : bool
      failures      : list[str] - 실패 사유
      courses_count : int
      first_fatigue : float | None
      first_acc_avg : float | None
      duration_ms   : int
    """
    from backend.services.algorithm import recommend_courses  # 로컬 임포트 (빠른 실패 방지)

    pid = persona["id"]
    mobility_type = persona["mobility_type"]
    days = persona["days"]
    area = persona.get("area", "")
    areas = [area] if area else []
    expected_quality = persona["expected_course_quality"]

    result: dict[str, Any] = {
        "persona_id": pid,
        "name": persona["name"],
        "mobility_type": mobility_type,
        "days": days,
        "area": area,
        "age_group": persona.get("age_group", ""),
        "special_conditions": persona.get("special_conditions"),
        "expected_course_quality": expected_quality,
        "passed": False,
        "failures": [],
        "courses_count": 0,
        "first_fatigue": None,
        "first_acc_avg": None,
        "duration_ms": 0,
    }

    t0 = time.time()
    try:
        courses = recommend_courses(
            spots=SPOT_POOL,
            mobility_types=[mobility_type],
            days=days,
            areas=areas,
            is_rainy=False,
        )

        result["courses_count"] = len(courses)

        # ── 검증 1: 코스 1개 이상 ──────────────────────────────────
        if not courses:
            result["failures"].append(f"코스 0개 (권역={area}, 유형={mobility_type})")
        else:
            first = courses[0]
            fatigue = first.get("total_fatigue", 9999)
            acc_avg = first.get("accessibility_avg", 0.0)
            result["first_fatigue"] = round(fatigue, 2)
            result["first_acc_avg"] = round(acc_avg, 2)

            # ── 검증 2: 피로도 < 250 ──────────────────────────────
            if fatigue >= MAX_DAILY_FATIGUE:
                result["failures"].append(
                    f"피로도 초과: {fatigue:.1f} >= {MAX_DAILY_FATIGUE}"
                )

            # ── 검증 3: 접근성 등급 >= expected_course_quality ───
            if acc_avg < expected_quality:
                result["failures"].append(
                    f"접근성 등급 미달: {acc_avg:.1f} < {expected_quality:.1f}"
                )

            # ── 검증 4: 멀티데이 일수 일치 ───────────────────────
            actual_days = len({c["day"] for c in courses})
            if actual_days < days:
                result["failures"].append(
                    f"day 수 부족: {actual_days} < {days} (스팟 풀 부족 가능)"
                )

        result["passed"] = len(result["failures"]) == 0

    except Exception as exc:
        result["failures"].append(f"{type(exc).__name__}: {str(exc)[:200]}")

    result["duration_ms"] = round((time.time() - t0) * 1000)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 리포트 저장
# ══════════════════════════════════════════════════════════════════════════════

def write_reports(results: list[dict[str, Any]]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    by_mobility: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_mobility[r["mobility_type"]].append(r["passed"])

    mobility_stats = {
        mt: {
            "total": len(v),
            "passed": sum(v),
            "rate_pct": round(sum(v) / len(v) * 100, 1),
        }
        for mt, v in by_mobility.items()
    }

    by_days: dict[int, list[bool]] = defaultdict(list)
    for r in results:
        by_days[r["days"]].append(r["passed"])

    days_stats = {
        d: {
            "total": len(v),
            "passed": sum(v),
            "rate_pct": round(sum(v) / len(v) * 100, 1),
        }
        for d, v in sorted(by_days.items())
    }

    bugs = [
        {
            "persona_id": r["persona_id"],
            "name": r["name"],
            "mobility_type": r["mobility_type"],
            "days": r["days"],
            "area": r["area"],
            "failures": r["failures"],
        }
        for r in results
        if not r["passed"]
    ]

    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "test_method": "algorithm-direct (no browser)",
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

    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ── Markdown ──────────────────────────────────────────────────────────
    lines = [
        "# 페르소나 API 레이어 테스트 결과",
        "",
        f"**생성**: {report['generated_at']}  |  **방법**: 알고리즘 직접 호출 (브라우저 없음)",
        "",
        "## 요약",
        "",
        "| 항목 | 값 |",
        "|------|----|",
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
        lines.append(f"| {mt} | {s['total']} | {s['passed']} | {s['rate_pct']}% |")

    lines += [
        "",
        "## days별 통과율",
        "",
        "| 일정 | 총 | 통과 | 통과율 |",
        "|------|----|------|--------|",
    ]
    for d, s in days_stats.items():
        label = {1: "당일(1일)", 2: "1박2일", 3: "2박3일"}.get(d, f"{d}일")
        lines.append(f"| {label} | {s['total']} | {s['passed']} | {s['rate_pct']}% |")

    if bugs:
        lines += [
            "",
            "## 실패 페르소나 및 실패 이유",
            "",
            "| ID | 이름 | 유형 | 일정 | 권역 | 실패 이유 |",
            "|----|------|------|------|------|-----------|",
        ]
        for b in bugs:
            reason = " / ".join(b["failures"])
            lines.append(
                f"| {b['persona_id']} | {b['name']} | {b['mobility_type']} "
                f"| {b['days']}일 | {b['area']} | {reason} |"
            )
    else:
        lines += ["", "## 발견된 버그", "", "없음 - 모든 페르소나 통과"]

    lines += [
        "",
        "## 전체 결과",
        "",
        "| ID | 이름 | 유형 | 일정 | 권역 | 코스수 | 피로도 | 접근성 | 결과 |",
        "|----|------|------|------|------|--------|--------|--------|------|",
    ]
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        fat = f"{r['first_fatigue']:.1f}" if r["first_fatigue"] is not None else "-"
        acc = f"{r['first_acc_avg']:.1f}" if r["first_acc_avg"] is not None else "-"
        lines.append(
            f"| {r['persona_id']} | {r['name']} | {r['mobility_type']} "
            f"| {r['days']}일 | {r['area']} | {r['courses_count']} "
            f"| {fat} | {acc} | {status} |"
        )

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# pytest 엔트리포인트
# ══════════════════════════════════════════════════════════════════════════════

def test_50_personas_api():
    """
    50개 페르소나를 알고리즘 직접 호출로 검증한다 (브라우저/서버 불필요).
    """
    assert PERSONAS_FILE.exists(), f"personas.json 없음: {PERSONAS_FILE}"
    personas: list[dict] = json.loads(PERSONAS_FILE.read_text(encoding="utf-8"))
    assert len(personas) == 50

    results: list[dict[str, Any]] = []

    print(f"\n{'='*62}")
    print(f"  50 personas API test  -  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*62}\n")

    for idx, persona in enumerate(personas, 1):
        r = validate_persona(persona)
        results.append(r)
        mark = "OK" if r["passed"] else "NG"
        fat = f"{r['first_fatigue']:.1f}" if r["first_fatigue"] is not None else "  - "
        acc = f"{r['first_acc_avg']:.1f}" if r["first_acc_avg"] is not None else "  -"
        fail_msg = f"  >> {r['failures'][0][:55]}" if not r["passed"] else ""
        print(
            f"[{idx:>2}/50] {r['persona_id']} {r['mobility_type']:10s} "
            f"{r['days']}d {r['area']:4s} | "
            f"코스:{r['courses_count']:2d} fat:{fat} acc:{acc} [{mark}]{fail_msg}"
        )

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    by_mt: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    for r in results:
        p, t = by_mt[r["mobility_type"]]
        by_mt[r["mobility_type"]] = (p + int(r["passed"]), t + 1)

    print(f"\n{'='*62}")
    print(f"  결과: {passed}/{total} PASS  ({failed} FAIL)")
    print(f"  mobility_type별:")
    for mt, (p, t) in sorted(by_mt.items()):
        bar = "#" * p + "." * (t - p)
        print(f"    {mt:12s} [{bar}] {p}/{t}")
    print(f"{'='*62}\n")

    write_reports(results)
    print(f"  리포트: {REPORT_JSON.name} / {REPORT_MD.name}")

    if failed:
        fail_summary = "\n  ".join(
            f"{r['persona_id']} ({r['mobility_type']}/{r['days']}d/{r['area']}): "
            + " | ".join(r["failures"])
            for r in results
            if not r["passed"]
        )
        pytest.fail(f"\n{failed}/50 FAIL:\n  {fail_summary}")
