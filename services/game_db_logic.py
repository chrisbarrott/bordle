"""Database game logic separated from connection code.

This module provides higher-level functions the app can call to get the
current game number and the country for the game of the day.
"""
from datetime import date
import json
import random
from zoneinfo import ZoneInfo
from typing import Optional, Dict

from .game_logger import setup_logger
from .postgres_connector import fetch_one, fetch_value
from .sql_queries import (
    GET_COUNT_DAILY_GAMES,
    GET_DAILY_GAME_BY_DATE,
    GET_MAX_DAILY_GAME_ROTATION,
    GET_USED_COUNTRIES_FOR_ROTATION,
    INSERT_DAILY_GAME_ROW,
    get_insert_player_game_state_row_query,
    get_select_player_game_state_query,
    get_update_player_game_state_guess_query,
)

logger = setup_logger()

UK_TZ = ZoneInfo("Europe/London")

with open("static/map_data/country_drop_down.json", "r", encoding="utf-8") as f:
    _all_countries = set(json.load(f))

with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    _border_map = json.load(f)

_borderable_countries = [country for country in _all_countries if country in _border_map]


def _normalize_player_state(row: Optional[Dict]) -> Optional[Dict[str, object]]:
    if not row:
        return None

    return {
        "game_number": _to_int(row.get("game_number")),
        "guess_history": json.loads(row.get("guess_history") or "[]"),
        "wrong_guesses": json.loads(row.get("wrong_guesses") or "[]"),
        "hard_mode": bool(row.get("hard_mode", False)),
        "guessed_main_country": bool(row.get("guessed_main_country", False)),
        "game_over": bool(row.get("game_over", False)),
        "game_result_recorded": bool(row.get("game_result_recorded", False)),
    }


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
        target_date = _today_uk_date()

    ensure_daily_game_for_date(target_date)
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


def _today_uk_date() -> date:
    from datetime import datetime

    return datetime.now(UK_TZ).date()


def _get_current_rotation() -> int:
    row = fetch_one(GET_MAX_DAILY_GAME_ROTATION)
    value = row.get("max_rotation") if row else None
    return int(value) if value is not None else 0


def _get_used_countries(rotation: int) -> set[str]:
    row = fetch_one(GET_USED_COUNTRIES_FOR_ROTATION, (rotation,))
    if not row:
        return set()

    used = row.get("used_countries") or []
    return {country for country in used if country}


def ensure_daily_game_for_date(target_date: Optional[date] = None) -> Optional[Dict[str, str]]:
    if target_date is None:
        target_date = _today_uk_date()

    target_date_param = target_date.isoformat()

    existing = fetch_one(GET_DAILY_GAME_BY_DATE, (target_date_param,))
    if existing:
        return {"country_code": None, "country_name": existing.get("country_name")}

    if not _borderable_countries:
        logger.error("[POSTGRES] No borderable countries available to assign daily game")
        return None

    # Retry a few times in case two processes race to create today's row.
    for _ in range(3):
        current_rotation = _get_current_rotation()
        used = _get_used_countries(current_rotation)

        remaining = [country for country in _borderable_countries if country not in used]
        if not remaining:
            current_rotation += 1
            remaining = list(_borderable_countries)

        chosen_country = random.choice(remaining)
        inserted = fetch_one(
            INSERT_DAILY_GAME_ROW,
            (target_date_param, chosen_country, current_rotation),
        )
        if inserted:
            country_name = inserted.get("country_name")
            logger.info(
                f"[POSTGRES] Assigned daily country: {country_name} for date={target_date_param}, rotation={current_rotation}"
            )
            return {"country_code": None, "country_name": country_name}

        existing_after_conflict = fetch_one(GET_DAILY_GAME_BY_DATE, (target_date_param,))
        if existing_after_conflict:
            return {
                "country_code": None,
                "country_name": existing_after_conflict.get("country_name"),
            }

    logger.error(f"[POSTGRES] Failed to ensure daily game row for date={target_date_param}")
    return None


def load_game_state(player_uid: Optional[str], target_date: Optional[date] = None) -> Optional[Dict[str, object]]:
    if not player_uid:
        return None

    if target_date is None:
        target_date = _today_uk_date()

    target_date_param = target_date.isoformat()
    try:
        row = fetch_one(get_select_player_game_state_query(), (player_uid, target_date_param))
    except Exception:
        logger.exception(
            f"[POSTGRES] load_game_state failed for player_uid={player_uid}, date={target_date_param}"
        )
        return None

    return _normalize_player_state(row)


def create_game_state_row(
    player_uid: Optional[str],
    hard_mode: bool = False,
    game_number: Optional[int] = None,
    target_date: Optional[date] = None,
) -> Optional[Dict[str, object]]:
    if not player_uid:
        return None

    if target_date is None:
        target_date = _today_uk_date()

    resolved_game_number = game_number if game_number is not None else get_current_game_number()
    target_date_param = target_date.isoformat()
    try:
        row = fetch_one(
            get_insert_player_game_state_row_query(),
            (
                player_uid,
                target_date_param,
                resolved_game_number,
                int(bool(hard_mode)),
                player_uid,
                target_date_param,
            ),
        )
    except Exception:
        logger.exception(
            f"[POSTGRES] create_game_state_row failed for player_uid={player_uid}, date={target_date_param}"
        )
        return None

    return _normalize_player_state(row)


def upsert_game_state(
    player_uid: Optional[str],
    guess_history,
    wrong_guesses,
    guessed_main_country: bool,
    hard_mode: bool,
    game_over: bool,
    game_result_recorded: bool,
    game_number: Optional[int] = None,
    target_date: Optional[date] = None,
) -> Optional[Dict[str, object]]:
    if not player_uid:
        return None

    if target_date is None:
        target_date = _today_uk_date()

    resolved_game_number = game_number if game_number is not None else get_current_game_number()
    target_date_param = target_date.isoformat()
    params = (
        resolved_game_number,
        json.dumps(guess_history or []),
        json.dumps(wrong_guesses or []),
        int(bool(hard_mode)),
        int(bool(guessed_main_country)),
        int(bool(game_over)),
        int(bool(game_result_recorded)),
        player_uid,
        target_date_param,
    )

    try:
        row = fetch_one(get_update_player_game_state_guess_query(), params)
    except Exception:
        logger.exception(
            f"[POSTGRES] upsert_game_state failed for player_uid={player_uid}, date={target_date_param}"
        )
        return None

    # If no row was updated, either the row doesn't exist yet or game_over is already true.
    if not row:
        existing = load_game_state(player_uid, target_date)
        if existing and existing.get("game_over"):
            logger.info(
                f"[POSTGRES] state update blocked for completed game: player_uid={player_uid}, date={target_date_param}"
            )
        return existing

    return _normalize_player_state(row)
