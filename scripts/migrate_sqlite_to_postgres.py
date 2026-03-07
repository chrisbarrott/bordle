import os
import sqlite3
import re

try:
    import psycopg2
except ImportError:
    psycopg2 = None


def map_sqlite_type(sql_type: str) -> str:
    # very basic mapping; extend as needed
    sql_type = sql_type.upper()
    if "INT" in sql_type:
        return "INTEGER"
    if "CHAR" in sql_type or "CLOB" in sql_type or "TEXT" in sql_type:
        return "TEXT"
    if "BLOB" in sql_type:
        return "BYTEA"
    if "REAL" in sql_type or "FLOA" in sql_type or "DOUB" in sql_type:
        return "DOUBLE PRECISION"
    if "DATE" in sql_type:
        return "DATE"
    return sql_type


def migrate():
    if psycopg2 is None:
        print("psycopg2 is not installed. Install psycopg2-binary to use this script.")
        return

    sqlite_path = os.path.join(os.path.dirname(__file__), "..", "db", "games.db")
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"SQLite database not found at {sqlite_path}")

    dsn = os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Postgres DSN not configured. Set POSTGRES_DSN or DATABASE_URL.")

    env = os.getenv("FLASK_ENV", "development")

    print(f"Opening SQLite database at {sqlite_path}")
    s_conn = sqlite3.connect(sqlite_path)
    s_conn.row_factory = sqlite3.Row
    s_cur = s_conn.cursor()

    print("Connecting to Postgres")
    p_conn = psycopg2.connect(dsn)
    p_cur = p_conn.cursor()

    # grab all user tables
    s_cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = s_cur.fetchall()
    for name, create_sql in tables:
        target = f"{env}_{name}"
        print(f"Migrating table {name} -> {target}")
        # crudely modify create_sql to refer to target table and map types
        # remove AUTOINCREMENT, replace """
        create_sql_clean = re.sub(r"AUTOINCREMENT", "", create_sql, flags=re.IGNORECASE)
        create_sql_clean = create_sql_clean.replace(name, target)
        # naive column type mapping
        def repl_type(match):
            colname = match.group(1)
            coltype = map_sqlite_type(match.group(2))
            return f"{colname} {coltype}"
        create_sql_clean = re.sub(r"(\w+)\s+(\w+)", repl_type, create_sql_clean)

        try:
            p_cur.execute(create_sql_clean)
            p_conn.commit()
        except Exception as e:
            print(f"Could not create table {target}: {e}")

        # copy rows
        s_cur.execute(f"SELECT * FROM {name}")
        rows = s_cur.fetchall()
        if rows:
            cols = [description[0] for description in s_cur.description]
            placeholders = ",".join(["%s"] * len(cols))
            insert_sql = f"INSERT INTO {target} ({','.join(cols)}) VALUES ({placeholders})"
            for r in rows:
                try:
                    p_cur.execute(insert_sql, tuple(r))
                except Exception as e:
                    print(f"Error inserting row into {target}: {e}")
            p_conn.commit()
            print(f"Copied {len(rows)} rows to {target}")
        else:
            print(f"No data to copy for {name}")

    s_conn.close()
    p_conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
