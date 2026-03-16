"""Centralized SQL statements used by the Postgres migration services.

Keep all queries here so it's obvious which SQL is executed against the
new Postgres database.
"""

GET_COUNT_DAILY_GAMES = "SELECT COUNT(DISTINCT game_date) AS game_number FROM daily_game"

GET_DAILY_GAME_BY_DATE = (
    "SELECT country AS country_name FROM daily_game WHERE game_date = %s LIMIT 1"
)
