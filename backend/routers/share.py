"""POST /api/share, GET /api/share/{token} — 일정 공유 엔드포인트 (SQLite 영속화, 24시간 만료)."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.store import course_store

_SHARE_TTL_HOURS = 24

logger = logging.getLogger(__name__)
router = APIRouter()

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "share.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_share_db() -> None:
    """앱 시작 시 호출하여 테이블을 생성한다."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS shares (
                token TEXT PRIMARY KEY,
                course_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )"""
        )
        # 기존 테이블에 expires_at 컬럼이 없는 경우 마이그레이션
        try:
            conn.execute("SELECT expires_at FROM shares LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE shares ADD COLUMN expires_at TIMESTAMP")
            conn.execute(
                "UPDATE shares SET expires_at = datetime(created_at, '+24 hours') WHERE expires_at IS NULL"
            )
        conn.commit()
    finally:
        conn.close()
    logger.info("share DB 초기화 완료: %s", _DB_PATH)


class ShareRequest(BaseModel):
    course_id: str | None = None
    course: dict | None = None


class ShareResponse(BaseModel):
    token: str
    url: str


@router.post("/api/share", response_model=ShareResponse)
async def create_share(req: ShareRequest):
    course = course_store.get(req.course_id) if req.course_id else None
    if not course and req.course:
        course = req.course
    if not course:
        raise HTTPException(status_code=404, detail="코스를 찾을 수 없습니다.")
    course_id = course.get("id")
    if not course_id:
        raise HTTPException(status_code=400, detail="공유할 코스 데이터에 id가 필요합니다.")

    course_store.put(course_id, course)
    token = uuid.uuid4().hex[:8]
    expires_at = datetime.now(timezone.utc) + timedelta(hours=_SHARE_TTL_HOURS)

    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO shares (token, course_json, expires_at) VALUES (?, ?, ?)",
            (token, json.dumps(course, ensure_ascii=False), expires_at.isoformat()),
        )
        conn.commit()
    except Exception as e:
        logger.error("공유 링크 저장 실패: %s", e)
        raise HTTPException(status_code=500, detail="공유 링크 저장에 실패했습니다.")
    finally:
        conn.close()

    return {"token": token, "url": f"/share.html?token={token}"}


@router.get("/api/share/{token}")
async def get_share(token: str):
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT course_json, expires_at FROM shares WHERE token = ?", (token,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="공유 링크를 찾을 수 없습니다.")

    # 만료 체크
    if row[1]:
        try:
            expires_at = datetime.fromisoformat(row[1])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                raise HTTPException(status_code=410, detail="공유 링크가 만료되었습니다. (24시간 경과)")
        except (ValueError, TypeError):
            pass  # 파싱 실패 시 만료 체크 건너뜀

    return json.loads(row[0])
