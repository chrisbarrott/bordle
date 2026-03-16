"""Database game logic separated from connection code.

This module provides higher-level functions the app can call to get the
current game number and the country for the game of the day.
"""
from datetime import date
from typing import Optional, Dict

from .game_logger import setup_logger
from .postgres_connector import fetch_one, fetch_value
from .sql_queries import (
    GET_COUNT_DAILY_GAMES,
    GET_DAILY_GAME_BY_DATE,
)

logger = setup_logger()


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def get_current_game_number() -> Optional[int]:
    """Return the latest game number from daily_game row count."""
    try:
        game_number = _to_int(fetch_value(GET_COUNT_DAILY_GAMES))
        if game_number is None:
            logger.warning("[POSTGRES] game_number query returned no value")
        return game_number
    except Exception:
        logger.exception("[POSTGRES] game_number query failed")
        return None


def get_country_of_the_day(target_date: Optional[date] = None) -> Optional[Dict[str, str]]:
    """Return a dict with country info for the daily game.

    The shape returned is {"country_code": ..., "country_name": ...}.
    """
    if target_date is None:
        target_date = date.today()
    target_date_param = target_date.isoformat()
    try:
        row = fetch_one(GET_DAILY_GAME_BY_DATE, (target_date_param,))
    except Exception:
        logger.exception(f"[POSTGRES] country query failed for date={target_date_param}")
        return None

    if not row:
        logger.warning(f"[POSTGRES] no country found for date={target_date_param}")
        return None

    return {
        "country_code": None,
        "country_name": row.get("country_name"),
    }
