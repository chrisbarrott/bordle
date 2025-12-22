from datetime import date
import json
import math
import uuid

from services.game_database_connections import (
    get_game_number,
    get_today_country,
    init_db,
    record_game_result,
    record_world_leaderboard_result,
)
from services.game_get_data import (
    get_all_drop_down_options,
    get_border_options,
    get_country_shape,
    get_shapes,
    get_user_ip,
    get_user_location,
)
from services.game_logger import setup_logger

# Setup logger
logger = setup_logger()

# Load border map once
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)

# Load GeoJSON shapes once
with open("data/countries_shapes.json", "r", encoding="utf-8") as f:
    geojson_data = json.load(f)


# Game init
def initialize_game(session):
    # Build database if required
    init_db()

    # Set today so we can run a new init each day
    session["game_date"] = str(date.today())

    # Pull todays game from SQL
    session["country_name"] = get_today_country()

    # Assign a temp UID for the player if not already set
    if "player_uid" not in session:
        session["player_uid"] = str(uuid.uuid4())
        logger.info(f"Assigned new player UID: {session['player_uid']}")

    # Saved for testing
    # session["country_name"] = random.choice(list(border_map.keys()))

    # Set the guesses
    session["correct_guesses"] = []
    session["wrong_guesses"] = []

    # get all countries for drop down list
    all_countries = get_all_drop_down_options()

    session["available_options"] = sorted(all_countries)
    session["all_countries"] = sorted(all_countries)

    # Set hard_mode
    hard_mode = session.get("hard_mode", False)
    
    # Set show border lines
    session["show_border_lines"] = borders_enabled_for_today(session)

    # Remove the main country from options if not in hard mode
    if not hard_mode:
        if session["country_name"] in session["available_options"]:
            session["available_options"].remove(session["country_name"])

    correct_borders = border_map[session["country_name"]]
    session["border_count"] = len(correct_borders)  # Total borders
    session["borders_remaining"] = len(
        correct_borders
    )  # Will decrement as user guesses

    # Set the game attempts logic
    session["remaining_guesses"] = 5
    session["game_result_recorded"] = False
    session["game_result"] = "Started"

    # Set game number for session handling
    session["game_number"] = get_game_number()
    logger.info(
        f"Initialized game #{session['game_number']} for player {session['player_uid']}"
    )

    # Get the IP and lookup location
    session["user_ip"] = get_user_ip()
    session["player_data"] = get_user_location(session["user_ip"])
    # logger.info(f"Player playing from location: {session['location']}")
    # logger.info(json.dumps({"player_location": session["player_data"]}))


# Game reset (hidden)
def reset_game(session):
    session.clear()


def normalize(name):
    return name.lower().strip()


def process_guess(guess, session):
    # Always sort before rendering
    dropdown_options = sorted(session["available_options"])

    # Set the guess
    session["guess_country"] = guess

    # Remove guess from available options and sort
    if guess in dropdown_options:
        session["available_options"].remove(guess)
        session["available_options"] = sorted(session["available_options"])

    # Check if guess is correct or not
    country_name = session["country_name"]

    # Hard mode: if guessing the correct country
    if session.get("hard_mode", True):
        correct_country = normalize(session.get("country_name", ""))
        if guess.lower() == correct_country.lower():
            session["guessed_main_country"] = True

            # Remove from available options
            if session["country_name"] in session.get("available_options", []):
                session["available_options"].remove(session["country_name"])
            return

    if guess in border_map.get(country_name, []):
        if guess not in session["correct_guesses"]:
            session["correct_guesses"].append(guess)
            session["borders_remaining"] -= 1  # Decrease borders remaining
    else:
        if guess not in session["wrong_guesses"]:
            session["wrong_guesses"].append(guess)
            session["remaining_guesses"] -= 1

    # Track guesses in order
    if "guess_history" not in session:
        session["guess_history"] = []

    # Add guess in order for share functionality
    if guess not in session["guess_history"]:
        session["guess_history"].append(guess)


def allowed_attempts_perc(n_borders):
    # Never allow more than 75% of correct answers
    return max(1, round(n_borders * 0.6))


def allowed_attempts_fixed(n_borders):
    # Tiered system
    if n_borders <= 2:
        return 1
    elif n_borders <= 4:
        return 2
    elif n_borders <= 6:
        return 3
    elif n_borders <= 8:
        return 4
    else:
        return 5


def allowed_attempts_scaling(n_borders):
    # Logarithmic Scaling
    return max(1, math.floor(math.log2(n_borders + 1)))


def borders_enabled_for_today(session):
    borders = session.get("show_border_lines")

    if not borders:
        return False

    return (
        borders.get("enabled") is True and
        borders.get("game_number") == get_game_number()
    )


def get_game_state(session):
    # set game number
    game_number = get_game_number()
    session["game_number"] = game_number

    # get the country name
    country_name = session.get("country_name")

    all_countries = session.get("all_countries")
    available_options = get_border_options(session)
    border_names = border_map.get(country_name, [])
    borders_remaining = session.get("borders_remaining", 0)
    border_count = session.get("border_count", 0)
    correct_guesses = session.get("correct_guesses", [])
    country_geojson = get_country_shape(country_name)
    hard_mode = session.get("hard_mode", False)
    show_border_lines = session.get("show_border_lines", False)
    remaining_guesses = session.get("remaining_guesses", 0)
    wrong_guesses = session.get("wrong_guesses", [])
    guessed_main_country = session.get("guessed_main_country")
    game_result_recorded = session.get("game_result_recorded", False)
    guess_history = session.get("guess_history", [])  # FIXED: no tuple
    game_over = session.get("game_over", False)
    game_result = session.get("game_result", "In progress")
    guess_country = session.get("guess_country", "")
    player_uid = session.get("player_uid", "Unknown")

    # Unpack player_data tuple into session for easy access
    country, region, city = session.get(
        "player_data", ("Unknown", "Unknown", "Unknown")
    )
    session["player_country"] = country
    session["player_region"] = region
    session["player_city"] = city

    # Map shapes based on current guesses
    correct_shapes = get_shapes(correct_guesses)
    wrong_shapes = get_shapes(wrong_guesses)

    game_over = remaining_guesses <= 0 or set(correct_guesses) == set(border_names)

    # Record result only once per session
    if game_over and game_result_recorded is False:
        logger.info(
            f"Game over: {game_over} and result recorded: {game_result_recorded}"
        )
        if set(correct_guesses) == set(border_names):
            # Update world leaderboard first (idempotent check), then record aggregated game result
            record_world_leaderboard_result(True, session.get("player_uid"))

            # record game result second (to ensure accurate remaining guesses)
            record_game_result(True, remaining_guesses, session.get("player_uid"))

            # Update session game result
            game_result = "Win"
            session["game_result"] = game_result

        elif remaining_guesses <= 0:
            # Update world leaderboard first (idempotent check), then record aggregated game result
            record_world_leaderboard_result(False, session.get("player_uid"))

            # record game result second (to ensure accurate remaining guesses)
            record_game_result(False, remaining_guesses, session.get("player_uid"))

            # Update session game result
            game_result = "Loss"
            session["game_result"] = game_result

        # Mark as recorded
        session["game_result_recorded"] = True
        game_result_recorded = True
        logger.debug("Setting game_result_recorded to True")

    else:
        logger.info(f"Game over: {game_over} or result recorded: {game_result_recorded}")
        game_result = session.get("game_result", "In progress")

    # If game is over, show all correct answers in the final map
    final_shapes = get_shapes(border_names) if game_over else []

    game_state = {
        "all_correct": border_names,
        "attempts_left": remaining_guesses,
        "border_count": border_count,
        "borders_remaining": borders_remaining,
        "correct_count": len(correct_guesses),
        "correct_guesses": correct_guesses,
        "country_name": country_name,
        "game_result": game_result,
        "game_result_recorded": session["game_result_recorded"],
        "game_over": game_over,
        "game_number": game_number,
        "guess_country": guess_country,
        "guess_history": guess_history,
        "guessed_main_country": guessed_main_country,
        "hard_mode": hard_mode,
        "player_country": session["player_country"],
        "player_region": session["player_region"],
        "player_city": session["player_city"],
        "player_uid": player_uid,
        "show_border_lines": show_border_lines,
        "wrong_guesses": wrong_guesses,
    }

    # Only log game state if not an invalid session
    skip_log = game_over and game_result == "Started"
    if skip_log:
        logger.info("Skipped logging for game over and game started")
    else:
        # Valid session, log full game state
        logger.info(json.dumps(game_state))

    return {
        "all_correct": border_names,
        "all_countries": all_countries,
        "attempts_left": remaining_guesses,
        "border_count": border_count,
        "border_options": available_options,
        "borders_remaining": borders_remaining,
        "correct_count": len(correct_guesses),
        "correct_guesses": correct_guesses,
        "correct_shapes": correct_shapes,
        "country_geojson": country_geojson,
        "country_name": country_name,
        "final_shapes": final_shapes,
        "game_result": game_result,
        "game_result_recorded": session["game_result_recorded"],
        "game_over": game_over,
        "game_number": game_number,
        "guess_country": guess_country,
        "guess_history": guess_history,
        "guessed_main_country": guessed_main_country,
        "hard_mode": hard_mode,
        "show_border_lines": show_border_lines,
        "wrong_guesses": wrong_guesses,
        "wrong_shapes": wrong_shapes,
        "player_country": session["player_country"],
        "player_region": session["player_region"],
        "player_city": session["player_city"],
        "player_uid": player_uid,
    }
