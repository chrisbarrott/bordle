import os
import sqlite3

from services.game_database_connections import export_table_to_csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')  # assumes this file is in services/
os.makedirs(DB_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_FOLDER, 'games.db')
OUTPUT_FILE = os.path.join(DB_FOLDER, 'games.csv')


def main():
    try:
        export_table_to_csv(OUTPUT_FILE)
    except sqlite3.OperationalError as e:
        print(f"⚠️ Failed {e}")


if __name__ == "__main__":
    main()
