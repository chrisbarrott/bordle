import json
import os
from typing import Any

import redis

from services.game_logger import setup_logger

logger = setup_logger()


_CLIENT: redis.Redis | None = None


def _get_client() -> redis.Redis | None:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        _CLIENT = redis.from_url(url, decode_responses=True)
        # quick ping to validate
        _CLIENT.ping()
        logger.info("[REDIS] connected")
        return _CLIENT
    except Exception as e:
        logger.warning(f"[REDIS] connection failed: {e}")
        _CLIENT = None
        return None


def redis_available() -> bool:
    return _get_client() is not None


def redis_get(key: str) -> Any | None:
    c = _get_client()
    if not c:
        return None
    try:
        val = c.get(key)
        if val is None:
            return None
        return json.loads(val)
    except Exception as e:
        logger.warning(f"[REDIS] get failed for {key}: {e}")
        return None


def redis_set(key: str, value: Any, ex: int | None = 3600) -> None:
    c = _get_client()
    if not c:
        return
    try:
        c.set(key, json.dumps(value), ex=ex)
    except Exception as e:
        logger.warning(f"[REDIS] set failed for {key}: {e}")


def redis_delete(key: str) -> None:
    c = _get_client()
    if not c:
        return
    try:
        c.delete(key)
    except Exception as e:
        logger.warning(f"[REDIS] delete failed for {key}: {e}")
