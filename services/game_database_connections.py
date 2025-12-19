import json
import os
import random
import sqlite3
import pytz

from datetime import date, datetime

from services.game_get_data import get_all_drop_down_options, get_user_ip, get_user_location
from services.game_logger import setup_logger

# Setup logger
logger = setup_logger()

# Set database paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')  # assumes this file is in services/
os.makedirs(DB_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_FOLDER, 'games.db')
ENVIRONMENT = os.getenv("FLASK_ENV", "development")  # default if not set

# Load GeoJSON shapes once
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)


def get_db_connection():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')  # assumes this file is in services/
    os.makedirs(DB_FOLDER, exist_ok=True)
    DB_PATH = os.path.join(DB_FOLDER, 'games.db')
    return sqlite3.connect(DB_PATH)


def cleanup_old_player_results():
    """Remove player_results entries older than 7 days."""
    uk = pytz.timezone('Europe/London')
    today = datetime.now(uk).date()
    cutoff_date = today - __import__('datetime').timedelta(days=7)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "DELETE FROM player_results WHERE game_date < ?",
        (cutoff_date,)
    )
    
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    
    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} old player result records (before {cutoff_date})")


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create country stats table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_stats (
            game_date DATE PRIMARY KEY,
            successes INTEGER DEFAULT 0,
            failures INTEGER DEFAULT 0
        )
    ''')

    # Create daily country stats table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_game (
            game_date DATE PRIMARY KEY,
            country TEXT
        )
    ''')

    # Create table to ensure player states are recorded only once per day
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_results (
            game_number INTEGER,
            game_date DATE,
            player_result TEXT,
            player_uid TEXT,
            PRIMARY KEY (game_date, game_number, player_uid)
        )
    ''')

    conn.commit()
    conn.close()
    
    # Clean up old records
    cleanup_old_player_results()


def record_game_result(success: bool, remaining_countries: str, player_uid: str = None):
    # Get today's date in UK time
    uk = pytz.timezone('Europe/London')
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
            logger.info(f"Skipping duplicate game result for player {player_uid} on {today}")
            conn.close()
            return
        
        # mark player as recorded
        cursor.execute(
            "INSERT INTO player_results (game_date, game_number, player_result, player_uid) VALUES (?, ?, ?)",
            (today, game_number, success, player_uid),
        )

    # ----- Update daily aggregated stats -----

    # Insert or update aggregated daily stats
    if success:
        cursor.execute('''
            INSERT INTO game_stats (game_date, successes, failures)
            VALUES (?, 1, 0)
            ON CONFLICT(game_date) DO UPDATE SET successes = successes + 1
        ''', (today,))
    else:
        cursor.execute('''
            INSERT INTO game_stats (game_date, successes, failures)
            VALUES (?, 0, 1)
            ON CONFLICT(game_date) DO UPDATE SET failures = failures + 1
        ''', (today,))

    conn.commit()
    conn.close()


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
    cursor.execute("""
        SELECT COALESCE(successes,0), COALESCE(failures,0)
        FROM game_stats
        WHERE game_date = ?
    """, (date.today().isoformat(),))

    row = cursor.fetchone()
    conn.close()

    if row:
        successes_today, failures_today = row
        games_today = successes_today + failures_today
        success_rate_today = round((successes_today / games_today) * 100) if games_today > 0 else 0
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
    borderable_countries = {country for country in all_countries if country in border_map}
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
        (today, new_country, current_rotation)
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
        LIMIT 50;
    """)
    all_time = cursor.fetchall()

    conn.close()

    # ✅ Convert SQLite rows to JSON-safe dicts
    def format_data(rows):
        return [
            {
                "country": r["country"],
                "success_rate": round(r["success_rate"], 1),
                "total_guesses": int(r["total_plays"])
            }
            for r in rows
        ]

    return {
        "daily": format_data(daily),
        "all_time": format_data(all_time)
    }


def record_world_leaderboard_result(success: bool, player_uid: str = None):
    user_ip = get_user_ip()  # Flask: get user's IP
    country, region, city = get_user_location(user_ip)

    # Now you can store it in your database
    uk = pytz.timezone('Europe/London')
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
        if cursor.fetchone():
            logger.info(f"Skipping world leaderboard update for already-recorded player {player_uid} on {game_date}")
            conn.close()
            return {"player_country": "Unknown", "player_region": "Unknown", "player_city": "Unknown"}

    # Default values
    country, region, city = "Unknown", "Unknown", "Unknown"

    # If user IP available, get location
    if user_ip:
        country, region, city = get_user_location(user_ip)

    # Sometimes location can't be determined
    if country == "Unknown":
        logger.warning(f"Not updating country stats for IP: {user_ip} - could not determine location")

    else:
        logger.info(f"Updating country stats for user location: {country}, {region}, {city}")
        # Update or insert record for today + location
        cursor.execute('''
            INSERT INTO country_stats (game_date, country, region, city, plays, successes, failures)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(game_date, country, region, city)
            DO UPDATE SET 
                plays = plays + 1,
                successes = successes + excluded.successes,
                failures = failures + excluded.failures
        ''', (game_date, country, region, city, 1 if success else 0, 0 if success else 1))

        conn.commit()
        conn.close()

    return {
        "player_country": country,
        "player_region": region,
        "player_city": city
    }
