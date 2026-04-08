"""GET /api/search-places — 키워드로 부산 장소 검색 (TourAPI searchKeyword2 + 캐시 폴백)."""
from __future__ import annotations

import os
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter

from backend.services.tourapi import TOUR_API_BASE, TOUR_API_KEY, fetch_spots

router = APIRouter()


def _encoded_key() -> str:
    return TOUR_API_KEY if "%" in TOUR_API_KEY else quote(TOUR_API_KEY, safe="")


@router.get("/api/search-places")
async def search_places(keyword: str = ""):
    """카카오 Places 대체 검색 엔드포인트.

    1차: TourAPI searchKeyword2 (부산 areaCode=6)
    2차 폴백: 캐시된 스팟에서 이름 매칭
    반환 형식: [{place_name, category_name, address_name, x, y, phone, place_url}]
    """
    keyword = keyword.strip()
    if not keyword:
        return []

    # 1차: TourAPI searchKeyword2
    if TOUR_API_KEY:
        try:
            ek = _encoded_key()
            params = urlencode({
                "numOfRows": "20", "pageNo": "1",
                "MobileOS": "ETC", "MobileApp": "MurieopsBusan", "_type": "json",
                "keyword": keyword, "areaCode": "6",
            })
            url = f"{TOUR_API_BASE}/searchKeyword2?serviceKey={ek}&{params}"
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(url)
                r.raise_for_status()
                body = r.json()["response"]["body"]
                items = body.get("items")
                if items:
                    item_list = items.get("item", [])
                    if isinstance(item_list, dict):
                        item_list = [item_list]
                    if item_list:
                        return [_to_kakao_format(it) for it in item_list[:10]]
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("TourAPI searchKeyword2 failed: %s", exc)

    # 2차 폴백: 캐시된 스팟 이름 매칭
    try:
        spots = await fetch_spots()
        kw_lower = keyword.strip()[:100].lower()
        matched = [
            s for s in spots
            if kw_lower in s.get("name", "").lower()
        ][:10]
        return [_spot_to_kakao_format(s) for s in matched]
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Spot cache fallback failed: %s", exc)
        return []


def _to_kakao_format(item: dict) -> dict:
    """TourAPI searchKeyword2 item → 카카오 Places 형식."""
    addr = item.get("addr1", "") or ""
    if item.get("addr2"):
        addr = f"{addr} {item['addr2']}".strip()
    content_type_id = str(item.get("contenttypeid", ""))
    category = _content_type_to_category(content_type_id)
    lng = str(item.get("mapx", ""))
    lat = str(item.get("mapy", ""))
    content_id = item.get("contentid", "")
    place_url = (
        f"https://www.visitkorea.or.kr/detail?contentId={content_id}"
        if content_id else ""
    )
    return {
        "place_name": item.get("title", ""),
        "category_name": category,
        "address_name": addr,
        "x": lng,
        "y": lat,
        "phone": item.get("tel", "") or "",
        "place_url": place_url,
    }


def _spot_to_kakao_format(spot: dict) -> dict:
    """내부 스팟 dict → 카카오 Places 형식."""
    return {
        "place_name": spot.get("name", ""),
        "category_name": spot.get("category", "관광지"),
        "address_name": spot.get("description", ""),
        "x": str(spot.get("lng", "")),
        "y": str(spot.get("lat", "")),
        "phone": "",
        "place_url": "",
    }


def _content_type_to_category(content_type_id: str) -> str:
    mapping = {
        "12": "관광지",
        "14": "문화시설",
        "15": "행사/공연/축제",
        "25": "여행코스",
        "28": "레포츠",
        "32": "숙박",
        "38": "쇼핑",
        "39": "음식점",
    }
    return mapping.get(content_type_id, "장소")
