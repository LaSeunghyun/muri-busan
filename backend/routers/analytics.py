"""POST /api/log/recommend, /api/log/survey — 사용 로그 및 만족도 조사 저장."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.supabase_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()


class RecommendLogRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    days: int = Field(..., ge=1, le=5)
    mobility_types: list[str] = Field(default_factory=list)
    areas: list[str] = Field(default_factory=list)
    start_date: Optional[str] = None
    course_ids: list[str] = Field(default_factory=list)
    course_count: int = 0
    fallback_used: bool = False
    ai_enabled: bool = False


class RecommendLogResponse(BaseModel):
    ok: bool
    log_id: Optional[str] = None


class SurveyRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    log_id: Optional[str] = None
    score: int = Field(..., ge=1, le=5)
    reason_categories: list[str] = Field(default_factory=list)
    reason_text: Optional[str] = Field(default=None, max_length=500)


class SurveyResponse(BaseModel):
    ok: bool
    survey_id: Optional[str] = None


@router.post("/api/log/recommend", response_model=RecommendLogResponse)
async def log_recommendation(req: RecommendLogRequest):
    """추천 요청 로그 저장. Supabase 미설정이면 no-op으로 OK 반환."""
    client = get_client()
    if not client:
        return RecommendLogResponse(ok=True, log_id=None)

    try:
        data = {
            "session_id": req.session_id,
            "days": req.days,
            "mobility_types": req.mobility_types,
            "areas": req.areas,
            "start_date": req.start_date,
            "course_ids": req.course_ids[:50],
            "course_count": req.course_count,
            "fallback_used": req.fallback_used,
            "ai_enabled": req.ai_enabled,
        }
        result = client.table("recommendation_logs").insert(data).execute()
        rows = getattr(result, "data", None) or []
        log_id = rows[0].get("id") if rows else None
        return RecommendLogResponse(ok=True, log_id=log_id)
    except Exception as e:
        logger.warning("추천 로그 저장 실패: %s", e)
        # 로깅 실패해도 사용자 경험 영향 없도록 200 반환
        return RecommendLogResponse(ok=False, log_id=None)


@router.post("/api/log/survey", response_model=SurveyResponse)
async def log_survey(req: SurveyRequest):
    """만족도 조사 저장."""
    client = get_client()
    if not client:
        return SurveyResponse(ok=True, survey_id=None)

    try:
        data = {
            "session_id": req.session_id,
            "log_id": req.log_id,
            "score": req.score,
            "reason_categories": req.reason_categories[:10],
            "reason_text": (req.reason_text or "").strip() or None,
        }
        result = client.table("satisfaction_surveys").insert(data).execute()
        rows = getattr(result, "data", None) or []
        survey_id = rows[0].get("id") if rows else None
        return SurveyResponse(ok=True, survey_id=survey_id)
    except Exception as e:
        logger.warning("만족도 저장 실패: %s", e)
        raise HTTPException(status_code=500, detail="설문 저장에 실패했어요. 잠시 후 다시 시도해주세요.")
