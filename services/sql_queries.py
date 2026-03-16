"""Centralized SQL statements used by the Postgres migration services.

Keep all queries here so it's obvious which SQL is executed against the
new Postgres database.
"""

GET_MAX_GAME_NUMBER = "SELECT MAX(game_number) AS game_number FROM games"
GET_MAX_ID = "SELECT MAX(id) AS game_number FROM games"
GET_MAX_ROTATION = "SELECT MAX(rotation) AS game_number FROM daily_game"
GET_COUNT_DAILY_GAMES = "SELECT COUNT(DISTINCT game_date) AS game_number FROM daily_game"

GET_DAILY_GAME_BY_DATE = (
    "SELECT country_code, country_name FROM daily_game WHERE game_date = %s LIMIT 1"
)

GET_DAILY_GAME_BY_DATE_WITH_NAME_ONLY = (
    "SELECT NULL::text AS country_code, country_name FROM daily_game WHERE game_date = %s LIMIT 1"
)

GET_DAILY_GAME_BY_DATE_WITH_COUNTRY_ONLY = (
    "SELECT NULL::text AS country_code, country AS country_name FROM daily_game WHERE game_date = %s LIMIT 1"
)

GET_GAME_BY_NUMBER = (
    "SELECT country_code, country_name FROM games WHERE game_number = %s LIMIT 1"
)

GET_GAME_BY_NUMBER_WITH_NAME_ONLY = (
    "SELECT NULL::text AS country_code, country_name FROM games WHERE game_number = %s LIMIT 1"
)

GET_GAME_BY_NUMBER_WITH_COUNTRY_ONLY = (
    "SELECT NULL::text AS country_code, country AS country_name FROM games WHERE game_number = %s LIMIT 1"
)

GET_DAILY_GAME_BY_ROTATION = (
    "SELECT NULL::text AS country_code, country AS country_name FROM daily_game WHERE rotation = %s LIMIT 1"
)
