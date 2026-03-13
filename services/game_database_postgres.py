"""PostgreSQL backend for Bordle.

Drop-in replacement for game_database_connections.py.
Exports the same public API so app.py / game_logic.py imports can be
switched by changing a single import line, e.g.:

    # was:
    from services.game_database_connections import ...
    # becomes:
    from services.game_database_postgres import ...

Connection resolution is environment-aware via FLASK_ENV and network context:
    - development/dev prefers external connections (DATABASE_URL_EXTERNAL)
    - uat/staging and production/prod prefer Render internal DATABASE_URL

Env-specific DSNs are still supported:
    POSTGRES_DSN_DEV/UAT/PROD, DATABASE_URL_DEV/UAT/PROD

By default, tables are *not* prefixed (recommended when using separate
databases). Set USE_ENV_TABLE_PREFIX=1 only if you intentionally share one
database across environments.
"""

from __future__ import annotations

import json
import os
import random
import time
from datetime import date, datetime, timedelta
from threading import Lock
from typing import Any

import pytz
import psycopg2
import psycopg2.extras
import psycopg2.extensions
import psycopg2.pool

from flask import session

from services.game_get_data import (
    get_all_drop_down_options,
    get_user_ip,
    get_user_location,
)
from services.game_logger import setup_logger

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

logger = setup_logger()

ENVIRONMENT = os.getenv("FLASK_ENV", "development")
USE_ENV_TABLE_PREFIX = os.getenv("USE_ENV_TABLE_PREFIX", "0") == "1"
_AUTO_DETECTED_ENV_PREFIX: bool | None = None
_AUTO_DETECT_ATTEMPTED = False
_SCHEMA_READY = False
_SCHEMA_LOCK = Lock()
_POOL: psycopg2.pool.ThreadedConnectionPool | None = None
_POOL_LOCK = Lock()
_LANDING_STATS_CACHE: tuple | None = None
_LANDING_STATS_CACHE_TTL = 30  # seconds
_LANDING_STATS_CACHE_TS: float = 0.0
_LANDING_STATS_LOCK = Lock()

with open("static/map_data/border_map.json", "r", encoding="utf-8") as _f:
    border_map = json.load(_f)


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _truncate_for_log(value: str, max_len: int = 700) -> str:
    if len(value) <= max_len:
        return value
    return value[:max_len] + "...<truncated>"


def _format_query_for_log(query: Any) -> str:
    if query is None:
        return ""
    if isinstance(query, bytes):
        query = query.decode("utf-8", errors="replace")
    return _truncate_for_log(str(query).strip().replace("\n", " "))


def _format_params_for_log(params: Any) -> str:
    if params is None:
        return "none"
    return _truncate_for_log(repr(params), 500)


class PostgresLoggingCursor(psycopg2.extensions.cursor):
    def execute(self, query, vars=None):
        logger.info(
            f'[POSTGRES_DB] execute sql="{_format_query_for_log(query)}" params={_format_params_for_log(vars)}'
        )
        return super().execute(query, vars)

    def executemany(self, query, vars_list):
        count = len(vars_list) if vars_list is not None else 0
        logger.info(
            f'[POSTGRES_DB] executemany sql="{_format_query_for_log(query)}" batch_size={count}'
        )
        return super().executemany(query, vars_list)


class PostgresLoggingRealDictCursor(psycopg2.extras.RealDictCursor):
    def execute(self, query, vars=None):
        logger.info(
            f'[POSTGRES_DB] execute sql="{_format_query_for_log(query)}" params={_format_params_for_log(vars)}'
        )
        return super().execute(query, vars)

    def executemany(self, query, vars_list):
        count = len(vars_list) if vars_list is not None else 0
        logger.info(
            f'[POSTGRES_DB] executemany sql="{_format_query_for_log(query)}" batch_size={count}'
        )
        return super().executemany(query, vars_list)


class PostgresLoggingConnection(psycopg2.extensions.connection):
    def cursor(self, *args, **kwargs):
        if "cursor_factory" not in kwargs or kwargs["cursor_factory"] is None:
            kwargs["cursor_factory"] = PostgresLoggingCursor
        logger.info("[POSTGRES_DB] cursor_open")
        return super().cursor(*args, **kwargs)

    def commit(self):
        logger.info("[POSTGRES_DB] commit")
        return super().commit()

    def rollback(self):
        logger.info("[POSTGRES_DB] rollback")
        return super().rollback()

    def close(self):
        logger.info("[POSTGRES_DB] connection_close")
        return super().close()


def _get_dsn() -> str:
    env = (ENVIRONMENT or "development").lower()

    if env in {"production", "prod"}:
        candidates = [
            "DATABASE_URL",
            "POSTGRES_DSN_PROD",
            "DATABASE_URL_PROD",
            "POSTGRES_DSN",
            "DATABASE_URL_EXTERNAL",
        ]
    elif env in {"uat", "staging"}:
        candidates = [
            "DATABASE_URL",
            "POSTGRES_DSN_UAT",
            "DATABASE_URL_UAT",
            "POSTGRES_DSN",
            "DATABASE_URL_EXTERNAL",
        ]
    else:
        candidates = [
            "DATABASE_URL_EXTERNAL",
            "POSTGRES_DSN_DEV",
            "DATABASE_URL_DEV",
            "POSTGRES_DSN",
            "DATABASE_URL",
        ]

    dsn = None
    for key in candidates:
        value = os.getenv(key)
        if value:
            dsn = value
            break

    if not dsn:
        raise RuntimeError(
            "No PostgreSQL DSN found for FLASK_ENV. Set env-specific DSN "
            "(POSTGRES_DSN_DEV/UAT/PROD or DATABASE_URL_DEV/UAT/PROD) or "
            "fallback DSN (POSTGRES_DSN, DATABASE_URL_EXTERNAL, DATABASE_URL)."
        )
    # Render uses postgres:// but psycopg2 prefers postgresql://
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)
    return dsn


def get_db_connection() -> "_PooledConn":
    """Borrow a connection from the pool (creates the pool on first call)."""
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    dsn=_get_dsn(),
                    connection_factory=PostgresLoggingConnection,
                )
                logger.info(f"[POSTGRES_DB] pool_created minconn=1 maxconn=10 env={ENVIRONMENT}")

    raw = _POOL.getconn()
    # Ensure the connection is still alive; replace if not
    try:
        raw.isolation_level  # lightweight attribute access that raises if closed
        if raw.closed:
            raise psycopg2.OperationalError("connection closed")
    except Exception:
        try:
            _POOL.putconn(raw, close=True)
        except Exception:
            pass
        raw = psycopg2.connect(_get_dsn(), connection_factory=PostgresLoggingConnection)
        _POOL.putconn(raw)  # add back
        raw = _POOL.getconn()

    logger.info(f"[POSTGRES_DB] connection_from_pool env={ENVIRONMENT}")
    return _PooledConn(raw, _POOL)


class _PooledConn:
    """Wraps a pooled connection so that close() returns it to the pool."""
    __slots__ = ("_conn", "_pool", "_returned")

    def __init__(self, conn: psycopg2.extensions.connection, pool: psycopg2.pool.ThreadedConnectionPool):
        self._conn = conn
        self._pool = pool
        self._returned = False

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    @property
    def closed(self):
        return self._conn.closed

    def close(self):
        """Return the connection to the pool (does NOT close the underlying TCP connection)."""
        if not self._returned:
            self._returned = True
            try:
                if not self._conn.closed:
                    self._conn.rollback()  # reset any uncommitted state
            except Exception:
                pass
            self._pool.putconn(self._conn)
            logger.info("[POSTGRES_DB] connection_returned_to_pool")


# ---------------------------------------------------------------------------
# Table-name helper
# ---------------------------------------------------------------------------


def _env_prefixed_table_name(base: str) -> str:
    env = (ENVIRONMENT or "").strip()
    return f"{env}_{base}" if env else base


def _detect_table_prefix(cursor) -> None:
    """Batch all 8 to_regclass checks into a single round-trip using a provided cursor."""
    global _AUTO_DETECTED_ENV_PREFIX, _AUTO_DETECT_ATTEMPTED

    _AUTO_DETECT_ATTEMPTED = True

    if not ENVIRONMENT:
        _AUTO_DETECTED_ENV_PREFIX = False
        return

    check_names = (
        [_env_prefixed_table_name(t) for t in ("game_stats", "player_game_state", "player_stats", "country_stats")]
        + ["game_stats", "player_game_state", "player_stats", "country_stats"]
    )
    cursor.execute(
        "SELECT " + ", ".join(f"to_regclass('public.{t}')" for t in check_names)
    )
    row = cursor.fetchone()
    prefixed_hits = sum(1 for v in row[:4] if v)
    base_hits = sum(1 for v in row[4:] if v)

    _AUTO_DETECTED_ENV_PREFIX = prefixed_hits > 0 and base_hits == 0
    logger.info(
        "[POSTGRES_DB] auto-detected env-prefixed tables; using prefixed table names"
        if _AUTO_DETECTED_ENV_PREFIX
        else "[POSTGRES_DB] using unprefixed table names"
    )


def _resolve_table_prefix_mode() -> bool:
    global _AUTO_DETECTED_ENV_PREFIX, _AUTO_DETECT_ATTEMPTED

    if USE_ENV_TABLE_PREFIX:
        return True

    if _AUTO_DETECT_ATTEMPTED:
        return bool(_AUTO_DETECTED_ENV_PREFIX)

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _detect_table_prefix(cursor)
    except Exception as exc:
        _AUTO_DETECTED_ENV_PREFIX = False
        _AUTO_DETECT_ATTEMPTED = True
        logger.warning(f"[POSTGRES_DB] could not auto-detect env-prefixed tables: {exc}")
    finally:
        if conn is not None:
            conn.close()

    return bool(_AUTO_DETECTED_ENV_PREFIX)


def table_name(base: str) -> str:
    """Return base table name unless env-prefix mode is explicitly enabled."""
    if base == "daily_game":
        return "daily_game"
    if _resolve_table_prefix_mode():
        return _env_prefixed_table_name(base)
    return base


def _table_exists(cursor, table: str) -> bool:
    cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
    row = cursor.fetchone()
    return bool(row and row[0])


def _backfill_legacy_play_tables(cursor) -> None:
    unified_table = table_name("player_game_state")
    legacy_state = table_name("player_daily_state")
    legacy_results = table_name("player_results")

    if _table_exists(cursor, legacy_state):
        cursor.execute(
            f"""
            INSERT INTO {unified_table}
                (player_uid, game_date, guess_history, wrong_guesses,
                 hard_mode, guessed_main_country, game_over, game_result_recorded)
            SELECT
                player_uid,
                game_date,
                COALESCE(guess_history, '[]'),
                COALESCE(wrong_guesses, '[]'),
                COALESCE(hard_mode, 0),
                COALESCE(guessed_main_country, 0),
                COALESCE(game_over, 0),
                COALESCE(game_result_recorded, 0)
            FROM {legacy_state}
            ON CONFLICT (player_uid, game_date) DO UPDATE SET
                guess_history = COALESCE({unified_table}.guess_history, EXCLUDED.guess_history),
                wrong_guesses = COALESCE({unified_table}.wrong_guesses, EXCLUDED.wrong_guesses),
                hard_mode = GREATEST({unified_table}.hard_mode, EXCLUDED.hard_mode),
                guessed_main_country = GREATEST({unified_table}.guessed_main_country, EXCLUDED.guessed_main_country),
                game_over = GREATEST({unified_table}.game_over, EXCLUDED.game_over),
                game_result_recorded = GREATEST({unified_table}.game_result_recorded, EXCLUDED.game_result_recorded)
            """
        )

    if _table_exists(cursor, legacy_results):
        cursor.execute(
            f"""
            INSERT INTO {unified_table}
                (player_uid, game_date, game_number, game_over, game_result_recorded, leaderboard_recorded)
            SELECT
                player_uid,
                game_date::text,
                game_number,
                1,
                1,
                1
            FROM {legacy_results}
            ON CONFLICT (player_uid, game_date) DO UPDATE SET
                game_number = COALESCE(EXCLUDED.game_number, {unified_table}.game_number),
                game_over = 1,
                game_result_recorded = 1,
                leaderboard_recorded = 1
            """
        )


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


def ensure_schema() -> None:
    """Create all application tables once per process."""
    global _SCHEMA_READY

    if _SCHEMA_READY:
        return

    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Detect prefix on this connection (1 round-trip) before building DDL
            if not _AUTO_DETECT_ATTEMPTED:
                _detect_table_prefix(cursor)

            # Build DDL now that table_name() returns cached values
            ddl_statements = [
                f"""
                CREATE TABLE IF NOT EXISTS {table_name("game_stats")} (
                    game_date   DATE    PRIMARY KEY,
                    successes   INTEGER DEFAULT 0,
                    failures    INTEGER DEFAULT 0
                )
                """,
                f"""
                CREATE TABLE IF NOT EXISTS {table_name("daily_game")} (
                    game_date   TEXT    NOT NULL UNIQUE,
                    country     TEXT    NOT NULL,
                    rotation    INTEGER NOT NULL
                )
                """,
                f"""
                CREATE TABLE IF NOT EXISTS {table_name("player_game_state")} (
                    player_uid            TEXT    NOT NULL,
                    game_date             TEXT    NOT NULL,
                    game_number           INTEGER,
                    guess_history         TEXT    DEFAULT '[]',
                    wrong_guesses         TEXT    DEFAULT '[]',
                    hard_mode             INTEGER DEFAULT 0,
                    guessed_main_country  INTEGER DEFAULT 0,
                    game_over             INTEGER DEFAULT 0,
                    game_result           TEXT,
                    game_result_recorded  INTEGER DEFAULT 0,
                    leaderboard_recorded  INTEGER DEFAULT 0,
                    recorded_at           TIMESTAMP,
                    PRIMARY KEY (player_uid, game_date)
                )
                """,
                f"""
                CREATE TABLE IF NOT EXISTS {table_name("player_stats")} (
                    player_uid      TEXT    PRIMARY KEY,
                    games_played    INTEGER DEFAULT 0,
                    games_won       INTEGER DEFAULT 0,
                    current_streak  INTEGER DEFAULT 0,
                    best_streak     INTEGER DEFAULT 0,
                    migrated        INTEGER DEFAULT 0,
                    last_updated    DATE,
                    player_country  TEXT,
                    player_city     TEXT
                )
                """,
                f"""
                CREATE TABLE IF NOT EXISTS {table_name("country_stats")} (
                    id          SERIAL  PRIMARY KEY,
                    game_date   TEXT    NOT NULL,
                    country     TEXT,
                    region      TEXT,
                    city        TEXT,
                    plays       INTEGER DEFAULT 0,
                    successes   INTEGER DEFAULT 0,
                    failures    INTEGER DEFAULT 0,
                    UNIQUE (game_date, country, region, city)
                )
                """,
            ]

            for ddl in ddl_statements:
                cursor.execute(ddl)
            _backfill_legacy_play_tables(cursor)
            conn.commit()
            _SCHEMA_READY = True
        finally:
            conn.close()


def init_db() -> None:
    """Create all application tables (idempotent; safe to call on every start)."""
    ensure_schema()

    cleanup_old_player_results()
    cleanup_old_daily_games(30)


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------


def cleanup_old_player_results() -> None:
    """Remove old recorded results from unified player_game_state entries."""
    uk = pytz.timezone("Europe/London")
    cutoff = datetime.now(uk).date() - timedelta(days=30)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            DELETE FROM {table_name("player_game_state")}
            WHERE game_date::date < %s AND game_result_recorded = 1
            """,
            (cutoff,),
        )
        deleted = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    if deleted:
        logger.info(
            f"Cleaned up {deleted} old player_game_state result rows (before {cutoff})"
        )


def cleanup_old_daily_games(days: int = 30) -> None:
    """Delete player_game_state rows older than *days* days."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            DELETE FROM {table_name("player_game_state")}
            WHERE game_date::date < CURRENT_DATE - INTERVAL '{days} days'
            """
        )
        deleted = cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    logger.info(
        f"Cleanup: deleted {deleted} player_game_state rows older than {days} days"
    )


# ---------------------------------------------------------------------------
# Game number / daily country
# ---------------------------------------------------------------------------


def get_game_number() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT COUNT(DISTINCT game_date) FROM {table_name('daily_game')}"
        )
        row = cursor.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def _get_current_rotation(cursor) -> int:
    cursor.execute(f"SELECT MAX(rotation) FROM {table_name('daily_game')}")
    result = cursor.fetchone()[0]
    return result if result is not None else 0


def _get_used_countries(cursor, rotation: int) -> set:
    cursor.execute(
        f"SELECT country FROM {table_name('daily_game')} WHERE rotation = %s",
        (rotation,),
    )
    return {row[0] for row in cursor.fetchall()}


def get_today_country() -> str:
    today = date.today().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT country FROM {table_name('daily_game')} WHERE game_date = %s",
            (today,),
        )
        row = cursor.fetchone()
        if row:
            return row[0]

        all_countries = set(get_all_drop_down_options())
        borderable = {c for c in all_countries if c in border_map}

        current_rotation = _get_current_rotation(cursor)
        used = _get_used_countries(cursor, current_rotation)
        remaining = list(borderable - used)

        if not remaining:
            current_rotation += 1
            remaining = list(borderable)

        new_country = random.choice(remaining)
        cursor.execute(
            f"INSERT INTO {table_name('daily_game')} (game_date, country, rotation) VALUES (%s, %s, %s)",
            (today, new_country, current_rotation),
        )
        conn.commit()
        logger.info(f"Assigned new daily country: {new_country} for date: {today}")
        return new_country
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Aggregated daily stats
# ---------------------------------------------------------------------------


def get_games_today() -> tuple[int, int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT COALESCE(successes, 0), COALESCE(failures, 0)
            FROM   {table_name("game_stats")}
            WHERE  game_date = CURRENT_DATE
            """,
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if row:
        successes, failures = row
        total = successes + failures
        rate = round((successes / total) * 100) if total else 0
        return total, rate
    return 0, 0


def get_total_games() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT COALESCE(SUM(successes + failures), 0) FROM {table_name('game_stats')}"
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def get_landing_stats() -> tuple[int, int, int, int]:
    """Return (game_number, games_today, today_success_rate, total_games).

    Result is cached for _LANDING_STATS_CACHE_TTL seconds so repeated page
    loads do not hit the database at all.
    """
    global _LANDING_STATS_CACHE, _LANDING_STATS_CACHE_TS

    now = time.monotonic()
    with _LANDING_STATS_LOCK:
        if _LANDING_STATS_CACHE is not None and (now - _LANDING_STATS_CACHE_TS) < _LANDING_STATS_CACHE_TTL:
            return _LANDING_STATS_CACHE

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT COUNT(DISTINCT game_date) FROM {table_name('daily_game')}"
        )
        row = cursor.fetchone()
        game_number = row[0] if row else 0

        cursor.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN game_date = CURRENT_DATE THEN successes ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN game_date = CURRENT_DATE THEN failures  ELSE 0 END), 0),
                COALESCE(SUM(successes + failures), 0)
            FROM {table_name("game_stats")}
            """
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if row:
        today_succ, today_fail, total = row
        games_today = today_succ + today_fail
        rate = round((today_succ / games_today) * 100) if games_today else 0
        result = (int(game_number), int(games_today), rate, int(total))
    else:
        result = (int(game_number), 0, 0, 0)

    with _LANDING_STATS_LOCK:
        _LANDING_STATS_CACHE = result
        _LANDING_STATS_CACHE_TS = time.monotonic()

    return result


def invalidate_landing_stats_cache() -> None:
    """Call after recording a game result so stats refresh promptly."""
    global _LANDING_STATS_CACHE_TS
    with _LANDING_STATS_LOCK:
        _LANDING_STATS_CACHE_TS = 0.0


# ---------------------------------------------------------------------------
# Recording a game result
# ---------------------------------------------------------------------------


def record_game_result(
    success: bool,
    remaining_countries: str,
    player_uid: str | None = None,
) -> None:
    uk = pytz.timezone("Europe/London")
    today = datetime.now(uk).date().isoformat()
    game_number = get_game_number()

    conn = get_db_connection()
    cursor = conn.cursor()
    is_new_result = True

    try:
        if player_uid:
            cursor.execute(
                f"""
                SELECT game_result_recorded
                FROM {table_name("player_game_state")}
                WHERE game_date = %s AND player_uid = %s
                """,
                (today, player_uid),
            )
            state_row = cursor.fetchone()
            if state_row and bool(state_row[0]):
                logger.info(
                    f"Skipping duplicate game result for player {player_uid} on {today}"
                )
                is_new_result = False
            else:
                cursor.execute(
                    f"""
                    INSERT INTO {table_name("player_game_state")}
                        (player_uid, game_date, game_number, game_over, game_result, game_result_recorded, recorded_at)
                    VALUES (%s, %s, %s, 1, %s, 1, NOW())
                    ON CONFLICT (player_uid, game_date) DO UPDATE SET
                        game_number = EXCLUDED.game_number,
                        game_over = 1,
                        game_result = EXCLUDED.game_result,
                        game_result_recorded = 1,
                        recorded_at = NOW()
                    """,
                    (player_uid, today, game_number, "win" if success else "loss"),
                )

        # Daily aggregated stats
        if success:
            cursor.execute(
                f"""
                INSERT INTO {table_name("game_stats")} (game_date, successes, failures)
                VALUES (%s, 1, 0)
                ON CONFLICT (game_date) DO UPDATE SET successes = {table_name("game_stats")}.successes + 1
                """,
                (today,),
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO {table_name("game_stats")} (game_date, successes, failures)
                VALUES (%s, 0, 1)
                ON CONFLICT (game_date) DO UPDATE SET failures = {table_name("game_stats")}.failures + 1
                """,
                (today,),
            )

        # Per-player stats — only on first result of the day
        if player_uid and is_new_result:
            player_country, player_city = "Unknown", "Unknown"
            user_ip = get_user_ip()
            if user_ip:
                player_country, _region, player_city = get_user_location(user_ip)

            cursor.execute(
                f"""
                INSERT INTO {table_name("player_stats")}
                    (player_uid, games_played, games_won, current_streak, best_streak,
                     last_updated, player_country, player_city)
                VALUES (%s, 1, %s, %s, %s, CURRENT_DATE, %s, %s)
                ON CONFLICT (player_uid) DO UPDATE SET
                    games_played   = {table_name("player_stats")}.games_played + 1,
                    games_won      = {table_name("player_stats")}.games_won + %s,
                    current_streak = CASE WHEN %s
                                         THEN {table_name("player_stats")}.current_streak + 1
                                         ELSE 0 END,
                    best_streak    = CASE WHEN %s
                                         THEN GREATEST({table_name("player_stats")}.best_streak,
                                                       {table_name("player_stats")}.current_streak + 1)
                                         ELSE {table_name("player_stats")}.best_streak END,
                    last_updated   = CURRENT_DATE,
                    player_country = %s,
                    player_city    = %s
                """,
                (
                    # INSERT values
                    player_uid,
                    1 if success else 0,
                    1 if success else 0,
                    1 if success else 0,
                    player_country,
                    player_city,
                    # UPDATE values
                    1 if success else 0,
                    success,
                    success,
                    player_country,
                    player_city,
                ),
            )

            # Read back for logging
            cursor.execute(
                f"SELECT games_played, games_won, current_streak, best_streak FROM {table_name('player_stats')} WHERE player_uid = %s",
                (player_uid,),
            )
            row = cursor.fetchone()
            if row:
                gp, gw, cs, bs = row
                rate = round((gw / gp) * 100) if gp else 0
                logger.info(
                    json.dumps(
                        {
                            "event": "player_stats_updated",
                            "player_uid": player_uid,
                            "result": "win" if success else "loss",
                            "games_played": gp,
                            "games_won": gw,
                            "current_streak": cs,
                            "best_streak": bs,
                            "success_rate": rate,
                            "player_country": player_country,
                            "player_city": player_city,
                        }
                    )
                )

        conn.commit()
        invalidate_landing_stats_cache()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Player stats
# ---------------------------------------------------------------------------


def get_player_stats(player_uid: str) -> dict | None:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT games_played, games_won, current_streak, best_streak,
                   migrated, player_country, player_city, last_updated
            FROM   {table_name("player_stats")}
            WHERE  player_uid = %s
            """,
            (player_uid,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if row:
        result = {
            "games_played": row[0] or 0,
            "games_won": row[1] or 0,
            "current_streak": row[2] or 0,
            "best_streak": row[3] or 0,
            "migrated": bool(row[4]),
            "player_country": row[5] or "Unknown",
            "player_city": row[6] or "Unknown",
            "last_updated": row[7],
        }
        logger.debug(f"[GET_PLAYER_STATS] Found stats for {player_uid}: {result}")
        return result

    logger.debug(f"[GET_PLAYER_STATS] No stats found for {player_uid}")
    return None


def migrate_player_stats(player_uid: str, stats: dict) -> dict:
    """Merge client-side localStorage stats into player_stats (idempotent)."""
    existing = get_player_stats(player_uid)
    logger.info(f"[MIGRATION] Existing stats for {player_uid}: {existing}")

    if existing and existing.get("migrated"):
        logger.info(f"[MIGRATION] {player_uid} already migrated — skipping.")
        return {"status": "skipped", "reason": "already_migrated"}

    player_country, player_city = "Unknown", "Unknown"
    user_ip = get_user_ip()
    if user_ip:
        player_country, _region, player_city = get_user_location(user_ip)

    games_played = int(stats.get("gamesPlayed", 0))
    games_won = int(stats.get("gamesWon", 0))
    current_streak = int(stats.get("currentStreak", 0))
    best_streak = int(stats.get("bestStreak", current_streak))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if existing:
            ep = existing.get("games_played", 0) or 0
            ew = existing.get("games_won", 0) or 0
            ecs = existing.get("current_streak", 0) or 0
            ebs = existing.get("best_streak", 0) or 0

            mp = max(ep, games_played)
            mw = max(ew, games_won)
            mcs = max(ecs, current_streak)
            mbs = max(ebs, best_streak)

            logger.info(
                f"[MIGRATION] Deduping merge: played max({ep},{games_played})={mp}, "
                f"won max({ew},{games_won})={mw}"
            )
            cursor.execute(
                f"""
                UPDATE {table_name("player_stats")} SET
                    games_played   = %s,
                    games_won      = %s,
                    current_streak = %s,
                    best_streak    = %s,
                    migrated       = 1,
                    last_updated   = CURRENT_DATE,
                    player_country = %s,
                    player_city    = %s
                WHERE player_uid = %s
                """,
                (mp, mw, mcs, mbs, player_country, player_city, player_uid),
            )
        else:
            mp, mw, mcs, mbs = games_played, games_won, current_streak, best_streak
            cursor.execute(
                f"""
                INSERT INTO {table_name("player_stats")}
                    (player_uid, games_played, games_won, current_streak, best_streak,
                     migrated, last_updated, player_country, player_city)
                VALUES (%s, %s, %s, %s, %s, 1, CURRENT_DATE, %s, %s)
                """,
                (player_uid, mp, mw, mcs, mbs, player_country, player_city),
            )

        conn.commit()
    finally:
        conn.close()

    logger.info(
        json.dumps(
            {
                "event": "player_stats_migrated",
                "player_uid": player_uid,
                "games_played": mp,
                "games_won": mw,
                "current_streak": mcs,
                "best_streak": mbs,
                "success_rate": round((mw / mp) * 100) if mp else 0,
                "player_country": player_country,
                "player_city": player_city,
                "action": "update" if existing else "insert",
            }
        )
    )
    logger.info(f"[MIGRATION] ✅ Complete for {player_uid}")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# World leaderboard
# ---------------------------------------------------------------------------


def record_world_leaderboard_result(
    success: bool,
    player_uid: str | None = None,
) -> dict:
    country, region, city = "Unknown", "Unknown", "Unknown"
    user_ip = get_user_ip()
    if user_ip:
        country, region, city = get_user_location(user_ip)

    if country == "Unknown":
        logger.warning(
            f"Not updating country stats — could not determine location for IP: {user_ip}"
        )
        return {
            "player_country": "Unknown",
            "player_region": "Unknown",
            "player_city": "Unknown",
        }

    uk = pytz.timezone("Europe/London")
    game_date = datetime.now(uk).date().isoformat()
    game_number = get_game_number()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if player_uid:
            cursor.execute(
                f"""
                SELECT leaderboard_recorded
                FROM {table_name("player_game_state")}
                WHERE game_date = %s AND player_uid = %s
                """,
                (game_date, player_uid),
            )
            row = cursor.fetchone()
            if row and bool(row[0]):
                logger.info(
                    f"Skipping leaderboard update — already recorded for {player_uid} on {game_date}"
                )
                return {
                    "player_country": country,
                    "player_region": region,
                    "player_city": city,
                }

        logger.info(f"Updating country stats for {country}, {region}, {city}")
        cursor.execute(
            f"""
            INSERT INTO {table_name("country_stats")}
                (game_date, country, region, city, plays, successes, failures)
            VALUES (%s, %s, %s, %s, 1, %s, %s)
            ON CONFLICT (game_date, country, region, city) DO UPDATE SET
                plays     = {table_name("country_stats")}.plays + 1,
                successes = {table_name("country_stats")}.successes + EXCLUDED.successes,
                failures  = {table_name("country_stats")}.failures  + EXCLUDED.failures
            """,
            (
                game_date,
                country,
                region,
                city,
                1 if success else 0,
                0 if success else 1,
            ),
        )

        if player_uid:
            cursor.execute(
                f"""
                INSERT INTO {table_name("player_game_state")}
                    (player_uid, game_date, game_number, leaderboard_recorded)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (player_uid, game_date) DO UPDATE SET
                    game_number = COALESCE({table_name("player_game_state")}.game_number, EXCLUDED.game_number),
                    leaderboard_recorded = 1
                """,
                (player_uid, game_date, game_number),
            )

        conn.commit()
    finally:
        conn.close()

    return {"player_country": country, "player_region": region, "player_city": city}


def get_leaderboard_data() -> dict:
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=PostgresLoggingRealDictCursor)
    tbl = table_name("country_stats")

    daily_sql = f"""
        SELECT
            country,
            SUM(successes) AS total_successes,
            SUM(failures)  AS total_failures,
            SUM(plays)     AS total_plays,
            CASE
                WHEN (SUM(successes) + SUM(failures)) = 0 THEN 0
                ELSE CAST(SUM(successes) AS FLOAT) * 100.0
                       / (SUM(successes) + SUM(failures))
            END AS success_rate
        FROM   {tbl}
        WHERE  game_date::date = CURRENT_DATE
        GROUP  BY country
        HAVING SUM(plays) > 0
        ORDER  BY success_rate DESC, SUM(plays) DESC
        LIMIT  20
    """
    all_sql = f"""
        SELECT
            country,
            SUM(successes) AS total_successes,
            SUM(failures)  AS total_failures,
            SUM(plays)     AS total_plays,
            CASE
                WHEN (SUM(successes) + SUM(failures)) = 0 THEN 0
                ELSE CAST(SUM(successes) AS FLOAT) * 100.0
                       / (SUM(successes) + SUM(failures))
            END AS success_rate
        FROM   {tbl}
        GROUP  BY country
        HAVING SUM(plays) > 0
        ORDER  BY success_rate DESC, SUM(plays) DESC
        LIMIT  100
    """

    try:
        cursor.execute(daily_sql)
        daily = cursor.fetchall()

        cursor.execute(all_sql)
        all_time = cursor.fetchall()
    finally:
        conn.close()

    def format_data(rows):
        return [
            {
                "country": r["country"],
                "success_rate": round(r["success_rate"], 1),
                "total_guesses": int(r["total_plays"]),
            }
            for r in rows
        ]

    return {"daily": format_data(daily), "all_time": format_data(all_time)}


# ---------------------------------------------------------------------------
# Daily game state
# ---------------------------------------------------------------------------


def load_daily_game_state(player_uid: str) -> dict | None:
    today = date.today().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT guess_history, wrong_guesses,
                   guessed_main_country, game_over, game_result_recorded
            FROM   {table_name("player_game_state")}
            WHERE  player_uid = %s AND game_date = %s
            """,
            (player_uid, today),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if row:
        return {
            "guess_history": json.loads(row[0] or "[]"),
            "wrong_guesses": json.loads(row[1] or "[]"),
            "guessed_main_country": bool(row[2]),
            "game_over": bool(row[3]),
            "game_result_recorded": bool(row[4]),
        }
    return None


def save_daily_game_state(player_uid: str, game_over: bool = False) -> None:
    today = date.today().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            INSERT INTO {table_name("player_game_state")}
                (player_uid, game_date, guess_history, wrong_guesses,
                 guessed_main_country, hard_mode, game_over, game_result_recorded, game_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_uid, game_date) DO UPDATE SET
                guess_history        = EXCLUDED.guess_history,
                wrong_guesses        = EXCLUDED.wrong_guesses,
                guessed_main_country = EXCLUDED.guessed_main_country,
                hard_mode            = EXCLUDED.hard_mode,
                game_over            = EXCLUDED.game_over,
                game_result_recorded = EXCLUDED.game_result_recorded
            """,
            (
                player_uid,
                today,
                json.dumps(session.get("guess_history") or []),
                json.dumps(session.get("wrong_guesses") or []),
                bool(session.get("guessed_main_country", False)),
                bool(session.get("hard_mode", False)),
                bool(game_over),
                bool(session.get("game_result_recorded", False)),
                session.get("game_number"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
