import sqlite3
import os


def migrate_daily_games_with_rotation(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("Starting migration...")

        # # Step 1: Rename old table
        cursor.execute("ALTER TABLE daily_game RENAME TO daily_game_old;")
        print("Renamed existing table to daily_game_old.")

        # Step 2: Create new table with constraints
        cursor.execute("""
            CREATE TABLE daily_game (
                game_date TEXT NOT NULL UNIQUE,
                country TEXT NOT NULL,
                rotation INTEGER NOT NULL,
                UNIQUE(rotation, country)
            );
        """)
        print("Created new daily_game table with rotation column.")

        # Step 3: Migrate data, set rotation = 1
        cursor.execute("""
            INSERT INTO daily_game (game_date, country, rotation)
            SELECT game_date, country, 1 FROM daily_game_old;
        """)
        print("Copied data into new table with rotation set to 1.")

        # Step 4: Drop old table
        cursor.execute("DROP TABLE daily_game_old;")
        print("Dropped old daily_game_old table.")

        conn.commit()
        print("Migration complete ✅")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed ❌: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = os.path.join("db", "games.db")  # Adjust path if needed
    migrate_daily_games_with_rotation(db_path)
