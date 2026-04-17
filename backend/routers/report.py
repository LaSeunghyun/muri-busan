"""POST /api/report, GET /api/reports/{spot_id} — 현장 접근성 신고 엔드포인트."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "reports.db"

_VALID_ISSUE_TYPES = {
    "barrier_added",
    "elevator_broken",
    "restroom_closed",
    "accessible",
    "other",
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_report_db() -> None:
    """앱 시작 시 호출하여 신고 테이블을 생성한다."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                spot_id TEXT NOT NULL,
                spot_name TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                description TEXT DEFAULT '',
                lat REAL,
                lng REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_spot_id ON reports (spot_id)"
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("report DB 초기화 완료: %s", _DB_PATH)


class ReportRequest(BaseModel):
    spot_id: str = Field(..., min_length=1, max_length=64)
    spot_name: str = Field(..., min_length=1, max_length=200)
    issue_type: str = Field(..., description="barrier_added|elevator_broken|restroom_closed|accessible|other")
    description: str = Field(default="", max_length=500)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


class ReportResponse(BaseModel):
    id: str
    message: str


@router.post("/api/report", response_model=ReportResponse)
async def create_report(req: ReportRequest):
    if req.issue_type not in _VALID_ISSUE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"유효하지 않은 신고 유형입니다. 가능한 값: {', '.join(sorted(_VALID_ISSUE_TYPES))}",
        )

    report_id = uuid.uuid4().hex[:12]
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO reports (id, spot_id, spot_name, issue_type, description, lat, lng)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (report_id, req.spot_id, req.spot_name, req.issue_type, req.description, req.lat, req.lng),
        )
        conn.commit()
    except Exception as e:
        logger.error("신고 저장 실패: %s", e)
        raise HTTPException(status_code=500, detail="신고 저장에 실패했습니다.")
    finally:
        conn.close()

    return {"id": report_id, "message": "감사합니다! 데이터 개선에 도움이 됩니다."}


@router.get("/api/reports/{spot_id}")
async def get_reports(spot_id: str):
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, spot_id, spot_name, issue_type, description, lat, lng, created_at FROM reports WHERE spot_id = ? ORDER BY created_at DESC LIMIT 50",
            (spot_id,),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": r[0],
            "spot_id": r[1],
            "spot_name": r[2],
            "issue_type": r[3],
            "description": r[4],
            "lat": r[5],
            "lng": r[6],
            "created_at": r[7],
        }
        for r in rows
    ]
