import sqlite3
import os

def remove_latest_game(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Get the latest date in the table
        cursor.execute("SELECT game_date, country FROM daily_game ORDER BY game_date DESC LIMIT 1;")
        row = cursor.fetchone()

        if not row:
            print("No rows found in daily_game")
            return

        latest_date, country = row
        print(f"Deleting: {country} on {latest_date}")

        # Delete the row
        cursor.execute("DELETE FROM daily_game WHERE game_date = ?", (latest_date,))
        conn.commit()
        print("✅ Latest game removed successfully.")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error: {e}")

    finally:
        conn.close()


if __name__ == "__main__":
    db_path = os.path.join("db", "games.db")  # adjust if needed
    remove_latest_game(db_path)
