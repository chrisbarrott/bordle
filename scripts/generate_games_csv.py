import csv
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')
os.makedirs(DB_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_FOLDER, 'games.db')
OUTPUT_FILE = os.path.join(DB_FOLDER, 'games.csv')


def export_game_stats_to_csv(output_path: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM game_stats ORDER BY game_date")
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"⚠️ Failed: {e}")
        return
    finally:
        conn.close()

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)

    print(f"✅ Exported {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    export_game_stats_to_csv(OUTPUT_FILE)
