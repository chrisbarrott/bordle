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
    GET_MAX_ROTATION,
    GET_COUNT_DAILY_GAMES,
    GET_DAILY_GAME_BY_DATE,
    GET_DAILY_GAME_BY_DATE_WITH_NAME_ONLY,
    GET_DAILY_GAME_BY_DATE_WITH_COUNTRY_ONLY,
    GET_GAME_BY_NUMBER,
    GET_GAME_BY_NUMBER_WITH_NAME_ONLY,
    GET_GAME_BY_NUMBER_WITH_COUNTRY_ONLY,
    GET_DAILY_GAME_BY_ROTATION,
)


def _normalize_country_row(row: Dict[str, str]) -> Dict[str, str]:
    return {
        "country_code": row.get("country_code"),
        "country_name": row.get("country_name") or row.get("country"),
    }


# Cache the query variant that worked last time so probes don't repeat.
_country_date_query_cache: Optional[str] = None
_country_rotation_query_cache: Optional[str] = None


def _fetch_first_valid(
    queries: list,
    params,
    cache_var: str,
) -> Optional[Dict[str, str]]:
    """Try queries in order, cache the first that returns a row, skip probes next time."""
    global _country_date_query_cache, _country_rotation_query_cache
    cache = {"date": _country_date_query_cache, "rotation": _country_rotation_query_cache}
    cached_query = cache.get(cache_var)

    if cached_query:
        try:
            row = fetch_one(cached_query, params)
            if row:
                return _normalize_country_row(row)
        except Exception:
            pass
        # Cached query stopped working, reset and re-probe.
        if cache_var == "date":
            _country_date_query_cache = None
        else:
            _country_rotation_query_cache = None

    for query in queries:
        try:
            row = fetch_one(query, params, log_errors=False)
            if row:
                if cache_var == "date":
                    _country_date_query_cache = query
                else:
                    _country_rotation_query_cache = query
                return _normalize_country_row(row)
        except Exception:
            continue
    return None


_game_number_query_cache = None
# COUNT(DISTINCT game_date) is the canonical game number — one row per day played.
# The games table queries are legacy fallbacks for older schemas.
_GAME_NUMBER_QUERIES = [GET_COUNT_DAILY_GAMES, GET_MAX_GAME_NUMBER, GET_MAX_ID, GET_MAX_ROTATION]


def _safe_fetch_value(query: str, *, suppress_errors: bool = False):
    try:
        return fetch_value(query, log_errors=not suppress_errors)
    except Exception:
        return None


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def get_current_game_number() -> Optional[int]:
    """Attempt to determine the current/latest game number.

    Tries common patterns and returns an integer or None if not found.
    Caches the working query to avoid repeated schema-probe failures.
    """
    global _game_number_query_cache

    if _game_number_query_cache:
        cached_value = _to_int(_safe_fetch_value(_game_number_query_cache))
        if cached_value is not None:
            return cached_value
        _game_number_query_cache = None

    for query in _GAME_NUMBER_QUERIES:
        probed_value = _to_int(_safe_fetch_value(query, suppress_errors=True))
        if probed_value is not None:
            _game_number_query_cache = query
            return probed_value

    return None


def get_country_of_the_day(target_date: Optional[date] = None) -> Optional[Dict[str, str]]:
    """Return a dict with country info for the daily game.

    The shape returned is {"country_code": ..., "country_name": ...} when available.
    Tries a few fallback query shapes so it works with several schemas.
    """
    if target_date is None:
        target_date = date.today()
    target_date_param = target_date.isoformat()

    # Try multiple daily_game schema variants.
    row = _fetch_first_valid(
        [
            GET_DAILY_GAME_BY_DATE,
            GET_DAILY_GAME_BY_DATE_WITH_NAME_ONLY,
            GET_DAILY_GAME_BY_DATE_WITH_COUNTRY_ONLY,
        ],
        (target_date_param,),
        cache_var="date",
    )
    if row:
        return row

    # Fallback: use latest games table entry
    latest_game = get_current_game_number()
    if latest_game is not None:
        row = _fetch_first_valid(
            [
                GET_GAME_BY_NUMBER,
                GET_GAME_BY_NUMBER_WITH_NAME_ONLY,
                GET_GAME_BY_NUMBER_WITH_COUNTRY_ONLY,
                GET_DAILY_GAME_BY_ROTATION,
            ],
            (latest_game,),
            cache_var="rotation",
        )
        if row:
            return row

    return None
