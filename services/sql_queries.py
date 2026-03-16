"""Centralized SQL statements used by the Postgres migration services.

Keep all queries here so it's obvious which SQL is executed against the
new Postgres database.
"""

GET_MAX_GAME_NUMBER = "SELECT MAX(game_number) AS game_number FROM games"
GET_MAX_ID = "SELECT MAX(id) AS game_number FROM games"

GET_DAILY_GAME_BY_DATE = (
    "SELECT country_code, country_name FROM daily_games WHERE game_date = %s LIMIT 1"
)

GET_GAME_BY_NUMBER = (
    "SELECT country_code, country_name FROM games WHERE game_number = %s LIMIT 1"
)
