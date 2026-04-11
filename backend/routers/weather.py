"""GET /api/weather — 부산 현재 날씨 (기상청 단기예보)"""
from __future__ import annotations
import os, datetime, logging, httpx
from urllib.parse import quote
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()
WEATHER_KEY = os.getenv("WEATHER_KEY", "")

async def _call_weather_api(base_date: str, base_time: str) -> dict:
    """기상청 단기예보 API 호출. 실패 시 None 반환."""
    ek = WEATHER_KEY if "%" in WEATHER_KEY else quote(WEATHER_KEY, safe="")
    url = (
        "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
        f"?serviceKey={ek}"
        "&pageNo=1&numOfRows=60&dataType=JSON"
        f"&base_date={base_date}&base_time={base_time}"
        "&nx=98&ny=76"
    )
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get(url)
        return r.json()["response"]["body"]["items"]["item"]


async def fetch_weather_status(date_str: str | None = None) -> dict:
    """추천 알고리즘용 날씨 상태 반환.
    date_str: YYYYMMDD 형식. None이면 오늘.
    반환: {"available": bool, "is_rainy": bool, "sky": str, "tmp": str, "icon": str}
    날씨 조회 실패 시 맑음(is_rainy=False) 기본값.
    """
    if not WEATHER_KEY:
        return {"available": False, "is_rainy": False}
    try:
        # 기상청 API는 base_date가 오늘~최대 +3일까지만 지원.
        # 미래 여행일 요청 시 "오늘 현재 날씨"로 폴백 (데모 목적)
        now = datetime.datetime.now()
        if date_str:
            try:
                requested = datetime.datetime.strptime(date_str, "%Y%m%d")
                delta_days = (requested.date() - now.date()).days
                target = requested if 0 <= delta_days <= 2 else now
            except Exception:
                target = now
        else:
            target = now
        base_date = target.strftime("%Y%m%d")
        base_time = _nearest_base_time(target)
        items = await _call_weather_api(base_date, base_time)
        sky = next((x["fcstValue"] for x in items if x["category"] == "SKY"), "1")
        tmp = next((x["fcstValue"] for x in items if x["category"] == "TMP"), "20")
        pty = next((x["fcstValue"] for x in items if x["category"] == "PTY"), "0")
        is_rainy = pty != "0"
        return {
            "available": True,
            "is_rainy": is_rainy,
            "sky": {"1": "맑음", "3": "구름많음", "4": "흐림"}.get(sky, "맑음"),
            "tmp": tmp + "°C",
            "rain": is_rainy,
            "icon": "🌧️" if is_rainy else ("☀️" if sky == "1" else "⛅"),
        }
    except Exception as e:
        logger.warning("날씨 API 호출 실패: %s", e)
        return {"available": False, "is_rainy": False}


@router.get("/api/weather")
async def get_weather():
    result = await fetch_weather_status()
    if not result["available"]:
        return {"available": False}
    return result


def _nearest_base_time(now: datetime.datetime) -> str:
    hours = [2, 5, 8, 11, 14, 17, 20, 23]
    h = max((x for x in hours if x <= now.hour), default=23)
    return f"{h:02d}00"
