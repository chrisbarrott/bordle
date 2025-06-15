import sqlite3
import os

# Set database paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')  # assumes this file is in services/
os.makedirs(DB_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_FOLDER, 'games.db')


def get_all_daily_games():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM daily_game ORDER BY game_date DESC")
    rows = cursor.fetchall()

    # Get column names
    column_names = [description[0] for description in cursor.description]

    cursor.execute("SELECT COUNT(DISTINCT game_date) FROM daily_game")
    result = cursor.fetchone()
    print("game number: ", result[0] if result else 0)

    conn.close()

    # Print header
    print("\t".join(column_names))
    print("-" * 40)

    # Print rows
    for row in rows:
        print("\t".join(str(item) for item in row))



if __name__ == "__main__":
    get_all_daily_games()
