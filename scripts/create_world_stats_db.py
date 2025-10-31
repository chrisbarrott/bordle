from services.game_database_connections import get_db_connection, init_db


def create_location_stats_table():
    init_db()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS location_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_date TEXT NOT NULL,
        country TEXT,
        region TEXT,
        city TEXT,
        plays INTEGER DEFAULT 0,
        successes INTEGER DEFAULT 0,
        failures INTEGER DEFAULT 0,
        UNIQUE (game_date, country, region, city)
    );
    """)

    conn.commit()
    conn.close()
    print("✅ location_stats table created or already exists.")


if __name__ == "__main__":
    create_location_stats_table()