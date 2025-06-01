import json
import math

from services.game_database_connections import (
    get_today_country,
    init_db,
    record_game_result
)
from services.game_get_data import (
    get_border_options,
    get_country_shape,
    get_shapes
)

# Load border map once
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)

# Load GeoJSON shapes once
with open("data/countries_shapes.json", "r", encoding="utf-8") as f:
    geojson_data = json.load(f)
# print("Shapes: ", geojson_data.keys())


# Game init
def initialize_game(session):
    # Build database if required
    init_db()

    # Pull todays game from SQL
    session["country_name"] = get_today_country()

    # Saved for testing
    # session["country_name"] = random.choice(list(border_map.keys()))

    # Set the guesses
    session["correct_guesses"] = []
    session["wrong_guesses"] = []

    # get all dropdowns from border_map keys
    all_countries = set(border_map.keys())
    for borders in border_map.values():
        all_countries.update(borders)
    session["available_options"] = sorted(all_countries)
    session["all_countries"] = sorted(all_countries)

    # Set hard_mode
    hard_mode = session["hard_mode"]

    # Remove the main country from options if not in hard mode
    if not hard_mode:
        if session["country_name"] in session["available_options"]:
            session["available_options"].remove(session["country_name"])

    correct_borders = border_map[session["country_name"]]
    session["border_count"] = len(correct_borders)  # Total borders
    session["borders_remaining"] = len(correct_borders)  # Will decrement as user guesses

    # Set the game attempts logic
    # session["remaining_guesses"] = allowed_attempts_fixed(session["border_count"])
    session["remaining_guesses"] = 5


# Game reset (hidden)
def reset_game(session):
    session.clear()


def get_all_countries(border_map):
    all_countries = set(border_map.keys())
    return all_countries


def normalize(name):
    return name.lower().strip()


def process_guess(guess, session):
    # Always sort before rendering
    dropdown_options = sorted(session["available_options"])

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


def get_game_state(session):
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
    remaining_guesses = session.get("remaining_guesses", 0)
    wrong_guesses = session.get("wrong_guesses", [])
    guessed_main_country = session.get("guessed_main_country")

    # Map shapes based on current guesses
    correct_shapes = get_shapes(correct_guesses)
    wrong_shapes = get_shapes(wrong_guesses)

    game_over = remaining_guesses <= 0 or set(correct_guesses) == set(border_names)

    # log if gameover
    if game_over is True:
        if remaining_guesses <= 0:
            record_game_result(False)
        if set(correct_guesses) == set(border_names):
            record_game_result(True)

    # If game is over, show all correct answers in the final map
    final_shapes = get_shapes(border_names) if game_over else []

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
        "game_over": game_over,
        "guessed_main_country": guessed_main_country,
        "hard_mode": hard_mode,
        "wrong_guesses": wrong_guesses,
        "wrong_shapes": wrong_shapes,
    }
