import os

try:
    import psycopg2
except ImportError:
    psycopg2 = None


def validate():
    """Connect to Postgres and print some basic information."""
    if psycopg2 is None:
        print("psycopg2 is not installed. Please install psycopg2-binary first.")
        return

    dsn = os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        print("No Postgres DSN found in POSTGRES_DSN or DATABASE_URL environment variables.")
        return

    print(f"Connecting to Postgres using DSN: {dsn}")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    print(f"Postgres version: {version}")

    cur.execute("SELECT NOW();")
    now = cur.fetchone()[0]
    print(f"Server time: {now}")

    # list tables in public schema
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public';")
    tables = [t[0] for t in cur.fetchall()]
    print(f"Tables in public schema ({len(tables)}): {tables}")

    # try query environment-specific stats table if it exists
    env = os.getenv("FLASK_ENV", "development")
    sample_table = f"{env}_player_stats"
    if sample_table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {sample_table};")
            count = cur.fetchone()[0]
            print(f"{sample_table} row count: {count}")
        except Exception as e:
            print(f"Unable to query {sample_table}: {e}")

    conn.close()


if __name__ == "__main__":
    validate()
