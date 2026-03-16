from contextlib import contextmanager
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

def _get_db_params():
    # Support a full DATABASE_URL or individual components
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return {"dsn": database_url}

    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", 5432)),
        "dbname": os.getenv("POSTGRES_DB", "bordle"),
        "user": os.getenv("POSTGRES_USER", ""),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


@contextmanager
def get_connection():
    """Context manager that yields a new psycopg2 connection and closes it.

    Usage:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    """
    params = _get_db_params()
    conn = None
    try:
        if "dsn" in params:
            conn = psycopg2.connect(params["dsn"])
        else:
            conn = psycopg2.connect(**params)
        yield conn
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def fetch_one(query: str, params=None):
    """Execute a query and return a single row as a dict (or None)."""
    params = params or ()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchone()


def fetch_value(query: str, params=None):
    """Return the first column of the first row, or None."""
    row = fetch_one(query, params)
    if not row:
        return None
    # RealDictCursor returns a dict — take the first value
    return next(iter(row.values()))
