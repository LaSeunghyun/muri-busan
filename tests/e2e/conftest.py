"""E2E 테스트 공통 픽스처: 로컬 서버 기동 + Playwright 브라우저."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BASE_URL = "http://localhost:18765"


@pytest.fixture(scope="session")
def live_server():
    """uvicorn 서버를 세션 동안 한 번만 기동한다."""
    env = os.environ.copy()
    # 더미 환경변수 — E2E 테스트에서는 실제 외부 API 호출 없음
    env.setdefault("TOUR_API_KEY", "e2e-test-dummy")
    env.setdefault("GEMINI_API_KEY", "e2e-test-dummy")
    env.setdefault("KAKAO_MAP_KEY", "e2e-test-dummy")

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.main:app",
            "--host", "127.0.0.1",
            "--port", "18765",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 서버 기동 대기 (최대 10초)
    import urllib.request
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE_URL}/onboarding.html", timeout=1)
            break
        except Exception:
            time.sleep(0.3)

    yield BASE_URL

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def playwright_instance():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance):
    b = playwright_instance.chromium.launch(headless=True)
    yield b
    b.close()


@pytest.fixture
def page(browser, live_server):
    """각 테스트마다 새 페이지(탭)를 생성한다."""
    p = browser.new_page()
    p.set_default_timeout(10_000)
    yield p
    p.close()
