"""Migrate SQLite daily_game data into Postgres and create env-prefixed tables.

This script intentionally rebuilds the Postgres ``daily_game`` table from the
SQLite source of truth, then creates a fresh set of env-prefixed stats/state
tables using the same schema as the existing development tables.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = BASE_DIR / "db" / "games.db"
SAFE_IDENTIFIER = re.compile(r"[^a-z0-9_]")


def _normalize_identifier_part(value: str) -> str:
	normalized = (value or "").strip().lower().replace("-", "_")
	normalized = SAFE_IDENTIFIER.sub("", normalized)
	return normalized.strip("_")


def _resolve_env_prefix(explicit_prefix: str | None) -> str:
	"""Return the table prefix string, or "" for production (unprefixed tables)."""
	if explicit_prefix is not None:
		normalized = _normalize_identifier_part(explicit_prefix)
		if normalized in {"prod", "production"}:
			print("Using unprefixed production table names (country_stats, game_stats, etc.).")
			return ""
		if normalized:
			return normalized

	env_prefix = _normalize_identifier_part(os.getenv("POSTGRES_TABLE_PREFIX", ""))
	if env_prefix:
		return env_prefix

	flask_env = _normalize_identifier_part(os.getenv("FLASK_ENV", ""))
	if flask_env == "local":
		flask_env = "development"

	if flask_env in {"prod", "production"}:
		print("FLASK_ENV is production — using unprefixed production table names.")
		return ""

	if flask_env:
		return flask_env

	raise ValueError(
		"Unable to resolve an env table prefix. Pass --env-prefix (use 'production' for "
		"unprefixed prod tables) or set POSTGRES_TABLE_PREFIX/FLASK_ENV."
	)


def _get_postgres_connection() -> psycopg2.extensions.connection:
	params = _get_db_params()
	if "dsn" in params:
		return psycopg2.connect(params["dsn"])
	return psycopg2.connect(**params)


def _is_local_env() -> bool:
	return os.getenv("FLASK_ENV", "").strip().lower() == "local"


def _get_db_params() -> dict[str, str | int]:
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


def _sqlite_table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
	cursor.execute(
		"SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
		(table_name,),
	)
	return cursor.fetchone() is not None


def _sqlite_table_columns(cursor: sqlite3.Cursor, table_name: str) -> list[str]:
	cursor.execute(f"PRAGMA table_info({table_name})")
	return [row[1] for row in cursor.fetchall()]


def _compute_rotations(rows: list[tuple[str, str]]) -> list[tuple[str, str, int]]:
	migrated_rows: list[tuple[str, str, int]] = []
	current_rotation = 1
	used_countries: set[str] = set()

	for game_date, country in rows:
		if country in used_countries:
			current_rotation += 1
			used_countries = set()

		used_countries.add(country)
		migrated_rows.append((str(game_date), str(country), current_rotation))

	return migrated_rows


def _read_sqlite_daily_games(sqlite_path: Path) -> tuple[list[tuple[str, str, int]], str]:
	if not sqlite_path.exists():
		raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

	connection = sqlite3.connect(sqlite_path)
	try:
		cursor = connection.cursor()
		source_table = None
		for candidate in ("daily_game", "daily_game_old"):
			if not _sqlite_table_exists(cursor, candidate):
				continue

			cursor.execute(f"SELECT COUNT(*) FROM {candidate}")
			row_count = int(cursor.fetchone()[0])
			if row_count > 0:
				source_table = candidate
				break

		if source_table is None:
			raise RuntimeError(
				"No SQLite daily game rows found in daily_game or daily_game_old."
			)

		columns = _sqlite_table_columns(cursor, source_table)
		if "rotation" in columns:
			cursor.execute(
				f"SELECT game_date, country, rotation FROM {source_table} ORDER BY game_date ASC"
			)
			rows = [
				(str(game_date), str(country), int(rotation))
				for game_date, country, rotation in cursor.fetchall()
			]
		else:
			cursor.execute(
				f"SELECT game_date, country FROM {source_table} ORDER BY game_date ASC"
			)
			rows = _compute_rotations(cursor.fetchall())
	finally:
		connection.close()

	return rows, source_table


def _read_sqlite_table_rows(sqlite_path: Path, query: str) -> list[tuple]:
	connection = sqlite3.connect(sqlite_path)
	try:
		cursor = connection.cursor()
		cursor.execute(query)
		return cursor.fetchall()
	finally:
		connection.close()


def _read_sqlite_country_stats(
	sqlite_path: Path,
) -> list[tuple[int, str, str | None, str | None, str | None, int, int, int]]:
	rows = _read_sqlite_table_rows(
		sqlite_path,
		"""
		SELECT id, game_date, country, region, city, plays, successes, failures
		FROM country_stats
		ORDER BY id ASC
		""",
	)
	return [
		(
			int(row_id),
			str(game_date),
			country,
			region,
			city,
			int(plays or 0),
			int(successes or 0),
			int(failures or 0),
		)
		for row_id, game_date, country, region, city, plays, successes, failures in rows
	]


def _read_sqlite_game_stats(sqlite_path: Path) -> list[tuple[str, int, int]]:
	rows = _read_sqlite_table_rows(
		sqlite_path,
		"""
		SELECT game_date, successes, failures
		FROM game_stats
		ORDER BY game_date ASC
		""",
	)
	return [
		(str(game_date), int(successes or 0), int(failures or 0))
		for game_date, successes, failures in rows
	]


def _read_sqlite_player_stats(
	sqlite_path: Path,
) -> list[tuple[str, int, int, int, int, int, str | None, str | None, str | None]]:
	rows = _read_sqlite_table_rows(
		sqlite_path,
		"""
		SELECT
			player_uid,
			games_played,
			games_won,
			current_streak,
			best_streak,
			migrated,
			last_updated,
			player_city,
			player_country
		FROM player_stats
		ORDER BY player_uid ASC
		""",
	)
	return [
		(
			str(player_uid),
			int(games_played or 0),
			int(games_won or 0),
			int(current_streak or 0),
			int(best_streak or 0),
			int(migrated or 0),
			last_updated,
			player_city,
			player_country,
		)
		for (
			player_uid,
			games_played,
			games_won,
			current_streak,
			best_streak,
			migrated,
			last_updated,
			player_city,
			player_country,
		) in rows
	]


def _derive_game_result(guessed_main_country: int, game_over: int) -> str:
	if not int(game_over or 0):
		return "In progress"
	if int(guessed_main_country or 0):
		return "Won"
	return "Lost"


def _read_sqlite_player_game_state(sqlite_path: Path) -> list[tuple]:
	rows = _read_sqlite_table_rows(
		sqlite_path,
		"""
		SELECT
			player_uid,
			game_date,
			guess_history,
			wrong_guesses,
			guessed_main_country,
			game_over,
			hard_mode,
			game_result_recorded
		FROM player_daily_state
		ORDER BY game_date ASC, player_uid ASC
		""",
	)
	return [
		(
			str(player_uid),
			str(game_date),
			None,
			guess_history or "[]",
			wrong_guesses or "[]",
			int(hard_mode or 0),
			int(guessed_main_country or 0),
			int(game_over or 0),
			_derive_game_result(guessed_main_country, game_over),
			int(game_result_recorded or 0),
			0,
			None,
			False,
		)
		for (
			player_uid,
			game_date,
			guess_history,
			wrong_guesses,
			guessed_main_country,
			game_over,
			hard_mode,
			game_result_recorded,
		) in rows
	]


def _recreate_daily_game_table(cursor: psycopg2.extensions.cursor) -> None:
	cursor.execute("DROP TABLE IF EXISTS daily_game")
	cursor.execute(
		"""
		CREATE TABLE daily_game (
			game_date DATE PRIMARY KEY,
			country TEXT NOT NULL,
			rotation INTEGER NOT NULL,
			UNIQUE (rotation, country)
		)
		"""
	)


def _load_daily_games(
	cursor: psycopg2.extensions.cursor,
	daily_games: list[tuple[str, str, int]],
) -> int:
	if not daily_games:
		return 0

	execute_values(
		cursor,
		"""
		INSERT INTO daily_game (game_date, country, rotation)
		VALUES %s
		""",
		daily_games,
		template="(%s::date, %s, %s)",
		page_size=500,
	)
	return len(daily_games)


def _load_country_stats(cursor: psycopg2.extensions.cursor, table_name: str, rows: list[tuple]) -> int:
	if not rows:
		return 0

	execute_values(
		cursor,
		sql.SQL(
			"""
			INSERT INTO {} (id, game_date, country, region, city, plays, successes, failures)
			VALUES %s
			"""
		).format(sql.Identifier(table_name)).as_string(cursor),
		rows,
		template="(%s, %s, %s, %s, %s, %s, %s, %s)",
		page_size=500,
	)
	cursor.execute(
		sql.SQL(
			"""
			SELECT setval(
				pg_get_serial_sequence(%s, 'id'),
				COALESCE((SELECT MAX(id) FROM {}), 1),
				true
			)
			"""
		).format(sql.Identifier(table_name)),
		(table_name,),
	)
	return len(rows)


def _load_game_stats(cursor: psycopg2.extensions.cursor, table_name: str, rows: list[tuple]) -> int:
	if not rows:
		return 0

	execute_values(
		cursor,
		sql.SQL(
			"""
			INSERT INTO {} (game_date, successes, failures)
			VALUES %s
			"""
		).format(sql.Identifier(table_name)).as_string(cursor),
		rows,
		template="(%s::date, %s, %s)",
		page_size=500,
	)
	return len(rows)


def _load_player_stats(cursor: psycopg2.extensions.cursor, table_name: str, rows: list[tuple]) -> int:
	if not rows:
		return 0

	execute_values(
		cursor,
		sql.SQL(
			"""
			INSERT INTO {} (
				player_uid,
				games_played,
				games_won,
				current_streak,
				best_streak,
				migrated,
				last_updated,
				player_city,
				player_country
			)
			VALUES %s
			"""
		).format(sql.Identifier(table_name)).as_string(cursor),
		rows,
		template="(%s, %s, %s, %s, %s, %s, %s::date, %s, %s)",
		page_size=500,
	)
	return len(rows)


def _load_player_game_state(cursor: psycopg2.extensions.cursor, table_name: str, rows: list[tuple]) -> int:
	if not rows:
		return 0

	execute_values(
		cursor,
		sql.SQL(
			"""
			INSERT INTO {} (
				player_uid,
				game_date,
				game_number,
				guess_history,
				wrong_guesses,
				hard_mode,
				guessed_main_country,
				game_over,
				game_result,
				game_result_recorded,
				leaderboard_recorded,
				recorded_at,
				player_stats_recorded
			)
			VALUES %s
			"""
		).format(sql.Identifier(table_name)).as_string(cursor),
		rows,
		template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
		page_size=500,
	)
	return len(rows)


def _create_country_stats_table(
	cursor: psycopg2.extensions.cursor,
	table_name: str,
) -> None:
	identifier = sql.Identifier(table_name)
	cursor.execute(sql.SQL("DROP TABLE IF EXISTS {}") .format(identifier))
	cursor.execute(
		sql.SQL(
			"""
			CREATE TABLE {} (
				id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
				game_date TEXT NOT NULL,
				country TEXT,
				region TEXT,
				city TEXT,
				plays INTEGER DEFAULT 0,
				successes INTEGER DEFAULT 0,
				failures INTEGER DEFAULT 0,
				UNIQUE (game_date, country, region, city)
			)
			"""
		).format(identifier)
	)


def _create_game_stats_table(
	cursor: psycopg2.extensions.cursor,
	table_name: str,
) -> None:
	identifier = sql.Identifier(table_name)
	cursor.execute(sql.SQL("DROP TABLE IF EXISTS {}") .format(identifier))
	cursor.execute(
		sql.SQL(
			"""
			CREATE TABLE {} (
				game_date DATE PRIMARY KEY,
				successes INTEGER DEFAULT 0,
				failures INTEGER DEFAULT 0
			)
			"""
		).format(identifier)
	)


def _create_player_game_state_table(
	cursor: psycopg2.extensions.cursor,
	table_name: str,
) -> None:
	identifier = sql.Identifier(table_name)
	cursor.execute(sql.SQL("DROP TABLE IF EXISTS {}") .format(identifier))
	cursor.execute(
		sql.SQL(
			"""
			CREATE TABLE {} (
				player_uid TEXT NOT NULL,
				game_date TEXT NOT NULL,
				game_number INTEGER,
				guess_history TEXT DEFAULT '[]',
				wrong_guesses TEXT DEFAULT '[]',
				hard_mode INTEGER DEFAULT 0,
				guessed_main_country INTEGER DEFAULT 0,
				game_over INTEGER DEFAULT 0,
				game_result TEXT,
				game_result_recorded INTEGER DEFAULT 0,
				leaderboard_recorded INTEGER DEFAULT 0,
				recorded_at TIMESTAMP,
				player_stats_recorded BOOLEAN DEFAULT FALSE,
				PRIMARY KEY (player_uid, game_date)
			)
			"""
		).format(identifier)
	)


def _create_player_stats_table(
	cursor: psycopg2.extensions.cursor,
	table_name: str,
) -> None:
	identifier = sql.Identifier(table_name)
	cursor.execute(sql.SQL("DROP TABLE IF EXISTS {}") .format(identifier))
	cursor.execute(
		sql.SQL(
			"""
			CREATE TABLE {} (
				player_uid TEXT PRIMARY KEY,
				games_played INTEGER DEFAULT 0,
				games_won INTEGER DEFAULT 0,
				current_streak INTEGER DEFAULT 0,
				best_streak INTEGER DEFAULT 0,
				migrated INTEGER DEFAULT 0,
				last_updated DATE,
				player_city TEXT,
				player_country TEXT
			)
			"""
		).format(identifier)
	)


def _create_env_tables(cursor: psycopg2.extensions.cursor, env_prefix: str) -> list[str]:
	if env_prefix:
		table_names = [
			f"{env_prefix}_country_stats",
			f"{env_prefix}_game_stats",
			f"{env_prefix}_player_game_state",
			f"{env_prefix}_player_stats",
		]
	else:
		table_names = [
			"country_stats",
			"game_stats",
			"player_game_state",
			"player_stats",
		]

	_create_country_stats_table(cursor, table_names[0])
	_create_game_stats_table(cursor, table_names[1])
	_create_player_game_state_table(cursor, table_names[2])
	_create_player_stats_table(cursor, table_names[3])
	return table_names


def migrate(sqlite_path: Path, env_prefix: str, allow_development_prefix: bool) -> None:
	if env_prefix and env_prefix == "development" and not allow_development_prefix:
		raise ValueError(
			"Refusing to recreate development_* tables by default. "
			"Pass --allow-development-prefix if you intend to replace them."
		)

	daily_games, source_table = _read_sqlite_daily_games(sqlite_path)
	country_stats_rows = _read_sqlite_country_stats(sqlite_path)
	game_stats_rows = _read_sqlite_game_stats(sqlite_path)
	player_stats_rows = _read_sqlite_player_stats(sqlite_path)
	player_game_state_rows = _read_sqlite_player_game_state(sqlite_path)
	postgres_connection = _get_postgres_connection()
	try:
		with postgres_connection:
			with postgres_connection.cursor() as cursor:
				_recreate_daily_game_table(cursor)
				loaded_daily_games = _load_daily_games(cursor, daily_games)
				created_tables = _create_env_tables(cursor, env_prefix)
				loaded_country_stats = _load_country_stats(cursor, created_tables[0], country_stats_rows)
				loaded_game_stats = _load_game_stats(cursor, created_tables[1], game_stats_rows)
				loaded_player_game_state = _load_player_game_state(cursor, created_tables[2], player_game_state_rows)
				loaded_player_stats = _load_player_stats(cursor, created_tables[3], player_stats_rows)
	finally:
		postgres_connection.close()

	print(
		f"Recreated daily_game and loaded {loaded_daily_games} rows from {sqlite_path} "
		f"using SQLite table {source_table}."
	)
	print(f"Loaded {loaded_country_stats} rows into {created_tables[0]}.")
	print(f"Loaded {loaded_game_stats} rows into {created_tables[1]}.")
	print(f"Loaded {loaded_player_game_state} rows into {created_tables[2]}.")
	print(f"Loaded {loaded_player_stats} rows into {created_tables[3]}.")
	print("Created tables:")
	for table_name in created_tables:
		print(f"- {table_name}")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description=(
			"Overwrite Postgres daily_game from SQLite and create a fresh set "
			"of env-prefixed tables that match the current development schema."
		)
	)
	parser.add_argument(
		"--sqlite-path",
		default=str(DEFAULT_SQLITE_PATH),
		help="Path to the source SQLite database.",
	)
	parser.add_argument(
		"--env-prefix",
		default=None,
		help=(
			"Prefix to prepend to the four Postgres tables. Defaults to "
			"POSTGRES_TABLE_PREFIX, then FLASK_ENV (with local -> development)."
		),
	)
	parser.add_argument(
		"--allow-development-prefix",
		action="store_true",
		help="Allow replacing development_* tables when the resolved prefix is development.",
	)
	return parser.parse_args()


def main() -> None:
	load_dotenv()
	args = parse_args()
	env_prefix = _resolve_env_prefix(args.env_prefix)
	migrate(
		sqlite_path=Path(args.sqlite_path),
		env_prefix=env_prefix,
		allow_development_prefix=args.allow_development_prefix,
	)


if __name__ == "__main__":
	main()
