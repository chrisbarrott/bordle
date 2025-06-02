import json
import os
import random
import sqlite3
import pytz

from datetime import datetime

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
