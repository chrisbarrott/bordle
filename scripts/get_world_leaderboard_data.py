from services.game_database_connections import get_db_connection, init_db


def get_world_stats():
    """Return all rows from the country_stats table as a list of dicts."""
    init_db()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            game_date,
            country,
            region,
            city,
            plays,
            successes,
            failures
        FROM country_stats
        ORDER BY game_date DESC
    """)

    # Fetch column names
    columns = [col[0] for col in cursor.description]

    # Build list of dicts manually
    results = [dict(zip(columns, row)) for row in cursor.fetchall()]

    conn.close()
    return results


def remove_unknown_entries():
    """Remove all entries from country_stats where country == 'Unknown'."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM country_stats WHERE country = 'Unknown'")
    conn.commit()
    conn.close()
    print("Removed all entries where country == 'Unknown'")


if __name__ == "__main__":
    stats = get_world_stats()
    for row in stats:
        print(row)
    remove_unknown_entries()
