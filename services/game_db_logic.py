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
from .game_get_data import get_user_ip, get_user_location
from .postgres_connector import fetch_all, fetch_one, fetch_value
from .sql_queries import (
    GET_COUNT_DAILY_GAMES,
    GET_DAILY_GAME_BY_DATE,
    GET_MAX_DAILY_GAME_ROTATION,
    GET_USED_COUNTRIES_FOR_ROTATION,
    INSERT_DAILY_GAME_ROW,
    get_player_game_state_table_name,
    get_insert_player_game_state_row_query,
    get_select_player_game_state_query,
    get_update_player_game_state_guess_query,
    get_upsert_game_stats_query,
    get_upsert_country_stats_query,
    get_select_game_stats_for_date_query,
    get_select_total_games_query,
    get_select_daily_leaderboard_query,
    get_select_all_time_leaderboard_query,
    get_select_player_stats_query,
    get_upsert_player_stats_after_game_query,
    get_update_player_stats_migration_query,
    get_insert_player_stats_migration_query,
)

logger = setup_logger()

UK_TZ = ZoneInfo("Europe/London")

with open("static/map_data/country_drop_down.json", "r", encoding="utf-8") as f:
    _all_countries = set(json.load(f))

with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    _border_map = json.load(f)

_borderable_countries = [country for country in _all_countries if country in _border_map]
_player_state_schema_ready = False


def _ensure_player_game_state_schema() -> None:
    global _player_state_schema_ready

    if _player_state_schema_ready:
        return

    table_name = get_player_game_state_table_name()
    try:
        fetch_one(
            f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS game_result TEXT DEFAULT 'In progress'",
            log_errors=False,
        )
        _player_state_schema_ready = True
    except Exception:
        logger.exception(f"[POSTGRES] failed ensuring game_result column on {table_name}")


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
        "game_result": row.get("game_result") or "In progress",
    }


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _normalize_player_stats_row(row: Optional[Dict]) -> Optional[Dict[str, object]]:
    if not row:
        return None

    return {
        "games_played": _to_int(row.get("games_played")) or 0,
        "games_won": _to_int(row.get("games_won")) or 0,
        "current_streak": _to_int(row.get("current_streak")) or 0,
        "best_streak": _to_int(row.get("best_streak")) or 0,
        "migrated": bool(row.get("migrated", False)),
        "player_country": row.get("player_country") or "Unknown",
        "player_city": row.get("player_city") or "Unknown",
        "last_updated": row.get("last_updated"),
    }


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


def record_postgres_game_stats(success: bool, game_date: Optional[date] = None) -> None:
    """Upsert win/loss totals into the Postgres <env>_game_stats table."""
    if game_date is None:
        game_date = _today_uk_date()
    try:
        fetch_one(
            get_upsert_game_stats_query(),
            (game_date.isoformat(), 1 if success else 0, 0 if success else 1),
        )
        logger.info(f"[POSTGRES] game_stats upserted: date={game_date}, success={success}")
    except Exception:
        logger.exception(f"[POSTGRES] record_postgres_game_stats failed: date={game_date}")


def record_postgres_country_stats(
    success: bool,
    country: str,
    region: str,
    city: str,
    game_date: Optional[date] = None,
) -> None:
    """Upsert play/win/loss counts into the Postgres <env>_country_stats table."""
    if not country or country == "Unknown":
        return
    if game_date is None:
        game_date = _today_uk_date()
    try:
        fetch_one(
            get_upsert_country_stats_query(),
            (
                game_date.isoformat(),
                country,
                region or "",
                city or "",
                1 if success else 0,
                0 if success else 1,
            ),
        )
        logger.info(
            f"[POSTGRES] country_stats upserted: date={game_date}, country={country}, success={success}"
        )
    except Exception:
        logger.exception(
            f"[POSTGRES] record_postgres_country_stats failed: date={game_date}, country={country}"
        )


def record_postgres_player_stats(
    success: bool,
    player_uid: Optional[str],
    country: str = "Unknown",
    city: str = "Unknown",
) -> Optional[Dict[str, object]]:
    """Upsert per-player aggregate stats after a finished game."""
    if not player_uid:
        return None

    try:
        row = fetch_one(
            get_upsert_player_stats_after_game_query(),
            (
                player_uid,
                1 if success else 0,
                1 if success else 0,
                1 if success else 0,
                country or "Unknown",
                city or "Unknown",
            ),
        )
        return _normalize_player_stats_row(row)
    except Exception:
        logger.exception(f"[POSTGRES] record_postgres_player_stats failed: player_uid={player_uid}")
        return None


def get_games_today_stats(target_date: Optional[date] = None) -> tuple[int, int]:
    if target_date is None:
        target_date = _today_uk_date()

    row = fetch_one(get_select_game_stats_for_date_query(), (target_date.isoformat(),), log_errors=False)
    if not row:
        return 0, 0

    successes = _to_int(row.get("successes")) or 0
    failures = _to_int(row.get("failures")) or 0
    games_today = successes + failures
    success_rate_today = round((successes / games_today) * 100) if games_today > 0 else 0
    return games_today, success_rate_today


def get_total_games_count() -> int:
    row = fetch_one(get_select_total_games_query(), log_errors=False)
    if not row:
        return 0
    return _to_int(row.get("total_games")) or 0


def get_leaderboard_data() -> Dict[str, list[Dict[str, object]]]:
    today = _today_uk_date().isoformat()
    daily_rows = fetch_all(get_select_daily_leaderboard_query(), (today,), log_errors=False)
    all_time_rows = fetch_all(get_select_all_time_leaderboard_query(), log_errors=False)

    def _format_rows(rows):
        return [
            {
                "country": r.get("country"),
                "success_rate": round(float(r.get("success_rate") or 0), 1),
                "total_guesses": _to_int(r.get("total_plays")) or 0,
            }
            for r in rows
        ]

    return {
        "daily": _format_rows(daily_rows),
        "all_time": _format_rows(all_time_rows),
    }


def get_player_stats(player_uid: Optional[str]) -> Optional[Dict[str, object]]:
    if not player_uid:
        return None
    row = fetch_one(get_select_player_stats_query(), (player_uid,), log_errors=False)
    return _normalize_player_stats_row(row)


def migrate_player_stats(player_uid: Optional[str], stats: dict) -> Dict[str, str]:
    if not player_uid:
        return {"status": "error", "message": "player_uid required"}

    existing = get_player_stats(player_uid)
    if existing and existing.get("migrated"):
        return {"status": "skipped", "reason": "already_migrated"}

    user_ip = get_user_ip()
    player_country, _region, player_city = get_user_location(user_ip) if user_ip else ("Unknown", "Unknown", "Unknown")

    games_played = int(stats.get("gamesPlayed", 0))
    games_won = int(stats.get("gamesWon", 0))
    current_streak = int(stats.get("currentStreak", 0))
    best_streak = int(stats.get("bestStreak", current_streak))

    if existing:
        merged_played = max(existing.get("games_played", 0), games_played)
        merged_won = max(existing.get("games_won", 0), games_won)
        merged_current_streak = max(existing.get("current_streak", 0), current_streak)
        merged_best_streak = max(existing.get("best_streak", 0), best_streak)

        fetch_one(
            get_update_player_stats_migration_query(),
            (
                merged_played,
                merged_won,
                merged_current_streak,
                merged_best_streak,
                player_country,
                player_city,
                player_uid,
            ),
        )
        return {"status": "ok", "action": "update"}

    fetch_one(
        get_insert_player_stats_migration_query(),
        (
            player_uid,
            games_played,
            games_won,
            current_streak,
            best_streak,
            player_country,
            player_city,
        ),
    )
    return {"status": "ok", "action": "insert"}


def load_game_state(player_uid: Optional[str], target_date: Optional[date] = None) -> Optional[Dict[str, object]]:
    if not player_uid:
        return None

    if target_date is None:
        target_date = _today_uk_date()

    _ensure_player_game_state_schema()

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

    _ensure_player_game_state_schema()

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
    game_result: str = "In progress",
    game_number: Optional[int] = None,
    target_date: Optional[date] = None,
) -> Optional[Dict[str, object]]:
    if not player_uid:
        return None

    if target_date is None:
        target_date = _today_uk_date()

    _ensure_player_game_state_schema()

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
        game_result,
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
