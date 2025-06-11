# update_db.py
import os
import sqlite3

# Path to your SQLite database
# Set database paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')  # assumes this file is in services/
os.makedirs(DB_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_FOLDER, 'games.db')

# Data to insert
daily_game_data = [
    ('2025-06-03', 'South Korea'),
    ('2025-06-04', 'China'),
    ('2025-06-05', 'Suriname'),
    ('2025-06-06', 'Somalia'),
    ('2025-06-07', 'Cameroon'),
    ('2025-06-08', 'Ethiopia'),
    ('2025-06-09', 'United States of America'),
    ('2025-06-10', 'Kazakhstan'),
    ('2025-06-11', 'Morocco'),
]

game_stats_data = [
    ('2025-06-01', 1, 1),
    ('2025-06-03', 8, 0),
    ('2025-06-04', 8, 7),
    ('2025-06-05', 14, 4),
    ('2025-06-06', 7, 8),
    ('2025-06-07', 5, 6),
    ('2025-06-08', 7, 7),
    ('2025-06-09', 10, 2),
    ('2025-06-10', 5, 1),
    ('2025-06-11', 13, 14)
]


# Insert data
def update_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n=== Inserting daily_game data ===")
    for game_date, country in daily_game_data:
        cursor.execute('''
            INSERT OR REPLACE INTO daily_game (game_date, country)
            VALUES (?, ?)
        ''', (game_date, country))
        print(f"Inserted/Updated: {game_date} -> {country}")

    print("\n=== Inserting game_stats data ===")
    for game_date, successes, failures in game_stats_data:
        cursor.execute('''
            INSERT OR REPLACE INTO game_stats (game_date, successes, failures)
            VALUES (?, ?, ?)
        ''', (game_date, successes, failures))
        print(f"Inserted/Updated: {game_date} -> successes: {successes}, failures: {failures}")

    conn.commit()

    # Show final state of daily_game
    print("\n=== Final daily_game table ===")
    cursor.execute("SELECT * FROM daily_game ORDER BY game_date ASC")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

    # Show final state of game_stats
    print("\n=== Final game_stats table ===")
    cursor.execute("SELECT * FROM game_stats ORDER BY game_date ASC")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

    conn.close()
    print("\n✅ Database update complete.")

if __name__ == '__main__':
    update_database()