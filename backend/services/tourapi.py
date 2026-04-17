"""TourAPI 클라이언트 — TourAPI 실데이터 + 자체 큐레이션 접근성 검증 데이터 병합."""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from urllib.parse import quote, urlencode

import logging

import httpx

logger = logging.getLogger(__name__)
TOUR_API_KEY = os.getenv("TOUR_API_KEY", "")
TOUR_API_BASE = "https://apis.data.go.kr/B551011/KorService2"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ACCESS_CACHE_FILE = DATA_DIR / "accessibility_cache.json"
ACCESS_CACHE_TTL = 86400  # 24시간

_spots_cache: dict = {}
_access_cache: dict = {}   # contentid → {wheelchair, elevator, restroom, stroller}
SPOTS_CACHE_TTL = 3600
_curated_cache: list[dict] | None = None


def _encoded_key() -> str:
    return TOUR_API_KEY if "%" in TOUR_API_KEY else quote(TOUR_API_KEY, safe="")


def _curated_spots() -> list[dict]:
    global _curated_cache
    if _curated_cache is None:
        with open(DATA_DIR / "busan_spots.json", encoding="utf-8") as f:
            _curated_cache = json.load(f)
    return _curated_cache


# ── 접근성 캐시 로드/저장 ─────────────────────────────────────────
def _load_access_cache() -> None:
    global _access_cache
    if ACCESS_CACHE_FILE.exists():
        try:
            data = json.loads(ACCESS_CACHE_FILE.read_text(encoding="utf-8"))
            if time.time() - data.get("_ts", 0) < ACCESS_CACHE_TTL:
                _access_cache = data.get("items", {})
        except Exception as e:
            logger.warning("접근성 캐시 로드 실패: %s", e)


def _save_access_cache() -> None:
    try:
        ACCESS_CACHE_FILE.write_text(
            json.dumps({"_ts": time.time(), "items": _access_cache}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("접근성 캐시 저장 실패: %s", e)


def _parse_bool(text: str) -> bool | None:
    """'가능', '있음', 'Y' → True / '불가', '없음', 'N' → False."""
    t = (text or "").strip()
    if any(k in t for k in ("가능", "있음", "Y", "운영")):
        return True
    if any(k in t for k in ("불가", "없음", "N", "미운영")):
        return False
    return None


async def _fetch_detail_info(client: httpx.AsyncClient, contentid: str) -> dict:
    """detailInfo2 fldgubun=2(장애인) 항목으로 접근성 정보를 조회한다."""
    ek = _encoded_key()
    params = urlencode({
        "MobileOS": "ETC", "MobileApp": "MurieopsBusan", "_type": "json",
        "contentId": contentid, "contentTypeId": "12",
        "numOfRows": "20", "pageNo": "1",
    })
    url = f"{TOUR_API_BASE}/detailInfo2?serviceKey={ek}&{params}"
    try:
        r = await client.get(url, timeout=8.0)
        items = r.json()["response"]["body"]["items"]
        if not items:
            return {}
        item_list = items.get("item", [])
        item_list = item_list if isinstance(item_list, list) else [item_list] if item_list else []

        result: dict[str, bool | None] = {}
        for it in item_list:
            if str(it.get("fldgubun", "")) != "2":  # 장애인 항목만
                continue
            name = it.get("infoname", "")
            text = it.get("infotext", "")
            val = _parse_bool(text)
            if "휠체어" in name:
                result["wheelchair_accessible"] = val if val is not None else True
            elif "엘리베이터" in name or "리프트" in name:
                result["elevator"] = val if val is not None else False
            elif "화장실" in name:
                result["restroom_accessible"] = val if val is not None else True
            elif "유아차" in name or "유모차" in name:
                result["stroller_accessible"] = val if val is not None else True
        return result
    except Exception as e:
        logger.warning("detailInfo2 조회 실패 (contentid=%s): %s", contentid, e)
        return {}


async def _enrich_accessibility(spots: list[dict]) -> list[dict]:
    """detailInfo2로 접근성 데이터를 보강한다 (캐시 우선)."""
    global _access_cache
    if not TOUR_API_KEY:
        return spots

    if not _access_cache:
        _load_access_cache()

    # 캐시에 없는 contentid만 조회
    missing_ids = [
        s["id"].replace("tour_", "")
        for s in spots
        if s["id"].startswith("tour_") and s["id"].replace("tour_", "") not in _access_cache
    ]

    BATCH = 50
    if missing_ids:
        async with httpx.AsyncClient() as client:
            for i in range(0, len(missing_ids), BATCH):
                batch = missing_ids[i:i + BATCH]
                tasks = [_fetch_detail_info(client, cid) for cid in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for cid, res in zip(batch, results):
                    if isinstance(res, dict):
                        _access_cache[cid] = res
        _save_access_cache()

    # 스팟 데이터에 병합
    enriched = []
    for spot in spots:
        cid = spot["id"].replace("tour_", "")
        acc = _access_cache.get(cid, {})
        merged = {**spot}
        for field in ("wheelchair_accessible", "elevator", "restroom_accessible", "stroller_accessible"):
            if field in acc and acc[field] is not None:
                merged[field] = acc[field]
        enriched.append(merged)
    return enriched


# ── 메인 fetch ────────────────────────────────────────────────────
async def fetch_spots(area: str | None = None) -> list[dict]:
    if not TOUR_API_KEY:
        spots = _curated_spots()
        return [s for s in spots if s["area"] == area] if area else spots

    cache_key = f"spots_{area or 'all'}"
    if cache_key in _spots_cache and time.time() - _spots_cache[cache_key][0] < SPOTS_CACHE_TTL:
        return _spots_cache[cache_key][1]

    try:
        ek = _encoded_key()
        params = urlencode({
            "numOfRows": "100", "pageNo": "1",
            "MobileOS": "ETC", "MobileApp": "MurieopsBusan", "_type": "json",
            "areaCode": "6", "contentTypeId": "12",
        })
        url = f"{TOUR_API_BASE}/areaBasedList2?serviceKey={ek}&{params}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            item_list = r.json()["response"]["body"]["items"]["item"]
            item_list = item_list if isinstance(item_list, list) else [item_list] if item_list else []

        spots = _convert_tourapi(item_list)
        spots = await _enrich_accessibility(spots)   # 접근성 보강

        # 접근성 검증이 완료된 자체 큐레이션 실데이터(busan_spots.json)를 병합
        # TourAPI detailInfo2가 대부분 접근성 필드를 비워두므로 별도 확보한 실측 데이터
        curated = _curated_spots()
        existing_ids = {s["id"] for s in spots}
        spots = spots + [m for m in curated if m["id"] not in existing_ids]

        if area:
            spots = [s for s in spots if s["area"] == area]
        _spots_cache[cache_key] = (time.time(), spots)
        return spots

    except Exception as e:
        logger.error("TourAPI 스팟 조회 실패, mock 폴백: %s", e)
        spots = _curated_spots()
        return [s for s in spots if s["area"] == area] if area else spots


def _convert_tourapi(items: list[dict]) -> list[dict]:
    result = []
    for i, item in enumerate(items):
        addr = item.get("addr1", "")
        area = _infer_area(addr)
        result.append({
            "id": f"tour_{item.get('contentid', i)}",
            "name": item.get("title", ""),
            "area": area,
            "lat": float(item.get("mapy", 35.1796)),
            "lng": float(item.get("mapx", 129.0756)),
            "category": "관광지",
            "visit_time_min": 50,
            "slope_pct": 2.0,
            "wait_time_min": 5,
            "wheelchair_accessible": None,   # None=미확인, True=가능, False=불가
            "stroller_accessible": None,
            "elevator": False,
            "restroom_accessible": None,
            "accessibility_grade": 3,
            "description": item.get("addr1", ""),
            "image_url": item.get("firstimage") or None,
            "tags": ["관광"],
        })
    return result


# ── 행사/축제 조회 ───────────────────────────────────────────────
_festival_cache: dict = {}
FESTIVAL_CACHE_TTL = 3600


async def fetch_festivals(start_date: str | None = None) -> list[dict]:
    """searchFestival2 — 여행 시작일 기준 진행 중인 부산 행사 조회.
    start_date: 'YYYYMMDD' 형식. 없으면 오늘 날짜 사용.
    """
    if not TOUR_API_KEY:
        return []

    from datetime import datetime
    if not start_date:
        start_date = datetime.now().strftime("%Y%m%d")

    cache_key = f"fest_{start_date}"
    if cache_key in _festival_cache and time.time() - _festival_cache[cache_key][0] < FESTIVAL_CACHE_TTL:
        return _festival_cache[cache_key][1]

    try:
        ek = _encoded_key()
        params = urlencode({
            "numOfRows": "30", "pageNo": "1",
            "MobileOS": "ETC", "MobileApp": "MurieopsBusan", "_type": "json",
            "areaCode": "6",
            "eventStartDate": start_date,
        })
        url = f"{TOUR_API_BASE}/searchFestival2?serviceKey={ek}&{params}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            body = r.json()["response"]["body"]
            items = body.get("items")
            if not items:
                return []
            item_list = items.get("item", [])
            if isinstance(item_list, dict):
                item_list = [item_list]

        festivals = _convert_festivals(item_list, start_date)
        _festival_cache[cache_key] = (time.time(), festivals)
        return festivals

    except Exception as e:
        logger.error("축제/행사 조회 실패: %s", e)
        return []


def _convert_festivals(items: list[dict], start_date: str) -> list[dict]:
    result = []
    for item in items:
        addr = item.get("addr1", "")
        area = _infer_area(addr)
        evt_start = item.get("eventstartdate", "")
        evt_end = item.get("eventenddate", "")
        result.append({
            "id": f"fest_{item.get('contentid', '')}",
            "name": item.get("title", ""),
            "area": area,
            "lat": float(item.get("mapy", 35.1796)),
            "lng": float(item.get("mapx", 129.0756)),
            "category": "행사/축제",
            "visit_time_min": 70,
            "distance_from_prev_m": 1500,
            "slope_pct": 2.0,
            "wait_time_min": 10,
            "wheelchair_accessible": None,   # 행사별 현장 확인 필요 — 미확인 상태로 처리
            "stroller_accessible": None,
            "elevator": False,
            "restroom_accessible": None,
            "accessibility_grade": 2,         # 미확인 행사는 보수적 등급 적용
            "description": f"{addr} ({evt_start}~{evt_end})",
            "image_url": item.get("firstimage") or None,
            "tags": ["행사", "축제"],
            "_festival": True,
            "_event_start": evt_start,
            "_event_end": evt_end,
        })
    return result


# ── 상세 정보 (detailCommon2 + detailIntro2 + detailImage2) ──────────
_detail_cache: dict = {}
DETAIL_CACHE_TTL = 3600


async def _fetch_detail_common(client: httpx.AsyncClient, content_id: str) -> dict:
    """detailCommon2 — 공통 정보(주소·개요·전화·홈페이지)."""
    ek = _encoded_key()
    params = urlencode({
        "MobileOS": "ETC", "MobileApp": "MurieopsBusan", "_type": "json",
        "contentId": content_id,
        "numOfRows": "1", "pageNo": "1",
    })
    url = f"{TOUR_API_BASE}/detailCommon2?serviceKey={ek}&{params}"
    try:
        r = await client.get(url, timeout=8.0)
        items = r.json()["response"]["body"]["items"]
        if not items:
            return {}
        item = items.get("item", [])
        item = item[0] if isinstance(item, list) and item else item if isinstance(item, dict) else {}
        return {
            "overview": (item.get("overview") or "").strip(),
            "homepage": (item.get("homepage") or "").strip(),
            "tel": (item.get("tel") or "").strip(),
            "addr": (item.get("addr1") or "").strip(),
        }
    except Exception as e:
        logger.warning("detailCommon2 실패 (contentid=%s): %s", content_id, e)
        return {}


async def _fetch_detail_intro(client: httpx.AsyncClient, content_id: str, content_type_id: str = "12") -> dict:
    """detailIntro2 — 유형별 소개 정보(운영시간·휴일·주차·입장료)."""
    ek = _encoded_key()
    params = urlencode({
        "MobileOS": "ETC", "MobileApp": "MurieopsBusan", "_type": "json",
        "contentId": content_id, "contentTypeId": content_type_id,
        "numOfRows": "1", "pageNo": "1",
    })
    url = f"{TOUR_API_BASE}/detailIntro2?serviceKey={ek}&{params}"
    try:
        r = await client.get(url, timeout=8.0)
        items = r.json()["response"]["body"]["items"]
        if not items:
            return {}
        item = items.get("item", [])
        item = item[0] if isinstance(item, list) and item else item if isinstance(item, dict) else {}
        return {
            "usetime": (item.get("usetime") or "").strip(),
            "restdate": (item.get("restdate") or "").strip(),
            "parking": (item.get("parking") or "").strip(),
            "chkpet": (item.get("chkpet") or "").strip(),
        }
    except Exception as e:
        logger.warning("detailIntro2 실패 (contentid=%s): %s", content_id, e)
        return {}


async def _fetch_detail_images(client: httpx.AsyncClient, content_id: str) -> list[str]:
    """detailImage2 — 추가 이미지 갤러리."""
    ek = _encoded_key()
    params = urlencode({
        "MobileOS": "ETC", "MobileApp": "MurieopsBusan", "_type": "json",
        "contentId": content_id, "imageYN": "Y",
        "numOfRows": "10", "pageNo": "1",
    })
    url = f"{TOUR_API_BASE}/detailImage2?serviceKey={ek}&{params}"
    try:
        r = await client.get(url, timeout=8.0)
        items = r.json()["response"]["body"]["items"]
        if not items:
            return []
        item_list = items.get("item", [])
        if isinstance(item_list, dict):
            item_list = [item_list]
        return [it.get("originimgurl") for it in item_list if it.get("originimgurl")]
    except Exception as e:
        logger.warning("detailImage2 실패 (contentid=%s): %s", content_id, e)
        return []


async def fetch_spot_detail(content_id: str, content_type_id: str = "12") -> dict:
    """detailCommon2 + detailIntro2 + detailImage2 병렬 호출 후 병합 반환."""
    if not TOUR_API_KEY or not content_id:
        return {}
    cache_key = f"detail_{content_id}"
    cached = _detail_cache.get(cache_key)
    if cached and time.time() - cached[0] < DETAIL_CACHE_TTL:
        return cached[1]

    async with httpx.AsyncClient() as client:
        common, intro, images = await asyncio.gather(
            _fetch_detail_common(client, content_id),
            _fetch_detail_intro(client, content_id, content_type_id),
            _fetch_detail_images(client, content_id),
            return_exceptions=True,
        )
    result = {}
    if isinstance(common, dict):
        result.update(common)
    if isinstance(intro, dict):
        result.update(intro)
    if isinstance(images, list):
        result["images"] = images
    _detail_cache[cache_key] = (time.time(), result)
    return result


# ── 숙박 조회 (searchStay2) ──────────────────────────────────────────
_stay_cache: dict = {}
STAY_CACHE_TTL = 3600


async def fetch_stays(area: str | None = None) -> list[dict]:
    """searchStay2 — 부산 지역 숙박 후보 조회 (1박 이상 코스용)."""
    if not TOUR_API_KEY:
        return []
    cache_key = f"stay_{area or 'all'}"
    cached = _stay_cache.get(cache_key)
    if cached and time.time() - cached[0] < STAY_CACHE_TTL:
        return cached[1]
    try:
        ek = _encoded_key()
        params = urlencode({
            "numOfRows": "30", "pageNo": "1",
            "MobileOS": "ETC", "MobileApp": "MurieopsBusan", "_type": "json",
            "areaCode": "6",
        })
        url = f"{TOUR_API_BASE}/searchStay2?serviceKey={ek}&{params}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            body = r.json()["response"]["body"]
            items = body.get("items") or {}
            item_list = items.get("item", []) if items else []
            if isinstance(item_list, dict):
                item_list = [item_list]
        stays = _convert_stays(item_list)
        if area:
            stays = [s for s in stays if s["area"] == area]
        _stay_cache[cache_key] = (time.time(), stays)
        return stays
    except Exception as e:
        logger.warning("searchStay2 조회 실패: %s", e)
        return []


def _convert_stays(items: list[dict]) -> list[dict]:
    result = []
    for item in items:
        addr = item.get("addr1", "")
        area = _infer_area(addr)
        result.append({
            "id": f"stay_{item.get('contentid', '')}",
            "name": item.get("title", ""),
            "area": area,
            "lat": float(item.get("mapy", 35.1796)),
            "lng": float(item.get("mapx", 129.0756)),
            "category": "숙박",
            "visit_time_min": 0,  # 숙박은 체류 시간 계산에서 제외
            "slope_pct": 1.0,
            "wait_time_min": 0,
            "wheelchair_accessible": None,
            "stroller_accessible": None,
            "elevator": False,
            "restroom_accessible": None,
            "accessibility_grade": 3,
            "description": addr,
            "image_url": item.get("firstimage") or None,
            "tags": ["숙박"],
            "_stay": True,
        })
    return result


# ── 지역·분류 코드 (areaCode2, categoryCode2) ────────────────────────
_area_code_cache: dict[str, list[dict]] = {}
_category_code_cache: dict[str, list[dict]] = {}
CODE_CACHE_TTL = 86400  # 24시간 — 변동이 거의 없음


async def fetch_area_codes(area_code: str = "6") -> list[dict]:
    """areaCode2 — 지정 areaCode 하위의 시군구 코드 목록 조회.
    기본 6 = 부산광역시. 반환: [{"code": "1", "name": "강서구"}, ...]
    """
    if not TOUR_API_KEY:
        return []
    cache_key = f"area_{area_code}"
    cached = _area_code_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        ek = _encoded_key()
        params = urlencode({
            "numOfRows": "50", "pageNo": "1",
            "MobileOS": "ETC", "MobileApp": "MurieopsBusan", "_type": "json",
            "areaCode": area_code,
        })
        url = f"{TOUR_API_BASE}/areaCode2?serviceKey={ek}&{params}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            body = r.json()["response"]["body"]
            items = body.get("items") or {}
            item_list = items.get("item", []) if items else []
            if isinstance(item_list, dict):
                item_list = [item_list]
        codes = [
            {"code": str(it.get("code", "")), "name": it.get("name", "")}
            for it in item_list
            if it.get("name")
        ]
        _area_code_cache[cache_key] = codes
        return codes
    except Exception as e:
        logger.warning("areaCode2 조회 실패 (areaCode=%s): %s", area_code, e)
        return []


async def fetch_category_codes(cat1: str = "", cat2: str = "") -> list[dict]:
    """categoryCode2 — 관광 유형 분류 코드. cat1/cat2 미지정 시 최상위(cat1) 조회."""
    if not TOUR_API_KEY:
        return []
    cache_key = f"cat_{cat1 or 'root'}_{cat2 or ''}"
    cached = _category_code_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        ek = _encoded_key()
        query = {
            "numOfRows": "100", "pageNo": "1",
            "MobileOS": "ETC", "MobileApp": "MurieopsBusan", "_type": "json",
        }
        if cat1:
            query["cat1"] = cat1
        if cat2:
            query["cat2"] = cat2
        params = urlencode(query)
        url = f"{TOUR_API_BASE}/categoryCode2?serviceKey={ek}&{params}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            body = r.json()["response"]["body"]
            items = body.get("items") or {}
            item_list = items.get("item", []) if items else []
            if isinstance(item_list, dict):
                item_list = [item_list]
        codes = [
            {"code": str(it.get("code", "")), "name": it.get("name", "")}
            for it in item_list
            if it.get("name")
        ]
        _category_code_cache[cache_key] = codes
        return codes
    except Exception as e:
        logger.warning("categoryCode2 조회 실패 (cat1=%s cat2=%s): %s", cat1, cat2, e)
        return []


def _infer_area(addr: str) -> str:
    for k, v in [
        # 구·군 단위 (구체적인 것 먼저)
        ("해운대", "해운대"), ("기장", "기장"), ("수영", "수영"),
        ("영도", "영도"), ("사하", "사하"), ("강서", "강서"),
        ("금정", "금정"), ("북구", "북구"), ("사상", "사상"),
        ("연제", "연제"), ("동래", "동래"), ("남구", "남구"),
        ("동구", "동구"), ("서구", "서구"), ("중구", "중구"),
        # 주요 지명
        ("남포", "중구"), ("광안", "수영"), ("센텀", "해운대"),
        ("벡스코", "해운대"), ("북항", "동구"), ("태종대", "영도"),
    ]:
        if k in addr:
            return v
    return "부산"
