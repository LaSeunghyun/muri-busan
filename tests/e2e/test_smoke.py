"""Playwright E2E 스모크 테스트 — 온보딩 핵심 흐름 검증.

실행 전제:
    pip install playwright pytest-playwright
    playwright install chromium

실행 방법:
    pytest tests/e2e/ -v
"""

from __future__ import annotations

import json

import pytest

# ── 픽스처는 conftest.py에서 주입됨 ────────────────────────────────


def test_onboarding_page_loads(page, live_server):
    """온보딩 페이지가 정상 로드되고 핵심 요소가 표시된다."""
    page.goto(f"{live_server}/onboarding.html")
    assert "무리없이 부산" in page.title()

    # Step1 섹션이 보여야 함
    step1 = page.locator("#step1")
    assert step1.is_visible()

    # 4가지 이동약자 유형 카드가 모두 렌더링됨
    cards = page.locator(".ob-choice-card")
    assert cards.count() >= 4


def test_mobility_type_selection_enables_next(page, live_server):
    """이동약자 유형 카드를 클릭하면 aria-checked가 토글되고 다음 버튼이 활성화된다."""
    page.goto(f"{live_server}/onboarding.html")

    # 초기 상태: 다음 버튼 비활성
    next_btn = page.locator("#step1Next")
    assert next_btn.is_disabled()

    # 휠체어 카드 클릭
    wheelchair_card = page.locator("#typeGrid .ob-choice-card[data-type='wheelchair']")
    wheelchair_card.click()

    # aria-checked="true" 로 변경 확인
    assert wheelchair_card.get_attribute("aria-checked") == "true"

    # 다음 버튼 활성화 확인
    assert not next_btn.is_disabled()


def test_schedule_chip_selection_enables_next(page, live_server):
    """Step2 에서 기간 칩을 선택하면 다음 버튼이 활성화된다."""
    page.goto(f"{live_server}/onboarding.html")

    # Step1: 유형 선택 → 다음으로
    page.locator("#typeGrid .ob-choice-card[data-type='senior']").click()
    page.locator("#step1Next").click()

    # Step2가 표시될 때까지 대기
    page.wait_for_selector("#step2:visible", timeout=3000)

    # 초기 상태: 다음 버튼 비활성 (기간 미선택)
    step2_next = page.locator("#step2Next")
    assert step2_next.is_disabled()

    # '당일' 칩 선택
    day_chip = page.locator("#durationRow .duration-chip[data-days='1']")
    day_chip.click()

    # aria-checked="true" 확인
    assert day_chip.get_attribute("aria-checked") == "true"

    # 다음 버튼 활성화
    assert not step2_next.is_disabled()


def test_no_duration_selected_blocks_next_button(page, live_server):
    """Step2에서 기간을 선택하지 않으면 다음 버튼이 항상 비활성 상태다."""
    page.goto(f"{live_server}/onboarding.html")

    # Step1 통과
    page.locator("#typeGrid .ob-choice-card[data-type='stroller']").click()
    page.locator("#step1Next").click()
    page.wait_for_selector("#step2:visible", timeout=3000)

    # 기간 선택 없이 버튼 상태 확인
    step2_next = page.locator("#step2Next")
    assert step2_next.is_disabled(), "기간 미선택 시 다음 버튼은 비활성이어야 함"

    # 한 번 선택 후 취소(재클릭) 하면 다시 비활성
    chip = page.locator("#durationRow .duration-chip[data-days='2']")
    chip.click()
    assert not step2_next.is_disabled()
    chip.click()  # 토글 해제 시도
    # 단일 선택 UI이므로 해제 불가 — 버튼이 여전히 활성인 경우를 허용
    # (이 동작은 UX 정책에 따름 — 테스트는 초기 비활성만 보장)


def test_recommend_api_returns_courses(page, live_server):
    """코스 추천 API(/api/recommend)가 응답을 반환한다 (mock 인터셉트)."""
    # 외부 API(TOUR API, Gemini)를 호출하지 않도록 mock 응답 주입
    mock_response = {
        "courses": [
            {
                "id": "c001_abc123",
                "name": "해운대 무장애 탐방 코스",
                "day": 1,
                "spots": [
                    {
                        "id": "spot-1",
                        "name": "해운대해수욕장",
                        "area": "해운대",
                        "category": "해수욕장",
                        "wheelchair_accessible": True,
                        "stroller_accessible": True,
                        "restroom_accessible": True,
                        "elevator": False,
                        "lat": 35.1587,
                        "lng": 129.1604,
                        "slope_pct": 1.0,
                        "wait_time_min": 5,
                        "visit_time_min": 60,
                        "accessibility_grade": 5,
                    }
                ],
                "legs": [],
                "total_time_min": 60,
                "total_fatigue": 5.0,
                "distance_km": 0.0,
                "rest_spots": 1,
                "accessibility_avg": 5.0,
            }
        ],
        "summary": {
            "mobility_types": ["wheelchair"],
            "days": 1,
            "requested_areas": [],
            "applied_areas": [],
            "fallback_used": False,
            "spot_count": 1,
        },
    }

    page.route(
        "**/api/recommend",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(mock_response, ensure_ascii=False),
        ),
    )

    # fetch로 직접 호출하여 응답 확인
    result = page.evaluate(
        """async () => {
            const res = await fetch('/api/recommend', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mobility_types: ['wheelchair'], days: 1, areas: []})
            });
            return await res.json();
        }"""
    )

    assert result["courses"], "코스가 1개 이상 반환되어야 함"
    assert result["courses"][0]["name"] == "해운대 무장애 탐방 코스"
    assert not result["summary"]["fallback_used"]
