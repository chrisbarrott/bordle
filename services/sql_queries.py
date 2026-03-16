"""Centralized SQL statements used by the Postgres migration services.

Keep all queries here so it's obvious which SQL is executed against the
new Postgres database.
"""

import os
import re

GET_COUNT_DAILY_GAMES = (
    "SELECT COUNT(DISTINCT game_date) AS game_number FROM daily_game"
)

GET_DAILY_GAME_BY_DATE = (
    "SELECT country AS country_name FROM daily_game WHERE game_date = %s LIMIT 1"
)

_SAFE_IDENTIFIER = re.compile(r"[^a-z0-9_]")


def _normalize_identifier_part(value: str) -> str:
    normalized = (value or "").strip().lower().replace("-", "_")
    normalized = _SAFE_IDENTIFIER.sub("", normalized)
    return normalized.strip("_")


def _get_env_table_prefix() -> str:
    explicit_prefix = _normalize_identifier_part(os.getenv("POSTGRES_TABLE_PREFIX", ""))
    if explicit_prefix:
        return explicit_prefix

    flask_env = _normalize_identifier_part(os.getenv("FLASK_ENV", ""))
    if flask_env == "local":
        flask_env = "development"

    if flask_env and flask_env not in ("prod", "production"):
        return flask_env

    return ""


def get_env_country_stats_table_name() -> str:
    prefix = _get_env_table_prefix()
    return f"{prefix}_country_stats" if prefix else "country_stats"


def get_env_game_stats_table_name() -> str:
    prefix = _get_env_table_prefix()
    return f"{prefix}_game_stats" if prefix else "game_stats"


def get_player_game_state_table_name() -> str:
    prefix = _get_env_table_prefix()
    return f"{prefix}_player_game_state" if prefix else "player_game_state"


def get_env_player_stats_table_name() -> str:
    prefix = _get_env_table_prefix()
    return f"{prefix}_player_stats" if prefix else "player_stats"


def get_player_game_state_table_candidates() -> list[str]:
    return [get_player_game_state_table_name()]


def get_select_player_game_state_query() -> str:
    table_name = get_player_game_state_table_name()
    return f"""
SELECT
    game_number,
    guess_history,
    wrong_guesses,
    hard_mode,
    guessed_main_country,
    game_over,
    game_result_recorded
FROM {table_name}
WHERE player_uid = %s AND game_date = %s::date
LIMIT 1
"""


def get_insert_player_game_state_row_query() -> str:
    table_name = get_player_game_state_table_name()
    return f"""
WITH inserted AS (
    INSERT INTO {table_name} (
        player_uid,
        game_date,
        game_number,
        guess_history,
        wrong_guesses,
        hard_mode,
        guessed_main_country,
        game_over,
        game_result_recorded
    ) VALUES (%s, %s, %s, '[]', '[]', %s, 0, 0, 0)
    ON CONFLICT (player_uid, game_date)
    DO NOTHING
    RETURNING
        game_number,
        guess_history,
        wrong_guesses,
        hard_mode,
        guessed_main_country,
        game_over,
        game_result_recorded
)
SELECT
    game_number,
    guess_history,
    wrong_guesses,
    hard_mode,
    guessed_main_country,
    game_over,
    game_result_recorded
FROM inserted
UNION ALL
SELECT
    game_number,
    guess_history,
    wrong_guesses,
    hard_mode,
    guessed_main_country,
    game_over,
    game_result_recorded
FROM {table_name}
WHERE player_uid = %s
    AND game_date = %s::date
    AND NOT EXISTS (SELECT 1 FROM inserted)
LIMIT 1
"""


def get_update_player_game_state_guess_query() -> str:
    table_name = get_player_game_state_table_name()
    return f"""
UPDATE {table_name}
SET
    game_number = COALESCE(game_number, %s),
    guess_history = %s,
    wrong_guesses = %s,
    hard_mode = %s,
    guessed_main_country = %s,
    game_over = %s,
    game_result_recorded = %s,
    recorded_at = CURRENT_TIMESTAMP
WHERE player_uid = %s
    AND game_date = %s::date
    AND COALESCE(game_over, 0) = 0
RETURNING
    game_number,
    guess_history,
    wrong_guesses,
    hard_mode,
    guessed_main_country,
    game_over,
    game_result_recorded
"""
