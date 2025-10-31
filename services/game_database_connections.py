import json
import os
import random
import sqlite3
import pytz

from datetime import date, datetime

from services.game_get_data import get_all_drop_down_options, get_user_ip, get_user_location
from services.game_observe import send_to_observe

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


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_stats (
            game_date DATE PRIMARY KEY,
            successes INTEGER DEFAULT 0,
            failures INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_game (
            game_date DATE PRIMARY KEY,
            country TEXT
        )
    ''')

    conn.commit()
    conn.close()


def record_game_result(success: bool, remaining_countries: str):
    # Get today's date in UK time
    uk = pytz.timezone('Europe/London')
    today = datetime.now(uk).date()
    now = datetime.now(uk)

    # Set database environment
    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert or update
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

    # Send enriched payload to Observe
    payload = {
        "timestamp": now.isoformat(),
        "game_date": str(today),
        "result": "success" if success else "failure",
        "environment": ENVIRONMENT,
        "country_name": get_today_country(),
        "game_number": get_game_number(),
        "games_today": get_games_today()[0],
        "total_games": get_total_games(),
        "remaining_guesses": remaining_countries
    }
    send_to_observe(payload)


def get_today_country_old():
    # Get current date in UK time
    uk = pytz.timezone('Europe/London')
    today = datetime.now(uk).date()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE IF NOT EXISTS daily_game (game_date DATE PRIMARY KEY, country TEXT)")

    cursor.execute("SELECT country FROM daily_game WHERE game_date = ?", (today,))
    row = cursor.fetchone()

    if row:
        country = row[0]
    else:
        all_countries = set(border_map.keys())
        country = random.choice(list(all_countries))
        cursor.execute("INSERT INTO daily_game (game_date, country) VALUES (?, ?)", (today, country))
        conn.commit()

    conn.close()
    return country


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
    print(f"Borderable countries: {len(borderable_countries)}")

    # check the rotation
    current_rotation = get_current_rotation(cursor)

    # ensure its not been used
    used = get_used_countries(cursor, current_rotation)

    remaining = list(borderable_countries - used)
    print(f"Games remaining : {len(remaining)}")

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

    return new_country


def get_leaderboard_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Today's stats
    cursor.execute("""
        SELECT country,
            successes,
            failures,
            plays
        FROM country_stats
            WHERE game_date = DATE('now', 'localtime')
        GROUP BY country
        HAVING total_guesses > 0
        ORDER BY successes DESC
        LIMIT 5
    """)
    daily = cursor.fetchall()

    # All-time stats
    cursor.execute("""
        SELECT country,
            successes,
            failures,
            plays
        FROM country_stats
        WHERE plays > 0
        ORDER BY successes DESC
        LIMIT 5
    """)
    all_time = cursor.fetchall()

    conn.close()

    def format_data(rows):
        return [
            {
                "country": r["country"],
                "success_rate": (r["successes"] / r["total_guesses"]) * 100 if r["total_guesses"] else 0,
                "total_guesses": r["total_guesses"]
            }
            for r in rows
        ]

    return {
        "daily": format_data(daily),
        "all_time": format_data(all_time)
    }


def record_world_leaderboard_result(success: bool):
    user_ip = get_user_ip()  # Flask: get user's IP
    country, region, city = get_user_location(user_ip)
    print(f"User Location: Country={country}, Region={region}, City={city}")

    # Now you can store it in your database
    uk = pytz.timezone('Europe/London')
    game_date = datetime.now(uk).date()

    # Lookup user location
    location = get_user_location(user_ip)
    country = location.get("country", "Unknown")
    print(f"Recording leaderboard result for country: {country}")

    """Update daily country stats for the leaderboard."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Make sure entry exists for today
    cursor.execute("""
        SELECT plays, successes, failures
        FROM country_stats
        WHERE game_date = ? AND country = ? AND region = ? AND city = ?
    """, (game_date, country, region, city))
    existing = cursor.fetchone()

    if existing:
        plays, successes, failures = existing
        plays += 1
        if success:
            successes += 1
        else:
            failures += 1
        cursor.execute("""
            UPDATE country_stats
            SET plays = ?, successes = ?, failures = ?
            WHERE game_date = ? AND country = ? AND region = ? AND city = ?
        """, (plays, successes, failures, game_date, country, region, city))
    else:
        cursor.execute("""
            INSERT INTO country_stats (game_date, country, region, city, plays, successes, failures)
            VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (game_date, country, region, city, 1 if success else 0, 0 if success else 1))

    conn.commit()
    conn.close()
