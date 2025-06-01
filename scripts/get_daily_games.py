import sqlite3
import os
from datetime import datetime

# Set database paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')  # assumes this file is in services/
os.makedirs(DB_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_FOLDER, 'games.db')


def get_all_daily_games():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT date, country FROM daily_game ORDER BY date DESC"
    cursor.execute(query)
    results = cursor.fetchall()
    print(results)

    conn.close()

    return results


def main():
    games = get_all_daily_games()
    if not games:
        print("No daily games found in the database.")
        return

    print("Date\t\tCountry")
    print("-" * 30)
    for date, country in games:
        print(f"{date}\t{country}")


if __name__ == "__main__":
    main()
