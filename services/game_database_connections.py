import json
import os
import random
import sqlite3

# Optional import for PostgreSQL support; installed on feature branch
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

from flask import request, session
import pytz

from datetime import date, datetime

from services.game_get_data import (
    get_all_drop_down_options,
    get_user_ip,
    get_user_location,
)
from services.game_logger import setup_logger

# Setup logger
logger = setup_logger()

# Set database paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, "..", "db")  # assumes this file is in services/
os.makedirs(DB_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_FOLDER, "games.db")
ENVIRONMENT = os.getenv("FLASK_ENV", "development")  # default if not set
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()  # can be 'sqlite' or 'postgres'


def table_name(base: str) -> str:
    """Return the correct table name for the current environment.

    When using PostgreSQL we prefix tables with the environment name (dev/uat/prod)
    so that a single database can host multiple environments. SQLite keeps its
    existing names unchanged.
    """
    if DB_TYPE == "postgres" and ENVIRONMENT:
        return f"{ENVIRONMENT}_{base}"
    return base


def get_postgres_connection():
    """Return a new psycopg2 connection using environment variables.

    Expects one of the following:
    - POSTGRES_DSN (custom connection string)
    - DATABASE_URL_EXTERNAL (for local testing against Render database)
    - DATABASE_URL (internal Render URL, only works inside Render)
    
    Raises if psycopg2 is not installed or the DSN is missing.
    """
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed; cannot open postgres connection")
    # Try external URL first (for local testing), then internal URL (for Render production)
    dsn = (
        os.getenv("POSTGRES_DSN") 
        or os.getenv("DATABASE_URL_EXTERNAL") 
        or os.getenv("DATABASE_URL")
    )
    if not dsn:
        raise RuntimeError(
            "No Postgres DSN configured. Set one of: POSTGRES_DSN, DATABASE_URL_EXTERNAL, or DATABASE_URL"
        )
    return psycopg2.connect(dsn)


def get_db_connection():
    """Return a database connection for the configured DB_TYPE."""
    if DB_TYPE == "postgres":
        return get_postgres_connection()
    # default to sqlite
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_FOLDER = os.path.join(BASE_DIR, "..", "db")  # assumes this file is in services/
    os.makedirs(DB_FOLDER, exist_ok=True)
    DB_PATH = os.path.join(DB_FOLDER, "games.db")
    return sqlite3.connect(DB_PATH)


def run_query(sql: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False):
    """Helper that executes SQL against the configured backend.

    - Converts ``%s`` placeholders to ``?`` for SQLite.
    - Opens/closes the connection automatically.
    - Commits after executing (Postgres requires this, SQLite is harmless).
    - Optionally returns ``fetchone`` or ``fetchall`` results.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if DB_TYPE != "postgres":
        sql = sql.replace("%s", "?")
    cursor.execute(sql, params)
    result = None
    if fetchone:
        result = cursor.fetchone()
    elif fetchall:
        result = cursor.fetchall()
    conn.commit()
    conn.close()
    return result


# Load GeoJSON shapes once
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)



def cleanup_old_player_results():
    """Remove player_results entries older than 30 days."""
    uk = pytz.timezone("Europe/London")
    today = datetime.now(uk).date()
    cutoff_date = today - __import__("datetime").timedelta(days=30)

    sql = f"DELETE FROM {table_name('player_results')} WHERE game_date < %s"
    run_query(sql, (cutoff_date,))
    # sqlite rowcount isn't returned via run_query; open a connection if we need it
    if DB_TYPE == 'sqlite':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(sql.replace('%s', '?'), (cutoff_date,))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
    else:
        deleted_count = None

    if deleted_count and deleted_count > 0:
        logger.info(
            f"Cleaned up {deleted_count} old player result records (before {cutoff_date})"
        )


def cleanup_old_daily_games(days: int = 30):
    """
    Deletes in-progress daily game state older than N days.
    """
    sql = f"""
        DELETE FROM {table_name('player_daily_state')}
        WHERE game_date < date('now', %s)
    """
    # run_query will convert %s to ? for sqlite
    params = (f"-{days} days",)
    conn = get_db_connection()
    cursor = conn.cursor()
    if DB_TYPE != 'postgres':
        sql = sql.replace('%s', '?')
    cursor.execute(sql, params)
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    logger.info(f"Cleanup: deleted {deleted} player_daily_state rows older than {days} days")


def init_db():
    # create tables using environment-aware names
    create_sql = {
        'game_stats': """
            CREATE TABLE IF NOT EXISTS %s (
                game_date DATE PRIMARY KEY,
                successes INTEGER DEFAULT 0,
                failures INTEGER DEFAULT 0
            )
        """,
        'daily_game': """
            CREATE TABLE IF NOT EXISTS %s (
                game_date DATE PRIMARY KEY,
                country TEXT
            )
        """,
        'player_results': """
            CREATE TABLE IF NOT EXISTS %s (
                game_number INTEGER,
                game_date DATE,
                player_uid TEXT,
                PRIMARY KEY (game_date, game_number, player_uid)
            )
        """,
        'player_daily_state': """
            CREATE TABLE IF NOT EXISTS %s (
                player_uid TEXT NOT NULL,
                game_date TEXT NOT NULL,
                guess_history TEXT,
                wrong_guesses TEXT,
                hard_mode INTEGER,
                guessed_main_country INTEGER,
                game_over INTEGER,
                game_result_recorded INTEGER,
                PRIMARY KEY (player_uid, game_date)
            )
        """,
        'player_stats': """
            CREATE TABLE IF NOT EXISTS %s (
                player_uid TEXT PRIMARY KEY,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                current_streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                migrated INTEGER DEFAULT 0,
                last_updated DATE
            )
        """,
    }
    conn = get_db_connection()
    cursor = conn.cursor()
    for base, template in create_sql.items():
        name = table_name(base)
        sql = template % name
        if DB_TYPE != 'postgres':
            sql = sql.replace('%s', '?')  # should not occur in create but safe
        cursor.execute(sql)

    conn.commit()
    conn.close()

    # Clean up old records
    cleanup_old_player_results()
    cleanup_old_daily_games(30)


def record_game_result(success: bool, remaining_countries: str, player_uid: str = None):
    # Get today's date in UK time
    uk = pytz.timezone("Europe/London")
    today = datetime.now(uk).date()
    game_number = get_game_number()

    # ----- Function to record the player session result -----

    # If a player_uid is provided, ensure we only count once per player per day
    if player_uid:
        sql_check = f"SELECT 1 FROM {table_name('player_results')} WHERE game_date = %s AND player_uid = %s"
        existing = run_query(sql_check, (today, player_uid), fetchone=True)
        if existing:
            logger.info(f"Skipping duplicate game result for player {player_uid} on {today}")
            return

        sql_insert = f"INSERT INTO {table_name('player_results')} (game_date, game_number, player_uid) VALUES (%s, %s, %s)"
        run_query(sql_insert, (today, game_number, player_uid))

    # ----- Update daily aggregated stats -----
    table_stats = table_name('game_stats')
    if success:
        sql = f"""
            INSERT INTO {table_stats} (game_date, successes, failures)
            VALUES (%s, 1, 0)
            ON CONFLICT(game_date) DO UPDATE SET successes = successes + 1
        """
        run_query(sql, (today,))
    else:
        sql = f"""
            INSERT INTO {table_stats} (game_date, successes, failures)
            VALUES (%s, 0, 1)
            ON CONFLICT(game_date) DO UPDATE SET failures = failures + 1
        """
        run_query(sql, (today,))


def get_player_stats(player_uid: str):
    sql = f"SELECT games_played, games_won, current_streak, best_streak, migrated " \
          f"FROM {table_name('player_stats')} WHERE player_uid = %s"
    row = run_query(sql, (player_uid,), fetchone=True)

    if row:
        result = {
            "games_played": row[0] or 0,
            "games_won": row[1] or 0,
            "current_streak": row[2] or 0,
            "best_streak": row[3] or 0,
            "migrated": bool(row[4]),
        }
        logger.debug(f"[GET_PLAYER_STATS] Found stats for {player_uid}: {result}")
        return result

    logger.debug(f"[GET_PLAYER_STATS] No stats found for {player_uid}")
    return None


def migrate_player_stats(player_uid: str, stats: dict):
    """Merge client-side stats into server-side `player_stats` table.

    This operation is idempotent per-player: if `migrated` is set, we skip to avoid double-counting.
    """
    logger.info(f"[MIGRATION] Starting migration for player {player_uid}")
    logger.info(f"[MIGRATION] Client-side stats received: {stats}")
    
    existing = get_player_stats(player_uid)
    logger.info(f"[MIGRATION] Existing server stats for {player_uid}: {existing}")

    if existing and existing.get("migrated"):
        logger.warning(f"[MIGRATION] Player {player_uid} already migrated. Skipping to prevent double-count.")
        return {"status": "skipped", "reason": "already_migrated"}

    # Prepare merge values
    games_played = int(stats.get("gamesPlayed", 0))
    games_won = int(stats.get("gamesWon", 0))
    current_streak = int(stats.get("currentStreak", 0))
    best_streak = int(stats.get("bestStreak", current_streak))

    logger.info(f"[MIGRATION] Parsed client stats: played={games_played}, won={games_won}, streak={current_streak}, best={best_streak}")

    if existing:
        merged_played = (existing.get("games_played", 0) or 0) + games_played
        merged_won = (existing.get("games_won", 0) or 0) + games_won
        merged_current_streak = max(existing.get("current_streak", 0) or 0, current_streak)
        merged_best_streak = max(existing.get("best_streak", 0) or 0, best_streak)

        logger.info(f"[MIGRATION] Merging existing and client stats: played {existing.get('games_played')} + {games_played} = {merged_played}, won {existing.get('games_won')} + {games_won} = {merged_won}")

        sql = f"""
            UPDATE {table_name('player_stats')} SET
                games_played = %s,
                games_won = %s,
                current_streak = %s,
                best_streak = %s,
                migrated = 1,
                last_updated = %s
            WHERE player_uid = %s
        """
        run_query(sql, (merged_played, merged_won, merged_current_streak, merged_best_streak, datetime.now().date(), player_uid))
        logger.info(f"[MIGRATION] Updated existing player stats: {player_uid}")
    else:
        logger.info(f"[MIGRATION] No existing stats found. Creating new record for {player_uid}")
        sql = f"""
            INSERT INTO {table_name('player_stats')} (
                player_uid, games_played, games_won, current_streak, best_streak, migrated, last_updated
            ) VALUES (%s, %s, %s, %s, %s, 1, %s)
        """
        run_query(sql, (player_uid, games_played, games_won, current_streak, best_streak, datetime.now().date()))
        logger.info(f"[MIGRATION] Inserted new player stats: {player_uid}")

    logger.info(f"[MIGRATION] ✅ Migration complete for player {player_uid}")
    return {"status": "ok"}


def get_game_number():
    sql = f"SELECT COUNT(DISTINCT game_date) FROM {table_name('daily_game')}"
    result = run_query(sql, fetchone=True)
    return result[0] if result else 0


def get_games_today():
    sql = f"""
        SELECT COALESCE(successes,0), COALESCE(failures,0)
        FROM {table_name('game_stats')}
        WHERE game_date = %s
    """
    row = run_query(sql, (date.today().isoformat(),), fetchone=True)

    if row:
        successes_today, failures_today = row
        games_today = successes_today + failures_today
        success_rate_today = (
            round((successes_today / games_today) * 100) if games_today > 0 else 0
        )
    else:
        games_today = 0
        success_rate_today = 0

    return games_today, success_rate_today


def get_total_games():
    sql = f"""
        SELECT SUM(successes + failures) AS total_games
        FROM {table_name('game_stats')}
    """
    row = run_query(sql, fetchone=True)
    total_games = row[0] if row and row[0] is not None else 0
    return total_games


def get_current_rotation():
    sql = f"SELECT MAX(rotation) FROM {table_name('daily_game')}"
    row = run_query(sql, fetchone=True)
    result = row[0] if row and row[0] is not None else 0
    return result


def get_used_countries(rotation):
    sql = f"SELECT country FROM {table_name('daily_game')} WHERE rotation = %s"
    rows = run_query(sql, (rotation,), fetchall=True)
    return {r[0] for r in rows} if rows else set()


def get_today_country():
    today = date.today().isoformat()

    # Check if today's game is already assigned
    sql = f"SELECT country FROM {table_name('daily_game')} WHERE game_date = %s"
    row = run_query(sql, (today,), fetchone=True)
    if row:
        return row[0]

    # get all the countries from the drop down json and compare it against the countries json
    all_countries = set(get_all_drop_down_options())
    borderable_countries = {
        country for country in all_countries if country in border_map
    }

    # check the rotation
    current_rotation = get_current_rotation()

    # ensure its not been used
    used = get_used_countries(current_rotation)

    remaining = list(borderable_countries - used)

    if not remaining:
        # All valid countries used in this rotation
        current_rotation += 1
        used = set()
        remaining = list(borderable_countries)

    new_country = random.choice(remaining)

    insert_sql = f"INSERT INTO {table_name('daily_game')} (game_date, country, rotation) VALUES (%s, %s, %s)"
    run_query(insert_sql, (today, new_country, current_rotation))

    logger.info(f"Assigned new daily country: {new_country} for date: {today}")

    return new_country


def get_leaderboard_data():
    # build base SQL fragments using table_name
    tbl = table_name('country_stats')
    daily_sql = f"""
        SELECT
            country,
            SUM(successes) AS total_successes,
            SUM(failures) AS total_failures,
            SUM(plays) AS total_plays,
            CASE
                WHEN (SUM(successes) + SUM(failures)) = 0 THEN 0
                ELSE (CAST(SUM(successes) AS FLOAT) * 100.0 / (SUM(successes) + SUM(failures)))
            END AS success_rate
        FROM {tbl}
        WHERE game_date = DATE('now', 'localtime')
        GROUP BY country
        HAVING total_plays > 0
        ORDER BY success_rate DESC, total_plays DESC
        LIMIT 20;
    """
    daily = run_query(daily_sql, fetchall=True)

    all_sql = f"""
        SELECT
            country,
            SUM(successes) AS total_successes,
            SUM(failures) AS total_failures,
            SUM(plays) AS total_plays,
            CASE
                WHEN (SUM(successes) + SUM(failures)) = 0 THEN 0
                ELSE (CAST(SUM(successes) AS FLOAT) * 100.0 / (SUM(successes) + SUM(failures)))
            END AS success_rate
        FROM {tbl}
        GROUP BY country
        HAVING total_plays > 0
        ORDER BY success_rate DESC, total_plays DESC
        LIMIT 100;
    """
    all_time = run_query(all_sql, fetchall=True)

    # Convert rows (tuples) to dicts for compatibility
    def format_data(rows):
        return [
            {
                "country": r[0],
                "success_rate": round(r[4], 1),
                "total_guesses": int(r[3]),
            }
            for r in rows
        ]

    return {"daily": format_data(daily), "all_time": format_data(all_time)}


def record_world_leaderboard_result(success: bool, player_uid: str = None):
    # Default values
    country, region, city = "Unknown", "Unknown", "Unknown"

    # If user IP available, get location
    user_ip = get_user_ip()  # Flask: get user's IP
    if user_ip:
        country, region, city = get_user_location(user_ip)

    # Sometimes location can't be determined
    if country == "Unknown":
        logger.warning(
            f"Not updating country stats for IP: {user_ip} - could not determine location"
        )
        return {
            "player_country": "Unknown",
            "player_region": "Unknown",
            "player_city": "Unknown",
        }

    # Now you can store it in your database
    uk = pytz.timezone("Europe/London")
    game_date = datetime.now(uk).date()

    # If player_uid provided, skip if already recorded for this player/date
    if player_uid:
        sql = f"SELECT 1 FROM {table_name('player_results')} WHERE game_date = %s AND player_uid = %s"
        existing = run_query(sql, (game_date, player_uid), fetchone=True)
        if existing:
            logger.info(
                f"Skipping world leaderboard update for already-recorded player {player_uid} on {game_date}"
            )
            return {
                "player_country": country,
                "player_region": region,
                "player_city": city,
            }

    # ----- Update country stats -----
    if country != "Unknown":
        logger.info(
            f"Updating country stats for user location: {country}, {region}, {city}"
        )
        sql = f"""
            INSERT INTO {table_name('country_stats')} (game_date, country, region, city, plays, successes, failures)
            VALUES (%s, %s, %s, %s, 1, %s, %s)
            ON CONFLICT(game_date, country, region, city)
            DO UPDATE SET 
                plays = {table_name('country_stats')}.plays + 1,
                successes = {table_name('country_stats')}.successes + EXCLUDED.successes,
                failures = {table_name('country_stats')}.failures + EXCLUDED.failures
        """
        run_query(sql, (
            game_date,
            country,
            region,
            city,
            1 if success else 0,
            0 if success else 1,
        ))

    return {"player_country": country, "player_region": region, "player_city": city}


# Load daily game state for a player
def load_daily_game_state(player_uid):
    today = date.today().isoformat()
    sql = f"""
        SELECT
            guess_history, 
            wrong_guesses, 
            guessed_main_country,
            game_over 
        FROM 
            {table_name('player_daily_state')} 
        WHERE 
            player_uid=%s AND game_date=%s
    """
    row = run_query(sql, (player_uid, today), fetchone=True)

    if row:
        resp = {
            "guess_history": json.loads(row[0]),
            "wrong_guesses": json.loads(row[1]),
            "guessed_main_country": bool(row[2]),
            "game_over": bool(row[3]),
        }
        return resp
    return None


# Save daily game state for a player
def save_daily_game_state(player_uid, game_over=False):
    today = date.today().isoformat()
    sql = f'''
        INSERT INTO {table_name('player_daily_state')} (
            player_uid, 
            game_date, 
            guess_history, 
            wrong_guesses,
            guessed_main_country,
            hard_mode,
            game_over,
            game_result_recorded
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(player_uid, game_date) DO UPDATE SET
            guess_history = %s,
            wrong_guesses = %s,
            game_over = %s
        '''
    params = (
        player_uid,
        today,
        json.dumps(session.get("guess_history", []) or []),
        json.dumps(session.get("wrong_guesses", []) or []),
        bool(session.get("guessed_main_country", False)),
        bool(session.get("hard_mode", False)),
        bool(game_over),
        bool(session.get("game_result_recorded", False)),
        json.dumps(session.get("guess_history", []) or []),
        json.dumps(session.get("wrong_guesses", []) or []),
        bool(game_over),
    )
    run_query(sql, params)
