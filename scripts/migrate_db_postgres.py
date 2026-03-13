#!/usr/bin/env python
"""
Copy tables and rows from the local SQLite database into PostgreSQL.

This is intended as a one-off migration utility for moving the existing
`db/games.db` data into the Render-hosted PostgreSQL database.

Behavior:
- Reads all non-SQLite-internal tables from the SQLite source DB.
- Creates matching tables in PostgreSQL using an explicit FLASK_ENV prefix
    (for example `uat_game_stats`).
- Copies all rows across.
- By default, uses `ON CONFLICT DO NOTHING` where a primary key or unique
  constraint exists, so the script is safe to rerun.
- Optionally truncates the target tables first.

Usage examples:
    python scripts/migrate_sqlite_to_postgres.py
    python scripts/migrate_sqlite_to_postgres.py --replace
    python scripts/migrate_sqlite_to_postgres.py --source db/games.db --tables game_stats daily_game

Expected environment:
    DB_TYPE=postgres
    FLASK_ENV=uat|production|development
    POSTGRES_DSN=... or DATABASE_URL_EXTERNAL=... or DATABASE_URL=...
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from services.game_database_postgres import ENVIRONMENT, get_db_connection  # noqa: E402

try:
    from psycopg2 import sql
    from psycopg2.extras import execute_values
except ImportError as exc:  # pragma: no cover - operational failure path
    raise SystemExit(
        "psycopg2 is required for this script. Install dependencies first."
    ) from exc


TYPE_MAP = {
    "INT": "INTEGER",
    "INTEGER": "INTEGER",
    "TINYINT": "INTEGER",
    "SMALLINT": "INTEGER",
    "MEDIUMINT": "INTEGER",
    "BIGINT": "BIGINT",
    "UNSIGNED BIG INT": "BIGINT",
    "TEXT": "TEXT",
    "CLOB": "TEXT",
    "CHAR": "TEXT",
    "VARCHAR": "TEXT",
    "VARYING CHARACTER": "TEXT",
    "NCHAR": "TEXT",
    "NATIVE CHARACTER": "TEXT",
    "NVARCHAR": "TEXT",
    "BLOB": "BYTEA",
    "REAL": "DOUBLE PRECISION",
    "DOUBLE": "DOUBLE PRECISION",
    "DOUBLE PRECISION": "DOUBLE PRECISION",
    "FLOAT": "DOUBLE PRECISION",
    "NUMERIC": "NUMERIC",
    "DECIMAL": "NUMERIC",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "DATETIME": "TIMESTAMP",
    "TIMESTAMP": "TIMESTAMP",
}


def env_table_name(base: str) -> str:
    """Prefix tables by FLASK_ENV, except shared tables like daily_game."""
    if base == "daily_game":
        return "daily_game"
    env = (ENVIRONMENT or "development").strip()
    return f"{env}_{base}" if env else base


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate SQLite tables into PostgreSQL")
    parser.add_argument(
        "--source",
        default=str(ROOT_DIR / "db" / "games.db"),
        help="Path to the SQLite source database (default: db/games.db)",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        help="Optional subset of SQLite tables to copy",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Truncate target PostgreSQL tables before copying rows",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Insert batch size for PostgreSQL writes (default: 1000)",
    )
    return parser.parse_args()


def normalize_sqlite_type(declared_type: str | None) -> str:
    if not declared_type:
        return "TEXT"
    upper = declared_type.upper().strip()
    for key, mapped in TYPE_MAP.items():
        if key in upper:
            return mapped
    return "TEXT"


def get_sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    return [row[0] for row in cursor.fetchall()]


def get_create_sql(conn: sqlite3.Connection, table: str) -> str:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    )
    row = cursor.fetchone()
    return row[0] if row and row[0] else ""


def get_columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute(f'PRAGMA table_info("{table}")')
    columns = []
    for cid, name, col_type, notnull, default, pk in cursor.fetchall():
        columns.append(
            {
                "cid": cid,
                "name": name,
                "type": col_type,
                "notnull": bool(notnull),
                "default": default,
                "pk": int(pk),
            }
        )
    return columns


def get_unique_constraints(conn: sqlite3.Connection, table: str) -> list[list[str]]:
    cursor = conn.cursor()
    cursor.execute(f'PRAGMA index_list("{table}")')
    constraints: list[list[str]] = []

    for index_row in cursor.fetchall():
        # SQLite returns: seq, name, unique, origin, partial
        index_name = index_row[1]
        is_unique = bool(index_row[2])
        origin = index_row[3] if len(index_row) > 3 else None
        if not is_unique or origin == "pk":
            continue

        cursor.execute(f'PRAGMA index_info("{index_name}")')
        cols = [row[2] for row in cursor.fetchall()]
        if cols:
            constraints.append(cols)

    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for cols in constraints:
        key = tuple(cols)
        if key not in seen:
            deduped.append(cols)
            seen.add(key)
    return deduped


def detect_identity_columns(create_sql: str, columns: list[dict]) -> set[str]:
    create_upper = create_sql.upper()
    identity_columns: set[str] = set()
    for column in columns:
        if normalize_sqlite_type(column["type"]) != "INTEGER":
            continue
        name = re.escape(column["name"])
        pattern = rf'\b"?{name}"?\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b'
        if re.search(pattern, create_upper, re.IGNORECASE):
            identity_columns.add(column["name"])
    return identity_columns


def translate_default(default_value: str | None) -> sql.SQL | None:
    if default_value is None:
        return None

    raw = str(default_value).strip()
    upper = raw.upper()

    if upper in {"CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME"}:
        return sql.SQL(raw)

    if raw.startswith("(") and raw.endswith(")"):
        inner = raw[1:-1].strip()
        return translate_default(inner)

    if re.fullmatch(r"-?\d+(\.\d+)?", raw):
        return sql.SQL(raw)

    if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
        return sql.SQL(raw)

    # Unsupported SQLite-specific expressions are skipped rather than failing.
    return None


def build_create_table_statement(
    source_table: str,
    target_table: str,
    columns: list[dict],
    unique_constraints: list[list[str]],
    identity_columns: set[str],
) -> sql.Composed:
    pk_columns = [c for c in sorted(columns, key=lambda col: col["pk"]) if c["pk"] > 0]
    column_defs: list[sql.SQL] = []
    table_constraints: list[sql.SQL] = []

    for column in columns:
        parts: list[sql.SQL] = [sql.Identifier(column["name"])]

        if column["name"] in identity_columns:
            parts.append(sql.SQL("INTEGER GENERATED BY DEFAULT AS IDENTITY"))
        else:
            parts.append(sql.SQL(normalize_sqlite_type(column["type"])))

        if column["notnull"] or column["pk"] > 0:
            parts.append(sql.SQL("NOT NULL"))

        default_sql = translate_default(column["default"])
        if default_sql is not None and column["name"] not in identity_columns:
            parts.extend([sql.SQL("DEFAULT"), default_sql])

        column_defs.append(sql.SQL(" ").join(parts))

    if pk_columns:
        table_constraints.append(
            sql.SQL("PRIMARY KEY ({})").format(
                sql.SQL(", ").join(sql.Identifier(col["name"]) for col in pk_columns)
            )
        )

    for unique_cols in unique_constraints:
        table_constraints.append(
            sql.SQL("UNIQUE ({})").format(
                sql.SQL(", ").join(sql.Identifier(col) for col in unique_cols)
            )
        )

    all_defs = column_defs + table_constraints
    return sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
        sql.Identifier(target_table),
        sql.SQL(", ").join(all_defs),
    )


def get_postgres_columns(pg_conn, target_table: str) -> set[str]:
    with pg_conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (target_table,),
        )
        return {row[0] for row in cursor.fetchall()}


def add_missing_columns(pg_conn, target_table: str, source_columns: list[dict]) -> list[str]:
    existing = get_postgres_columns(pg_conn, target_table)
    missing: list[str] = []

    with pg_conn.cursor() as cursor:
        for column in source_columns:
            name = column["name"]
            if name in existing:
                continue

            col_type = normalize_sqlite_type(column["type"])
            cursor.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN {} {}")
                .format(sql.Identifier(target_table), sql.Identifier(name), sql.SQL(col_type))
            )
            missing.append(name)

    if missing:
        pg_conn.commit()
    return missing


def get_conflict_columns(columns: list[dict], unique_constraints: list[list[str]]) -> list[str]:
    pk_columns = [c["name"] for c in sorted(columns, key=lambda col: col["pk"]) if c["pk"] > 0]
    if pk_columns:
        return pk_columns
    if unique_constraints:
        return unique_constraints[0]
    return []


def chunked(rows: list[tuple], size: int) -> Iterable[list[tuple]]:
    for idx in range(0, len(rows), size):
        yield rows[idx: idx + size]


def create_target_table(
    pg_conn,
    sqlite_conn: sqlite3.Connection,
    source_table: str,
    replace: bool,
) -> tuple[list[dict], list[list[str]]]:
    columns = get_columns(sqlite_conn, source_table)
    unique_constraints = get_unique_constraints(sqlite_conn, source_table)
    create_sql = get_create_sql(sqlite_conn, source_table)
    identity_columns = detect_identity_columns(create_sql, columns)
    target_table = env_table_name(source_table)

    statement = build_create_table_statement(
        source_table=source_table,
        target_table=target_table,
        columns=columns,
        unique_constraints=unique_constraints,
        identity_columns=identity_columns,
    )

    with pg_conn.cursor() as cursor:
        if replace:
            cursor.execute(
                sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                    sql.Identifier(target_table)
                )
            )
        cursor.execute(statement)
    pg_conn.commit()

    # If table already existed (replace=False), ensure new source columns are present
    # before insert (e.g. player_country / player_city).
    added_columns = add_missing_columns(pg_conn, target_table, columns)
    if added_columns:
        print(f"Added missing columns to {target_table}: {', '.join(added_columns)}")

    return columns, unique_constraints


def read_sqlite_rows(conn: sqlite3.Connection, table: str) -> list[tuple]:
    cursor = conn.cursor()
    cursor.execute(f'SELECT * FROM "{table}"')
    return cursor.fetchall()


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    )
    return cursor.fetchone() is not None


def _sqlite_select_if_columns_exist(conn: sqlite3.Connection, table: str, preferred_cols: list[str]) -> tuple[list[str], list[tuple]]:
    available = {col["name"] for col in get_columns(conn, table)}
    cols = [col for col in preferred_cols if col in available]
    if not cols:
        return [], []
    cursor = conn.cursor()
    quoted = ", ".join(f'"{c}"' for c in cols)
    cursor.execute(f'SELECT {quoted} FROM "{table}"')
    return cols, cursor.fetchall()


def create_consolidated_player_table(pg_conn, replace: bool) -> str:
    target_table = env_table_name("player_game_state")
    with pg_conn.cursor() as cursor:
        if replace:
            cursor.execute(
                sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                    sql.Identifier(target_table)
                )
            )

        cursor.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    player_uid            TEXT    NOT NULL,
                    game_date             TEXT    NOT NULL,
                    game_number           INTEGER,
                    guess_history         TEXT    DEFAULT '[]',
                    wrong_guesses         TEXT    DEFAULT '[]',
                    hard_mode             INTEGER DEFAULT 0,
                    guessed_main_country  INTEGER DEFAULT 0,
                    game_over             INTEGER DEFAULT 0,
                    game_result           TEXT,
                    game_result_recorded  INTEGER DEFAULT 0,
                    leaderboard_recorded  INTEGER DEFAULT 0,
                    recorded_at           TIMESTAMP,
                    PRIMARY KEY (player_uid, game_date)
                )
                """
            ).format(sql.Identifier(target_table))
        )

    pg_conn.commit()
    return target_table


def migrate_consolidated_player_table(pg_conn, sqlite_conn: sqlite3.Connection, replace: bool, batch_size: int) -> int:
    target_table = create_consolidated_player_table(pg_conn, replace=replace)

    if replace:
        with pg_conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY").format(
                    sql.Identifier(target_table)
                )
            )
        pg_conn.commit()

    merged: dict[tuple[str, str], dict] = {}

    if sqlite_table_exists(sqlite_conn, "player_daily_state"):
        daily_cols, daily_rows = _sqlite_select_if_columns_exist(
            sqlite_conn,
            "player_daily_state",
            [
                "player_uid",
                "game_date",
                "guess_history",
                "wrong_guesses",
                "hard_mode",
                "guessed_main_country",
                "game_over",
                "game_result_recorded",
            ],
        )
        col_idx = {name: idx for idx, name in enumerate(daily_cols)}
        for row in daily_rows:
            player_uid = row[col_idx["player_uid"]]
            game_date = str(row[col_idx["game_date"]])
            key = (player_uid, game_date)
            state = merged.get(key, {
                "player_uid": player_uid,
                "game_date": game_date,
                "game_number": None,
                "guess_history": "[]",
                "wrong_guesses": "[]",
                "hard_mode": 0,
                "guessed_main_country": 0,
                "game_over": 0,
                "game_result": None,
                "game_result_recorded": 0,
                "leaderboard_recorded": 0,
                "recorded_at": None,
            })

            state["guess_history"] = row[col_idx.get("guess_history", 0)] or "[]"
            state["wrong_guesses"] = row[col_idx.get("wrong_guesses", 0)] or "[]"
            state["hard_mode"] = int(bool(row[col_idx["hard_mode"]])) if "hard_mode" in col_idx else state["hard_mode"]
            state["guessed_main_country"] = int(bool(row[col_idx["guessed_main_country"]])) if "guessed_main_country" in col_idx else state["guessed_main_country"]
            state["game_over"] = int(bool(row[col_idx["game_over"]])) if "game_over" in col_idx else state["game_over"]
            state["game_result_recorded"] = int(bool(row[col_idx["game_result_recorded"]])) if "game_result_recorded" in col_idx else state["game_result_recorded"]
            merged[key] = state

    if sqlite_table_exists(sqlite_conn, "player_results"):
        results_cols, results_rows = _sqlite_select_if_columns_exist(
            sqlite_conn,
            "player_results",
            ["player_uid", "game_date", "game_number"],
        )
        col_idx = {name: idx for idx, name in enumerate(results_cols)}
        for row in results_rows:
            player_uid = row[col_idx["player_uid"]]
            game_date = str(row[col_idx["game_date"]])
            key = (player_uid, game_date)
            state = merged.get(key, {
                "player_uid": player_uid,
                "game_date": game_date,
                "game_number": None,
                "guess_history": "[]",
                "wrong_guesses": "[]",
                "hard_mode": 0,
                "guessed_main_country": 0,
                "game_over": 0,
                "game_result": None,
                "game_result_recorded": 0,
                "leaderboard_recorded": 0,
                "recorded_at": None,
            })

            state["game_number"] = row[col_idx["game_number"]] if "game_number" in col_idx else state["game_number"]
            state["game_over"] = 1
            state["game_result_recorded"] = 1
            state["leaderboard_recorded"] = 1
            merged[key] = state

    rows = [
        (
            row["player_uid"],
            row["game_date"],
            row["game_number"],
            row["guess_history"],
            row["wrong_guesses"],
            row["hard_mode"],
            row["guessed_main_country"],
            row["game_over"],
            row["game_result"],
            row["game_result_recorded"],
            row["leaderboard_recorded"],
            row["recorded_at"],
        )
        for row in merged.values()
    ]

    if not rows:
        return 0

    insert_sql = sql.SQL(
        """
        INSERT INTO {} (
            player_uid, game_date, game_number, guess_history, wrong_guesses,
            hard_mode, guessed_main_country, game_over, game_result,
            game_result_recorded, leaderboard_recorded, recorded_at
        ) VALUES %s
        ON CONFLICT (player_uid, game_date) DO UPDATE SET
            game_number = COALESCE(EXCLUDED.game_number, {}.game_number),
            guess_history = COALESCE(EXCLUDED.guess_history, {}.guess_history),
            wrong_guesses = COALESCE(EXCLUDED.wrong_guesses, {}.wrong_guesses),
            hard_mode = GREATEST({}.hard_mode, EXCLUDED.hard_mode),
            guessed_main_country = GREATEST({}.guessed_main_country, EXCLUDED.guessed_main_country),
            game_over = GREATEST({}.game_over, EXCLUDED.game_over),
            game_result = COALESCE(EXCLUDED.game_result, {}.game_result),
            game_result_recorded = GREATEST({}.game_result_recorded, EXCLUDED.game_result_recorded),
            leaderboard_recorded = GREATEST({}.leaderboard_recorded, EXCLUDED.leaderboard_recorded),
            recorded_at = COALESCE(EXCLUDED.recorded_at, {}.recorded_at)
        """
    ).format(
        sql.Identifier(target_table),
        sql.Identifier(target_table),
        sql.Identifier(target_table),
        sql.Identifier(target_table),
        sql.Identifier(target_table),
        sql.Identifier(target_table),
        sql.Identifier(target_table),
        sql.Identifier(target_table),
        sql.Identifier(target_table),
        sql.Identifier(target_table),
        sql.Identifier(target_table),
    )

    inserted = 0
    with pg_conn.cursor() as cursor:
        for batch in chunked(rows, batch_size):
            execute_values(cursor, insert_sql.as_string(pg_conn), batch)
            inserted += len(batch)
    pg_conn.commit()
    return inserted


def insert_rows(pg_conn, target_table: str, columns: list[dict], rows: list[tuple], conflict_columns: list[str], batch_size: int) -> int:
    if not rows:
        return 0

    column_names = [column["name"] for column in columns]
    insert_prefix = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
        sql.Identifier(target_table),
        sql.SQL(", ").join(sql.Identifier(name) for name in column_names),
    )

    if conflict_columns:
        insert_sql = insert_prefix + sql.SQL(" ON CONFLICT ({}) DO NOTHING").format(
            sql.SQL(", ").join(sql.Identifier(name) for name in conflict_columns)
        )
    else:
        insert_sql = insert_prefix

    inserted = 0
    with pg_conn.cursor() as cursor:
        for batch in chunked(rows, batch_size):
            execute_values(cursor, insert_sql.as_string(pg_conn), batch)
            inserted += len(batch)
    pg_conn.commit()
    return inserted


def main() -> int:
    load_dotenv()
    args = parse_args()

    if not Path(args.source).exists():
        print(f"❌ SQLite source database not found: {args.source}")
        return 1

    try:
        sqlite_conn = sqlite3.connect(args.source)
        postgres_conn = get_db_connection()
    except Exception as exc:
        print(f"❌ Failed to open database connection: {exc}")
        return 1

    try:
        source_tables = get_sqlite_tables(sqlite_conn)

        # Legacy play-state tables are merged into consolidated player_game_state.
        # We skip direct migration of these unless explicitly requested.
        legacy_tables = {"player_daily_state", "player_results"}
        if args.tables:
            requested = set(args.tables)
            source_tables = [table for table in source_tables if table in requested]
        else:
            source_tables = [table for table in source_tables if table not in legacy_tables]

        if not source_tables:
            print("⚠️ No matching SQLite tables found to migrate.")
            return 0

        print("=" * 72)
        print("SQLite → PostgreSQL migration")
        print("=" * 72)
        print(f"Source SQLite DB : {args.source}")
        print(f"Target environment: {ENVIRONMENT}")
        print(f"Tables to migrate : {', '.join(source_tables)}")
        print(f"Replace existing  : {'yes' if args.replace else 'no'}")

        total_rows = 0
        for source_table in source_tables:
            target_table = env_table_name(source_table)
            print(f"\n--- Migrating {source_table} -> {target_table} ---")

            columns, unique_constraints = create_target_table(
                postgres_conn,
                sqlite_conn,
                source_table,
                replace=args.replace,
            )
            rows = read_sqlite_rows(sqlite_conn, source_table)
            conflict_columns = get_conflict_columns(columns, unique_constraints)
            attempted = insert_rows(
                postgres_conn,
                target_table,
                columns,
                rows,
                conflict_columns,
                args.batch_size,
            )

            total_rows += len(rows)
            print(f"Rows read     : {len(rows)}")
            print(f"Rows inserted : {attempted}")
            if conflict_columns:
                print(f"Conflict keys : {', '.join(conflict_columns)}")
            else:
                print("Conflict keys : none")

        # Build consolidated player_game_state for postgres service usage.
        consolidated_requested = (
            not args.tables
            or "player_game_state" in args.tables
            or "player_daily_state" in args.tables
            or "player_results" in args.tables
        )
        if consolidated_requested:
            target_table = env_table_name("player_game_state")
            print(f"\n--- Building consolidated table -> {target_table} ---")
            consolidated_rows = migrate_consolidated_player_table(
                postgres_conn,
                sqlite_conn,
                replace=args.replace,
                batch_size=args.batch_size,
            )
            print(f"Rows consolidated into {target_table}: {consolidated_rows}")

        print(f"\n✅ Migration complete. Total source rows processed: {total_rows}")
        return 0
    except Exception as exc:
        postgres_conn.rollback()
        print(f"❌ Migration failed: {exc}")
        return 1
    finally:
        sqlite_conn.close()
        postgres_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
