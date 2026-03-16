"""Database game logic separated from connection code.

This module provides higher-level functions the app can call to get the
current game number and the country for the game of the day.
"""
from datetime import date
from typing import Optional, Dict

from .postgres_connector import fetch_one, fetch_value
from .sql_queries import (
    GET_MAX_GAME_NUMBER,
    GET_MAX_ID,
    GET_DAILY_GAME_BY_DATE,
    GET_GAME_BY_NUMBER,
)


def get_current_game_number() -> Optional[int]:
    """Attempt to determine the current/latest game number.

    Tries common patterns and returns an integer or None if not found.
    """
    val = fetch_value(GET_MAX_GAME_NUMBER)
    if val is not None:
        try:
            return int(val)
        except Exception:
            pass

    # Fallback: max id
    val = fetch_value(GET_MAX_ID)
    if val is not None:
        try:
            return int(val)
        except Exception:
            pass

    return None


def get_country_of_the_day(target_date: Optional[date] = None) -> Optional[Dict[str, str]]:
    """Return a dict with country info for the daily game.

    The shape returned is {"country_code": ..., "country_name": ...} when available.
    Tries a few fallback query shapes so it works with several schemas.
    """
    if target_date is None:
        target_date = date.today()

    # Try a daily_games table with a date column
    row = fetch_one(GET_DAILY_GAME_BY_DATE, (target_date,))
    if row:
        return {"country_code": row.get("country_code"), "country_name": row.get("country_name")}

    # Fallback: use latest games table entry
    latest_game = get_current_game_number()
    if latest_game is not None:
        row = fetch_one(GET_GAME_BY_NUMBER, (latest_game,))
        if row:
            return {"country_code": row.get("country_code"), "country_name": row.get("country_name")}

    return None
