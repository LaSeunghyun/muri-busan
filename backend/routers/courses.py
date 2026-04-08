"""GET /api/courses/{course_id} — 코스 상세 엔드포인트."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.store import course_store

router = APIRouter()


def cache_courses(courses: list[dict]) -> None:
    """추천 결과를 캐시에 저장."""
    course_store.put_many(courses)


@router.get("/api/courses/{course_id}")
async def get_course(course_id: str):
    course = course_store.get(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="코스를 찾을 수 없습니다.")
    return course
