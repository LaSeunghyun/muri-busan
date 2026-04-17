"""GET /api/spot-detail/{content_id} — TourAPI detailCommon2 + detailIntro2 + detailImage2 통합 조회.

스팟 상세 모달에서 운영시간·휴일·주차·추가 이미지를 on-demand 로드한다.
content_id 는 숫자 문자열이며 최대 16자리로 제한한다.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from backend.services.tourapi import fetch_spot_detail

router = APIRouter()

_CONTENT_ID_RE = re.compile(r"^[0-9]{1,16}$")


@router.get("/api/spot-detail/{content_id}")
async def get_spot_detail(content_id: str, content_type_id: str = "12"):
    # content_id 화이트리스트 — 숫자 1~16자리만 허용
    if not _CONTENT_ID_RE.match(content_id):
        raise HTTPException(status_code=400, detail="잘못된 content_id 형식입니다.")
    # contentTypeId: 12 관광지, 14 문화시설, 15 축제, 28 레포츠, 32 숙박, 38 쇼핑, 39 음식점
    if content_type_id not in {"12", "14", "15", "25", "28", "32", "38", "39"}:
        content_type_id = "12"

    detail = await fetch_spot_detail(content_id, content_type_id)
    if not detail:
        raise HTTPException(status_code=404, detail="상세 정보를 찾을 수 없습니다.")
    return detail
