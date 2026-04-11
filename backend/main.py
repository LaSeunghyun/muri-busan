# 실행: python -m uvicorn backend.main:app --reload --port 8000
# 접속: http://localhost:8000
"""무리없이 부산 — FastAPI 메인 앱."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # 반드시 라우터 import 전에 호출해야 모듈 레벨 os.getenv가 정상 동작

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.routers import analytics, courses, recommend, report, search, share, weather


@asynccontextmanager
async def lifespan(app: FastAPI):
    share.init_share_db()
    share.cleanup_expired_shares()
    report.init_report_db()
    logger.info("앱 시작 완료")
    yield

# ── 로깅 설정 ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="무리없이 부산",
    description="이동약자 맞춤 부산 관광 코스 추천 서비스",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS 화이트리스트 ──────────────────────────────────────────────
_default_origins = "http://localhost:8000,http://127.0.0.1:8000"
_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate Limiting (경량 미들웨어) ──────────────────────────────────
# 경로별 제한: (최대 요청 수, 윈도우 초)
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/recommend": (10, 60),   # IP당 분당 10회
    "/api/share": (20, 60),       # IP당 분당 20회 (POST만)
    "/api/log/recommend": (30, 60),  # IP당 분당 30회
    "/api/log/survey": (10, 60),     # IP당 분당 10회 (같은 세션이 여러번 제출 방지)
}
_rate_buckets: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    limit_config = _RATE_LIMITS.get(path)
    if limit_config and request.method == "POST":
        max_requests, window_sec = limit_config
        client_ip = request.client.host if request.client else "unknown"
        bucket_key = f"{client_ip}:{path}"
        now = time.time()

        # 만료된 항목 제거
        _rate_buckets[bucket_key] = [
            t for t in _rate_buckets[bucket_key] if now - t < window_sec
        ]

        if len(_rate_buckets[bucket_key]) >= max_requests:
            logger.warning("Rate limit 초과: %s %s", client_ip, path)
            return JSONResponse(
                status_code=429,
                content={"detail": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."},
            )
        _rate_buckets[bucket_key].append(now)

    return await call_next(request)


# 라우터 등록
app.include_router(recommend.router)
app.include_router(courses.router)
app.include_router(share.router)
app.include_router(weather.router)
app.include_router(search.router)
app.include_router(report.router)
app.include_router(analytics.router)




@app.get("/runtime-config.js")
async def runtime_config():
    kakao_map_key = os.getenv("KAKAO_MAP_KEY", "").strip()
    javascript = (
        "window.RUNTIME_CONFIG = window.RUNTIME_CONFIG || {};\n"
        f"window.RUNTIME_CONFIG.kakaoMapKey = {json.dumps(kakao_map_key or None)};\n"
        "window.KAKAO_MAP_KEY = window.RUNTIME_CONFIG.kakaoMapKey;\n"
    )
    return Response(
        content=javascript,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )

# 정적 파일 서빙 (frontend/)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
