#!/usr/bin/env python
"""
Copy tables and rows from the local SQLite database into PostgreSQL.

This is intended as a one-off migration utility for moving the existing
`db/games.db` data into the Render-hosted PostgreSQL database.

Behavior:
- Reads all non-SQLite-internal tables from the SQLite source DB.
- Creates matching tables in PostgreSQL using the current environment prefix
  from `table_name()` (for example `uat_game_stats`).
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

from services.game_database_connections import ENVIRONMENT, get_postgres_connection, table_name  # noqa: E402

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
    target_table = table_name(source_table)

    statement = build_create_table_statement(
        source_table=source_table,
        target_table=target_table,
        columns=columns,
        unique_constraints=unique_constraints,
        identity_columns=identity_columns,
    )

    with pg_conn.cursor() as cursor:
        cursor.execute(statement)
        if replace:
            cursor.execute(
                sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY").format(
                    sql.Identifier(target_table)
                )
            )
    pg_conn.commit()
    return columns, unique_constraints


def read_sqlite_rows(conn: sqlite3.Connection, table: str) -> list[tuple]:
    cursor = conn.cursor()
    cursor.execute(f'SELECT * FROM "{table}"')
    return cursor.fetchall()


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
        postgres_conn = get_postgres_connection()
    except Exception as exc:
        print(f"❌ Failed to open database connection: {exc}")
        return 1

    try:
        source_tables = get_sqlite_tables(sqlite_conn)
        if args.tables:
            requested = set(args.tables)
            source_tables = [table for table in source_tables if table in requested]

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
            target_table = table_name(source_table)
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
