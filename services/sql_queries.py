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

GET_MAX_DAILY_GAME_ROTATION = (
    "SELECT MAX(rotation) AS max_rotation FROM daily_game"
)

GET_USED_COUNTRIES_FOR_ROTATION = (
    "SELECT COALESCE(json_agg(country), '[]'::json) AS used_countries FROM daily_game WHERE rotation = %s"
)

INSERT_DAILY_GAME_ROW = """
INSERT INTO daily_game (game_date, country, rotation)
VALUES (%s, %s, %s)
ON CONFLICT (game_date)
DO NOTHING
RETURNING country AS country_name
"""

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


# ---------------------------------------------------------------------------
# game_stats and country_stats – upsert queries
# ---------------------------------------------------------------------------

def get_upsert_game_stats_query() -> str:
    table_name = get_env_game_stats_table_name()
    return f"""
INSERT INTO {table_name} (game_date, successes, failures)
VALUES (%s, %s, %s)
ON CONFLICT (game_date) DO UPDATE SET
    successes = {table_name}.successes + EXCLUDED.successes,
    failures  = {table_name}.failures  + EXCLUDED.failures
"""


def get_upsert_country_stats_query() -> str:
    table_name = get_env_country_stats_table_name()
    return f"""
INSERT INTO {table_name} (game_date, country, region, city, plays, successes, failures)
VALUES (%s, %s, %s, %s, 1, %s, %s)
ON CONFLICT (game_date, country, region, city) DO UPDATE SET
    plays     = {table_name}.plays + 1,
    successes = {table_name}.successes + EXCLUDED.successes,
    failures  = {table_name}.failures  + EXCLUDED.failures
"""


def get_sync_country_stats_id_sequence_query() -> str:
    table_name = get_env_country_stats_table_name()
    return f"""
SELECT setval(
    pg_get_serial_sequence('{table_name}', 'id'),
    COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1,
    false
)
"""


def get_select_game_stats_for_date_query() -> str:
    table_name = get_env_game_stats_table_name()
    return f"""
SELECT
    COALESCE(successes, 0) AS successes,
    COALESCE(failures, 0) AS failures
FROM {table_name}
WHERE game_date::date = %s::date
LIMIT 1
"""


def get_select_total_games_query() -> str:
    table_name = get_env_game_stats_table_name()
    return f"""
SELECT COALESCE(SUM(successes + failures), 0) AS total_games
FROM {table_name}
"""


def get_select_daily_leaderboard_query() -> str:
    table_name = get_env_country_stats_table_name()
    return f"""
SELECT
    country,
    SUM(successes) AS total_successes,
    SUM(failures) AS total_failures,
    SUM(plays) AS total_plays,
    CASE
        WHEN (SUM(successes) + SUM(failures)) = 0 THEN 0
        ELSE (SUM(successes)::float * 100.0 / (SUM(successes) + SUM(failures)))
    END AS success_rate
FROM {table_name}
WHERE game_date::date = %s::date
GROUP BY country
HAVING SUM(plays) > 0
ORDER BY success_rate DESC, total_plays DESC
LIMIT 20
"""


def get_select_all_time_leaderboard_query() -> str:
    table_name = get_env_country_stats_table_name()
    return f"""
SELECT
    country,
    SUM(successes) AS total_successes,
    SUM(failures) AS total_failures,
    SUM(plays) AS total_plays,
    CASE
        WHEN (SUM(successes) + SUM(failures)) = 0 THEN 0
        ELSE (SUM(successes)::float * 100.0 / (SUM(successes) + SUM(failures)))
    END AS success_rate
FROM {table_name}
GROUP BY country
HAVING SUM(plays) > 0
ORDER BY success_rate DESC, total_plays DESC
LIMIT 100
"""


def get_select_player_stats_query() -> str:
    table_name = get_env_player_stats_table_name()
    return f"""
SELECT
    games_played,
    games_won,
    current_streak,
    best_streak,
    migrated,
    player_country,
    player_city,
    last_updated
FROM {table_name}
WHERE player_uid = %s
LIMIT 1
"""


def get_upsert_player_stats_after_game_query() -> str:
    table_name = get_env_player_stats_table_name()
    return f"""
INSERT INTO {table_name} (
    player_uid,
    games_played,
    games_won,
    current_streak,
    best_streak,
    migrated,
    last_updated,
    player_country,
    player_city
)
VALUES (%s, 1, %s, %s, %s, 0, CURRENT_DATE, %s, %s)
ON CONFLICT (player_uid) DO UPDATE SET
    games_played = {table_name}.games_played + 1,
    games_won = {table_name}.games_won + EXCLUDED.games_won,
    current_streak = CASE
        WHEN EXCLUDED.games_won > 0 THEN {table_name}.current_streak + 1
        ELSE 0
    END,
    best_streak = CASE
        WHEN EXCLUDED.games_won > 0 THEN GREATEST({table_name}.best_streak, {table_name}.current_streak + 1)
        ELSE {table_name}.best_streak
    END,
    last_updated = CURRENT_DATE,
    player_country = EXCLUDED.player_country,
    player_city = EXCLUDED.player_city
RETURNING
    games_played,
    games_won,
    current_streak,
    best_streak,
    migrated,
    player_country,
    player_city,
    last_updated
"""


def get_update_player_stats_migration_query() -> str:
    table_name = get_env_player_stats_table_name()
    return f"""
UPDATE {table_name}
SET
    games_played = %s,
    games_won = %s,
    current_streak = %s,
    best_streak = %s,
    migrated = 1,
    last_updated = CURRENT_DATE,
    player_country = %s,
    player_city = %s
WHERE player_uid = %s
RETURNING
    games_played,
    games_won,
    current_streak,
    best_streak,
    migrated,
    player_country,
    player_city,
    last_updated
"""


def get_insert_player_stats_migration_query() -> str:
    table_name = get_env_player_stats_table_name()
    return f"""
INSERT INTO {table_name} (
    player_uid,
    games_played,
    games_won,
    current_streak,
    best_streak,
    migrated,
    last_updated,
    player_country,
    player_city
)
VALUES (%s, %s, %s, %s, %s, 1, CURRENT_DATE, %s, %s)
RETURNING
    games_played,
    games_won,
    current_streak,
    best_streak,
    migrated,
    player_country,
    player_city,
    last_updated
"""


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
    game_result_recorded,
    player_stats_recorded,
    leaderboard_recorded,
    game_result
FROM {table_name}
WHERE player_uid = %s AND game_date::date = %s::date
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
        game_result_recorded,
        player_stats_recorded,
        leaderboard_recorded,
        game_result
    ) VALUES (%s, %s, %s, '[]', '[]', %s, 0, 0, 0, FALSE, 0, 'In progress')
    ON CONFLICT (player_uid, game_date)
    DO NOTHING
    RETURNING
        game_number,
        guess_history,
        wrong_guesses,
        hard_mode,
        guessed_main_country,
        game_over,
        game_result_recorded,
        player_stats_recorded,
        leaderboard_recorded,
        game_result
)
SELECT
    game_number,
    guess_history,
    wrong_guesses,
    hard_mode,
    guessed_main_country,
    game_over,
    game_result_recorded,
    player_stats_recorded,
    leaderboard_recorded,
    game_result
FROM inserted
UNION ALL
SELECT
    game_number,
    guess_history,
    wrong_guesses,
    hard_mode,
    guessed_main_country,
    game_over,
    game_result_recorded,
    player_stats_recorded,
    leaderboard_recorded,
    game_result
FROM {table_name}
WHERE player_uid = %s
    AND game_date::date = %s::date
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
    player_stats_recorded = %s,
    leaderboard_recorded = %s,
    game_result = %s,
    recorded_at = CURRENT_TIMESTAMP
WHERE player_uid = %s
    AND game_date::date = %s::date
RETURNING
    game_number,
    guess_history,
    wrong_guesses,
    hard_mode,
    guessed_main_country,
    game_over,
    game_result_recorded,
    player_stats_recorded,
    leaderboard_recorded,
    game_result
"""
