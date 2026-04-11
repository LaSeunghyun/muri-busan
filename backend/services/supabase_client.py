"""Supabase 클라이언트 싱글톤. 환경변수 없으면 None 반환 (graceful degradation)."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_client: Any = None
_init_attempted = False


def get_client():
    """Supabase 클라이언트 지연 초기화. 실패 시 None."""
    global _client, _init_attempted
    if _init_attempted:
        return _client
    _init_attempted = True

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not url or not key:
        logger.info("Supabase 비활성: SUPABASE_URL / SUPABASE_ANON_KEY 미설정")
        return None

    try:
        from supabase import create_client  # type: ignore
        _client = create_client(url, key)
        logger.info("Supabase 클라이언트 초기화 완료")
        return _client
    except Exception as e:
        logger.warning("Supabase 클라이언트 초기화 실패: %s", e)
        return None


def is_enabled() -> bool:
    return get_client() is not None
