"""GET /api/meta/* — TourAPI areaCode2 · categoryCode2 기반 메타 정보 노출.

- /api/meta/busan-sigungu — 부산(areaCode=6) 내 시군구 공식 코드·명칭
- /api/meta/tour-categories — 관광 유형 분류 코드 (cat1 또는 cat1+cat2 지정 가능)

타 지역 확장 시 지역 코드 동적 조회 경로를 확보하고, 관광지 카테고리 매핑의
공식 출처(한국관광공사 OpenAPI)를 증빙하는 용도이다.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from backend.services.tourapi import fetch_area_codes, fetch_category_codes

router = APIRouter()

_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")


@router.get("/api/meta/busan-sigungu")
async def get_busan_sigungu():
    """부산광역시(areaCode=6) 시군구 코드·명칭 목록."""
    codes = await fetch_area_codes("6")
    return {"area_code": "6", "area_name": "부산광역시", "items": codes}


@router.get("/api/meta/tour-categories")
async def get_tour_categories(cat1: str = "", cat2: str = ""):
    """관광 유형 분류 코드. cat1/cat2 미지정 시 최상위 분류 반환."""
    if cat1 and not _CODE_RE.match(cat1):
        raise HTTPException(status_code=400, detail="cat1 형식이 올바르지 않습니다.")
    if cat2 and not _CODE_RE.match(cat2):
        raise HTTPException(status_code=400, detail="cat2 형식이 올바르지 않습니다.")
    items = await fetch_category_codes(cat1, cat2)
    return {"cat1": cat1 or None, "cat2": cat2 or None, "items": items}
