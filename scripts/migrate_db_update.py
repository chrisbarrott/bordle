import sqlite3
import os


def _has_column(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _table_exists(cursor, table):
    cursor.execute("SELECT name FROM sqlite_master WHERE type=? AND name=?", ("table", table))
    return cursor.fetchone() is not None


def migrate_daily_games_with_rotation(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("Starting migration...")

        already_migrated = _table_exists(cursor, "daily_game") and _has_column(cursor, "daily_game", "rotation")

        if not already_migrated:
            # Step 1: Rename old table (only if daily_game_old doesn't already exist)
            if _table_exists(cursor, "daily_game_old"):
                print("daily_game_old already exists — skipping rename.")
            else:
                cursor.execute("ALTER TABLE daily_game RENAME TO daily_game_old;")
                print("Renamed existing table to daily_game_old.")

            # Step 2: Create new table with constraints
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_game (
                    game_date TEXT NOT NULL UNIQUE,
                    country TEXT NOT NULL,
                    rotation INTEGER NOT NULL,
                    UNIQUE(rotation, country)
                );
            """)
            print("Created new daily_game table with rotation column.")

            # Step 3: Migrate data, set rotation = 1
            cursor.execute("""
                INSERT OR IGNORE INTO daily_game (game_date, country, rotation)
                SELECT game_date, country, 1 FROM daily_game_old;
            """)
            print("Copied data into new table with rotation set to 1.")
        else:
            print("daily_game already has rotation column — skipping migration steps.")

        # Step 4: Drop old table if it still exists
        if _table_exists(cursor, "daily_game_old"):
            cursor.execute("DROP TABLE daily_game_old;")
            print("Dropped daily_game_old table.")

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
