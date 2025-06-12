import sqlite3
import csv
import os

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')
DB_PATH = os.path.join(DB_FOLDER, 'games.db')
CSV_PATH = os.path.join(DB_FOLDER, 'games.csv')

# Connect to DB
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Ensure tables exist (optional: create if missing)
cursor.execute('''
CREATE TABLE IF NOT EXISTS daily_game (
    game_date TEXT PRIMARY KEY,
    country_name TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS game_stats (
    game_date TEXT PRIMARY KEY,
    games_played INTEGER,
    wins INTEGER,
    losses INTEGER,
    FOREIGN KEY(game_date) REFERENCES daily_game(game_date)
)
''')

# Read and import CSV
with open(CSV_PATH, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        game_date = row["game_date"]
        country_name = row["country"]
        successes = int(row["successes"])
        failures = int(row["failures"])

        # Upsert into daily_games
        cursor.execute("""
            INSERT INTO daily_games (game_date, country)
            VALUES (?, ?)
            ON CONFLICT(game_date) DO UPDATE SET country=excluded.country
        """, (game_date, country_name))

        # Upsert into game_stats
        cursor.execute("""
            INSERT INTO game_stats (game_date, games_played, successes, failures)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(game_date) DO UPDATE SET
                successes=excluded.successes,
                failures=excluded.failures
        """, (game_date, successes, failures))

# Finalize
conn.commit()
conn.close()
print("✅ Database updated from CSV.")
