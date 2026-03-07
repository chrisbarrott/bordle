import json
import os
import random
import sqlite3
from flask import session
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

# Load GeoJSON shapes once
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)


def get_db_connection():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_FOLDER = os.path.join(BASE_DIR, "..", "db")  # assumes this file is in services/
    os.makedirs(DB_FOLDER, exist_ok=True)
    DB_PATH = os.path.join(DB_FOLDER, "games.db")
    return sqlite3.connect(DB_PATH)


def cleanup_old_player_results():
    """Remove player_results entries older than 30 days."""
    uk = pytz.timezone("Europe/London")
    today = datetime.now(uk).date()
    cutoff_date = today - __import__("datetime").timedelta(days=30)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM player_results WHERE game_date < ?", (cutoff_date,))

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted_count > 0:
        logger.info(
            f"Cleaned up {deleted_count} old player result records (before {cutoff_date})"
        )


def cleanup_old_daily_games(days: int = 30):
    """
    Deletes in-progress daily game state older than N days.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM player_daily_state
        WHERE game_date < date('now', ?)
        """,
        (f"-{days} days",)
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    logger.info(f"Cleanup: deleted {deleted} player_daily_state rows older than {days} days")


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create country stats table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_stats (
            game_date DATE PRIMARY KEY,
            successes INTEGER DEFAULT 0,
            failures INTEGER DEFAULT 0
        )
    """)

    # Create daily country stats table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_game (
            game_date DATE PRIMARY KEY,
            country TEXT
        )
    """)

    # Create table to ensure player states are recorded only once per day
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_results (
            game_number INTEGER,
            game_date DATE,
            player_uid TEXT,
            PRIMARY KEY (game_date, game_number, player_uid)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_daily_state (
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
    """)

    # Per-player aggregated stats (migration target for client-side stats)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_stats (
            player_uid TEXT PRIMARY KEY,
            games_played INTEGER DEFAULT 0,
            games_won INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0,
            migrated INTEGER DEFAULT 0,
            last_updated DATE
        )
    """)

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

    conn = get_db_connection()
    cursor = conn.cursor()

    # ----- Function to record the player session result -----

    # If a player_uid is provided, ensure we only count once per player per day
    if player_uid:
        # Find is player already recorded for today
        cursor.execute(
            "SELECT 1 FROM player_results WHERE game_date = ? AND player_uid = ?",
            (today, player_uid),
        )

        # If already recorded, skip
        if cursor.fetchone():
            logger.info(
                f"Skipping duplicate game result for player {player_uid} on {today}"
            )
            conn.close()
            return

        # mark player as recorded
        cursor.execute(
            "INSERT INTO player_results (game_date, game_number, player_uid) VALUES (?, ?, ?)",
            (today, game_number, player_uid),
        )

    # ----- Update daily aggregated stats -----

    # Insert or update aggregated daily stats
    if success:
        cursor.execute(
            """
            INSERT INTO game_stats (game_date, successes, failures)
            VALUES (?, 1, 0)
            ON CONFLICT(game_date) DO UPDATE SET successes = successes + 1
        """,
            (today,),
        )
    else:
        cursor.execute(
            """
            INSERT INTO game_stats (game_date, successes, failures)
            VALUES (?, 0, 1)
            ON CONFLICT(game_date) DO UPDATE SET failures = failures + 1
        """,
            (today,),
        )

    conn.commit()
    conn.close()


def get_player_stats(player_uid: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT games_played, games_won, current_streak, best_streak, migrated FROM player_stats WHERE player_uid = ?",
        (player_uid,)
    )
    row = cursor.fetchone()
    conn.close()

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

    conn = get_db_connection()
    cursor = conn.cursor()

    if existing and existing.get("migrated"):
        logger.warning(f"[MIGRATION] Player {player_uid} already migrated. Skipping to prevent double-count.")
        conn.close()
        return {"status": "skipped", "reason": "already_migrated"}

    # Prepare merge values
    games_played = int(stats.get("gamesPlayed", 0))
    games_won = int(stats.get("gamesWon", 0))
    current_streak = int(stats.get("currentStreak", 0))
    best_streak = int(stats.get("bestStreak", current_streak))

    logger.info(f"[MIGRATION] Parsed client stats: played={games_played}, won={games_won}, streak={current_streak}, best={best_streak}")

    if existing:
        # Simple merge: take maxima for streaks, sum totals
        merged_played = (existing.get("games_played", 0) or 0) + games_played
        merged_won = (existing.get("games_won", 0) or 0) + games_won
        merged_current_streak = max(existing.get("current_streak", 0) or 0, current_streak)
        merged_best_streak = max(existing.get("best_streak", 0) or 0, best_streak)

        logger.info(f"[MIGRATION] Merging existing and client stats: played {existing.get('games_played')} + {games_played} = {merged_played}, won {existing.get('games_won')} + {games_won} = {merged_won}")

        cursor.execute(
            """
            UPDATE player_stats SET
                games_played = ?,
                games_won = ?,
                current_streak = ?,
                best_streak = ?,
                migrated = 1,
                last_updated = date('now', 'localtime')
            WHERE player_uid = ?
            """,
            (
                merged_played,
                merged_won,
                merged_current_streak,
                merged_best_streak,
                player_uid,
            ),
        )
        logger.info(f"[MIGRATION] Updated existing player stats: {player_uid}")
    else:
        logger.info(f"[MIGRATION] No existing stats found. Creating new record for {player_uid}")
        cursor.execute(
            """
            INSERT INTO player_stats (
                player_uid, games_played, games_won, current_streak, best_streak, migrated, last_updated
            ) VALUES (?, ?, ?, ?, ?, 1, date('now', 'localtime'))
            """,
            (player_uid, games_played, games_won, current_streak, best_streak),
        )
        logger.info(f"[MIGRATION] Inserted new player stats: {player_uid}")

    conn.commit()
    conn.close()

    logger.info(f"[MIGRATION] ✅ Migration complete for player {player_uid}")
    return {"status": "ok"}


def get_game_number():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT game_date) FROM daily_game")
    result = cur.fetchone()
    conn.close()
    # print("Game Number:", result[0] if result else 0)
    return result[0] if result else 0


def get_games_today():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COALESCE(successes,0), COALESCE(failures,0)
        FROM game_stats
        WHERE game_date = ?
    """,
        (date.today().isoformat(),),
    )

    row = cursor.fetchone()
    conn.close()

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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT SUM(successes + failures) AS total_games
        FROM game_stats
    """)

    row = cursor.fetchone()
    conn.close()

    total_games = row[0] if row and row[0] is not None else 0

    return total_games


def get_current_rotation(cursor):
    cursor.execute("SELECT MAX(rotation) FROM daily_game")
    result = cursor.fetchone()[0]
    return result if result is not None else 0


def get_used_countries(cursor, rotation):
    cursor.execute("SELECT country FROM daily_game WHERE rotation = ?", (rotation,))
    return {row[0] for row in cursor.fetchall()}


def get_today_country():
    conn = get_db_connection()
    cursor = conn.cursor()
    today = date.today().isoformat()

    # Check if today's game is already assigned
    cursor.execute("SELECT country FROM daily_game WHERE game_date = ?", (today,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return row[0]

    # get all the counntries from the drop down json and compare it against the countries json
    all_countries = set(get_all_drop_down_options())
    borderable_countries = {
        country for country in all_countries if country in border_map
    }
    # print(f"Borderable countries: {len(borderable_countries)}")

    # check the rotation
    current_rotation = get_current_rotation(cursor)

    # ensure its not been used
    used = get_used_countries(cursor, current_rotation)

    remaining = list(borderable_countries - used)
    # print(f"Games remaining : {len(remaining)}")

    if not remaining:
        # All valid countries used in this rotation
        current_rotation += 1
        used = set()
        remaining = list(borderable_countries)

    new_country = random.choice(remaining)

    cursor.execute(
        "INSERT INTO daily_game (game_date, country, rotation) VALUES (?, ?, ?)",
        (today, new_country, current_rotation),
    )
    conn.commit()
    conn.close()

    logger.info(f"Assigned new daily country: {new_country} for date: {today}")

    return new_country


def get_leaderboard_data():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row  # ✅ Ensures we can use r["country"]

    cursor = conn.cursor()

    # ✅ Daily stats (for today)
    cursor.execute("""
        SELECT
            country,
            SUM(successes) AS total_successes,
            SUM(failures) AS total_failures,
            SUM(plays) AS total_plays,
            CASE
                WHEN (SUM(successes) + SUM(failures)) = 0 THEN 0
                ELSE (CAST(SUM(successes) AS FLOAT) * 100.0 / (SUM(successes) + SUM(failures)))
            END AS success_rate
        FROM country_stats
        WHERE game_date = DATE('now', 'localtime')
        GROUP BY country
        HAVING total_plays > 0
        ORDER BY success_rate DESC, total_plays DESC
        LIMIT 20;
    """)
    daily = cursor.fetchall()

    # ✅ All-time stats
    cursor.execute("""
        SELECT
            country,
            SUM(successes) AS total_successes,
            SUM(failures) AS total_failures,
            SUM(plays) AS total_plays,
            CASE
                WHEN (SUM(successes) + SUM(failures)) = 0 THEN 0
                ELSE (CAST(SUM(successes) AS FLOAT) * 100.0 / (SUM(successes) + SUM(failures)))
            END AS success_rate
        FROM country_stats
        GROUP BY country
        HAVING total_plays > 0
        ORDER BY success_rate DESC, total_plays DESC
        LIMIT 100;
    """)
    all_time = cursor.fetchall()

    conn.close()

    # ✅ Convert SQLite rows to JSON-safe dicts
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

    # Lookup user location
    conn = get_db_connection()
    cursor = conn.cursor()

    # If player_uid provided, skip if already recorded for this player/date
    if player_uid:
        cursor.execute(
            "SELECT 1 FROM player_results WHERE game_date = ? AND player_uid = ?",
            (game_date, player_uid),
        )

        # If already recorded, skip
        if cursor.fetchone():
            logger.info(
                f"Skipping world leaderboard update for already-recorded player {player_uid} on {game_date}"
            )
            conn.close()

            # Default return values
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

        # Update or insert record for today + location
        cursor.execute(
            """
            INSERT INTO country_stats (game_date, country, region, city, plays, successes, failures)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(game_date, country, region, city)
            DO UPDATE SET 
                plays = plays + 1,
                successes = successes + excluded.successes,
                failures = failures + excluded.failures
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

        conn.commit()
        conn.close()

    return {"player_country": country, "player_region": region, "player_city": city}


# Load daily game state for a player
def load_daily_game_state(player_uid):
    today = date.today().isoformat()

    # Lookup user location
    conn = get_db_connection()
    cursor = conn.cursor()

    row = cursor.execute("""
        SELECT
            guess_history, 
            wrong_guesses, 
            guessed_main_country,
            game_over 
        FROM 
            player_daily_state 
        WHERE 
            player_uid=? AND game_date=?
        """,
        (player_uid, today))
    
    row = cursor.fetchone()
    conn.close()

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

    # Lookup user location
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO player_daily_state (
            player_uid, 
            game_date, 
            guess_history, 
            wrong_guesses,
            guessed_main_country,
            hard_mode,
            game_over,
            game_result_recorded
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(player_uid, game_date) DO UPDATE SET
            guess_history = ?,
            wrong_guesses = ?,
            game_over = ?
        ''',
        (
            player_uid,
            today,
            json.dumps(session["guess_history"] or []),
            json.dumps(session["wrong_guesses"] or []), 
            bool(session["guessed_main_country"]),
            bool(session.get("hard_mode", False)),
            bool(game_over),
            bool(session.get("game_result_recorded", False)),
            json.dumps(session["guess_history"] or []),
            json.dumps(session["wrong_guesses"] or []),
            bool(game_over)
        )
    )

    conn.commit()
    conn.close()
