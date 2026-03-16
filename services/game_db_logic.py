"""Database game logic separated from connection code.

This module provides higher-level functions the app can call to get the
current game number and the country for the game of the day.
"""
from datetime import date
import json
from typing import Optional, Dict

from .game_logger import setup_logger
from .postgres_connector import fetch_one, fetch_value
from .sql_queries import (
    GET_COUNT_DAILY_GAMES,
    GET_DAILY_GAME_BY_DATE,
    get_insert_player_game_state_row_query,
    get_select_player_game_state_query,
    get_update_player_game_state_guess_query,
)

logger = setup_logger()


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


def load_game_state(player_uid: Optional[str], target_date: Optional[date] = None) -> Optional[Dict[str, object]]:
    if not player_uid:
        return None

    if target_date is None:
        target_date = date.today()

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
        target_date = date.today()

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
        target_date = date.today()

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
