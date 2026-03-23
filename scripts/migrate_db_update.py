import sqlite3
import os


def _table_exists(cursor, table_name):
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _get_table_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def _compute_rotations(rows):
    migrated_rows = []
    current_rotation = 1
    used_countries = set()

    for game_date, country in rows:
        if country in used_countries:
            current_rotation += 1
            used_countries = set()

        used_countries.add(country)
        migrated_rows.append((game_date, country, current_rotation))

    return migrated_rows


def _load_source_rows(cursor, table_name):
    columns = _get_table_columns(cursor, table_name)
    if "rotation" in columns:
        cursor.execute(
            f"SELECT game_date, country, rotation FROM {table_name} ORDER BY game_date ASC"
        )
        return cursor.fetchall()

    cursor.execute(f"SELECT game_date, country FROM {table_name} ORDER BY game_date ASC")
    return _compute_rotations(cursor.fetchall())


def migrate_daily_games_with_rotation(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("Starting migration...")

        source_table = None

        if _table_exists(cursor, "daily_game_old"):
            source_table = "daily_game_old"
            print("Found existing daily_game_old table from a previous migration attempt.")
        elif _table_exists(cursor, "daily_game"):
            columns = _get_table_columns(cursor, "daily_game")
            if "rotation" in columns:
                print("daily_game already has rotation column. Nothing to migrate.")
                conn.commit()
                return

            cursor.execute("ALTER TABLE daily_game RENAME TO daily_game_old;")
            source_table = "daily_game_old"
            print("Renamed existing table to daily_game_old.")
        else:
            raise RuntimeError("No daily_game source table found.")

        source_rows = _load_source_rows(cursor, source_table)
        if not source_rows:
            raise RuntimeError(f"No rows found in {source_table} to migrate.")

        cursor.execute("DROP TABLE IF EXISTS daily_game;")
        cursor.execute("""
            CREATE TABLE daily_game (
                game_date TEXT NOT NULL UNIQUE,
                country TEXT NOT NULL,
                rotation INTEGER NOT NULL,
                UNIQUE(rotation, country)
            );
        """)
        print("Created new daily_game table with rotation column.")

        cursor.executemany(
            """
            INSERT INTO daily_game (game_date, country, rotation)
            VALUES (?, ?, ?)
            """,
            source_rows,
        )
        print(f"Copied {len(source_rows)} rows into new daily_game table.")

        cursor.execute("DROP TABLE IF EXISTS daily_game_old;")
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
