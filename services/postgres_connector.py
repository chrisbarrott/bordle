from contextlib import contextmanager

import os
import json
from urllib.parse import urlparse
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import time
from services.game_logger import setup_logger

logger = setup_logger()

load_dotenv()


def _json_log(payload: dict) -> str:
    """Serialize log payloads safely (dates, decimals, etc.)."""
    return json.dumps(payload, default=str)


def _elapsed_seconds(start_time: float) -> float:
    return round(time.time() - start_time, 4)


def _log_event(level: str, event: str, **fields) -> None:
    payload = {"event": event, **fields, "timestamp": time.time()}
    log_message = _json_log(payload)
    if level == "error":
        logger.error(log_message)
    else:
        logger.info(log_message)


def _dsn_target(dsn: str) -> str:
    """Return a safe host:port target string for logging."""
    try:
        parsed = urlparse(dsn)
        host = parsed.hostname or "unknown"
        port = parsed.port or 5432
        return f"{host}:{port}"
    except Exception:
        return "unknown"

def _get_db_params():
    # Support a full DATABASE_URL or individual components
    flask_env = os.getenv("FLASK_ENV", "").lower()
    external_database_url = os.getenv("DATABASE_URL_EXTERNAL")
    if flask_env in ("local", "development") and external_database_url:
        return {"dsn": external_database_url}

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
    """Context manager that yields a new psycopg2 connection and closes it, with logging and timing."""
    params = _get_db_params()
    conn = None
    start_time = time.time()
    safe_params = {k: v for k, v in params.items() if k not in {"password", "dsn"}}
    if "dsn" in params:
        safe_params["target"] = _dsn_target(params["dsn"])
    _log_event("info", "postgres_connect_attempt", params=safe_params)
    try:
        if "dsn" in params:
            conn = psycopg2.connect(params["dsn"])
        else:
            conn = psycopg2.connect(**params)
        _log_event("info", "postgres_connect_success", duration=_elapsed_seconds(start_time))
    except Exception as e:
        _log_event(
            "error",
            "postgres_connect_failure",
            error=str(e),
            duration=_elapsed_seconds(start_time),
        )
        raise

    try:
        yield conn
    finally:
        if conn is not None:
            try:
                conn.close()
                _log_event("info", "postgres_connection_closed", duration=_elapsed_seconds(start_time))
            except Exception as e:
                _log_event("error", "postgres_connection_close_failure", error=str(e))


def fetch_one(query: str, params=None, log_errors: bool = True):
    """Execute a query and return a single row as a dict (or None), with logging and timing."""
    params = params or ()
    start_time = time.time()
    try:
        _log_event("info", "postgres_query_start", query=query, params=params)
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                row = cur.fetchone()
        _log_event(
            "info",
            "postgres_query_success",
            query=query,
            params=params,
            duration=_elapsed_seconds(start_time),
        )
        return row
    except Exception as e:
        if log_errors:
            _log_event(
                "error",
                "postgres_query_failure",
                query=query,
                params=params,
                error=str(e),
                duration=_elapsed_seconds(start_time),
            )
        raise


def fetch_value(query: str, params=None, log_errors: bool = True):
    """Return the first column of the first row, or None, with logging and timing."""
    start_time = time.time()
    try:
        row = fetch_one(query, params, log_errors=log_errors)
        if not row:
            _log_event(
                "info",
                "postgres_value_none",
                query=query,
                params=params,
                duration=_elapsed_seconds(start_time),
            )
            return None
        value = next(iter(row.values()))
        _log_event(
            "info",
            "postgres_value_success",
            query=query,
            params=params,
            value=value,
            duration=_elapsed_seconds(start_time),
        )
        return value
    except Exception as e:
        if log_errors:
            _log_event(
                "error",
                "postgres_value_failure",
                query=query,
                params=params,
                error=str(e),
                duration=_elapsed_seconds(start_time),
            )
        raise
