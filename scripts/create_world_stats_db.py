from services.game_database_connections import get_db_connection, init_db


def create_location_stats_table():
    init_db()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS country_stats (
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
    print("✅ location_stats table created or already exists.")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    if tables:
        print("📋 Tables in database:")
        for (name,) in tables:
            print(f" - {name}")
    else:
        print("⚠️ No tables found in database.")

    for (table_name,) in tables:
        print(f"\n🟢 Table: {table_name}")

        # Get columns for this table
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        if columns:
            for col in columns:
                # col is: (cid, name, type, notnull, dflt_value, pk)
                cid, name, col_type, notnull, default, pk = col
                nn = "NOT NULL" if notnull else ""
                pk_text = "PRIMARY KEY" if pk else ""
                default_text = f"DEFAULT {default}" if default is not None else ""
                print(f" - {name} ({col_type}) {nn} {pk_text} {default_text}".strip())
        else:
            print("   ⚠️ No columns found for this table.")

    # Fetch all columns from the country_stats table
    cursor.execute("""
        SELECT
            country,
            successes,
            failures,
            plays,
        FROM country_stats
    """)
    rows = cursor.fetchall()

    if not rows:
        print("No data found in the country_stats table.")
        return

if __name__ == "__main__":
    create_location_stats_table()