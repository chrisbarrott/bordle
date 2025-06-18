import json
import os
import random
import sqlite3
import pytz

from datetime import date, datetime

from services.game_get_data import get_all_drop_down_options

# Set database paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')  # assumes this file is in services/
os.makedirs(DB_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_FOLDER, 'games.db')

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


def record_game_result(success: bool):
    # Get today's date in UK time
    uk = pytz.timezone('Europe/London')
    today = datetime.now(uk).date()

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


def get_today_country():
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
    print("Game Number:", result[0] if result else 0)
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
    cursor.execute("SELECT MAX(rotation) FROM daily_games")
    result = cursor.fetchone()[0]
    return result if result is not None else 0

def get_used_countries(cursor, rotation):
    cursor.execute("SELECT country FROM daily_games WHERE rotation = ?", (rotation,))
    return {row[0] for row in cursor.fetchall()}

def assign_today_country():
    conn = sqlite3.connect("db/games.db")
    cursor = conn.cursor()
    today = datetime.utcnow().date().isoformat()

    # Check if today's game is already assigned
    cursor.execute("SELECT country FROM daily_game WHERE game_date = ?", (today,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return row[0]

    all_countries = set(get_all_drop_down_options())
    current_rotation = get_current_rotation(cursor)
    used = get_used_countries(cursor, current_rotation)

    remaining = list(all_countries - used)
    if not remaining:
        # All countries used in this rotation, start new one
        current_rotation += 1
        used = set()
        remaining = list(all_countries)

    new_country = random.choice(remaining)

    cursor.execute(
        "INSERT INTO daily_games (game_date, country, rotation) VALUES (?, ?, ?)",
        (today, new_country, current_rotation)
    )
    conn.commit()
    conn.close()

    return new_country


def get_current_rotation(cursor):
    cursor.execute("SELECT MAX(rotation) FROM daily_game")
    result = cursor.fetchone()[0]
    return result if result is not None else 0


def get_used_countries(cursor, rotation):
    cursor.execute("SELECT country FROM daily_game WHERE rotation = ?", (rotation,))
    return {row[0] for row in cursor.fetchall()}


def assign_today_country():
    conn = get_db_connection()
    cursor = conn.cursor()
    today = datetime.utcnow().date().isoformat()

    # Check if today's game is already assigned
    cursor.execute("SELECT country FROM daily_games WHERE date = ?", (today,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return row[0]

    all_countries = set(get_all_drop_down_options())
    current_rotation = get_current_rotation(cursor)
    used = get_used_countries(cursor, current_rotation)

    remaining = list(all_countries - used)
    if not remaining:
        # All countries used in this rotation, start new one
        current_rotation += 1
        used = set()
        remaining = list(all_countries)

    new_country = random.choice(remaining)

    cursor.execute(
        "INSERT INTO daily_games (date, country, rotation) VALUES (?, ?, ?)",
        (today, new_country, current_rotation)
    )
    conn.commit()
    conn.close()

    return new_country
