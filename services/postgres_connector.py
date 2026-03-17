from contextlib import contextmanager

import os
import json
from urllib.parse import urlparse
from dotenv import load_dotenv
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
import time
from services.game_logger import setup_logger

logger = setup_logger()

load_dotenv()

_connection_pool = None
_pool_params_key = None


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


def _sanitize_db_params(params: dict) -> dict:
    safe_params = {k: v for k, v in params.items() if k not in {"password", "dsn"}}
    if "dsn" in params:
        safe_params["target"] = _dsn_target(params["dsn"])
    return safe_params


def _db_params_key(params: dict):
    return tuple(sorted(params.items()))


def _is_local_env() -> bool:
    return os.getenv("FLASK_ENV", "").strip().lower() == "local"


def _get_db_params():
    # Support a full DATABASE_URL or individual components
    local_database_url = os.getenv("DATABASE_URL_LOCAL") or os.getenv("POSTGRES_LOCAL_URL")
    pgbouncer_database_url = os.getenv("DATABASE_URL_PGBOUNCER") or os.getenv("RENDER_PGBOUNCER_URL")
    external_database_url = os.getenv("DATABASE_URL_EXTERNAL")
    database_url = os.getenv("DATABASE_URL")

    if _is_local_env():
        if local_database_url:
            return {"dsn": local_database_url}
        if pgbouncer_database_url:
            return {"dsn": pgbouncer_database_url}
        if external_database_url:
            return {"dsn": external_database_url}
        if database_url:
            return {"dsn": database_url}

    if pgbouncer_database_url:
        return {"dsn": pgbouncer_database_url}

    if external_database_url:
        return {"dsn": external_database_url}

    if database_url:
        return {"dsn": database_url}

    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", 5432)),
        "dbname": os.getenv("POSTGRES_DB", "bordle"),
        "user": os.getenv("POSTGRES_USER", ""),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


def _is_write_query(query: str) -> bool:
    normalized_query = (query or "").lstrip().upper()
    if normalized_query.startswith("WITH"):
        return any(token in normalized_query for token in ("INSERT ", "UPDATE ", "DELETE "))

    first_token = normalized_query.split(None, 1)
    if not first_token:
        return False
    return first_token[0] in {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE"}


def _get_or_create_pool():
    global _connection_pool, _pool_params_key

    params = _get_db_params()
    params_key = _db_params_key(params)
    if _connection_pool is not None and _pool_params_key == params_key:
        return _connection_pool, params

    if _connection_pool is not None:
        try:
            _connection_pool.closeall()
            _log_event("info", "postgres_pool_reset")
        except Exception as e:
            _log_event("error", "postgres_pool_reset_failure", error=str(e))

    start_time = time.time()
    min_conn = int(os.getenv("POSTGRES_POOL_MIN", 1))
    max_conn = int(os.getenv("POSTGRES_POOL_MAX", 5))
    safe_params = _sanitize_db_params(params)
    _log_event(
        "info",
        "postgres_pool_create_attempt",
        params=safe_params,
        min_conn=min_conn,
        max_conn=max_conn,
    )
    try:
        if "dsn" in params:
            _connection_pool = ThreadedConnectionPool(min_conn, max_conn, params["dsn"])
        else:
            _connection_pool = ThreadedConnectionPool(min_conn, max_conn, **params)
        _pool_params_key = params_key
        _log_event(
            "info",
            "postgres_pool_create_success",
            duration=_elapsed_seconds(start_time),
            params=safe_params,
            min_conn=min_conn,
            max_conn=max_conn,
        )
        return _connection_pool, params
    except Exception as e:
        _connection_pool = None
        _pool_params_key = None
        _log_event(
            "error",
            "postgres_pool_create_failure",
            error=str(e),
            duration=_elapsed_seconds(start_time),
            params=safe_params,
        )
        raise


@contextmanager
def get_connection():
    """Yield a pooled psycopg2 connection and return it to the pool afterwards."""
    pool, params = _get_or_create_pool()
    conn = None
    start_time = time.time()
    safe_params = _sanitize_db_params(params)
    _log_event("info", "postgres_pool_acquire_attempt", params=safe_params)
    try:
        conn = pool.getconn()
        conn.autocommit = False
        _log_event("info", "postgres_pool_acquire_success", duration=_elapsed_seconds(start_time))
    except Exception as e:
        _log_event(
            "error",
            "postgres_pool_acquire_failure",
            error=str(e),
            duration=_elapsed_seconds(start_time),
        )
        raise

    try:
        yield conn
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception as e:
                _log_event("error", "postgres_connection_rollback_failure", error=str(e))
        raise
    finally:
        if conn is not None:
            try:
                if conn.closed:
                    pool.putconn(conn, close=True)
                else:
                    pool.putconn(conn)
                _log_event("info", "postgres_pool_release", duration=_elapsed_seconds(start_time))
            except Exception as e:
                _log_event("error", "postgres_pool_release_failure", error=str(e))


def fetch_one(query: str, params=None, log_errors: bool = True):
    """Execute a query and return a single row as a dict (or None), with logging and timing."""
    params = params or ()
    start_time = time.time()
    is_write_query = _is_write_query(query)
    try:
        _log_event("info", "postgres_query_start", query=query, params=params)
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                row = cur.fetchone()
            if is_write_query:
                conn.commit()
            else:
                conn.rollback()
        _log_event(
            "info",
            "postgres_query_success",
            query=query,
            params=params,
            duration=_elapsed_seconds(start_time),
            write_query=is_write_query,
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
