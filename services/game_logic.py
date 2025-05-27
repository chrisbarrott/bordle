import json
import math
import random

from services.game_get_data import get_border_options, get_country_shape, get_shapes

# Load border map once
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)

# Load GeoJSON shapes once
with open("data/countries_shapes.json", "r", encoding="utf-8") as f:
    geojson_data = json.load(f)


def reset_game(session):
    session.clear()


# def initialize_game(session):
#     # session["country_name"] = "France"
#     session["country_name"] = random.choice(list(border_map.keys()))
#     session["remaining_guesses"] = 5
#     session["correct_guesses"] = []
#     session["wrong_guesses"] = []
#     session["correct_seas"] = []

#     # set all the dropdown options
#     all_options = {name for borders in border_map.values() for name in country.get("borders", [])}
#     session["available_options"] = sorted(all_options)

#     # add sea data
#     all_seas = {sea for country in border_map.values() for sea in country.get("seas", [])}
#     session["available_seas"] = sorted(all_seas)


def initialize_game(session):
    session["country_name"] = random.choice(list(border_map.keys()))
    session["remaining_guesses"] = 5
    session["correct_guesses"] = []
    session["wrong_guesses"] = []
    session["correct_seas"] = []

    # Correctly extract all countries from "borders"
    all_border_options = set()
    all_seas = set()

    for entry in border_map.values():
        all_border_options.update(entry.get("borders", []))
        all_seas.update(entry.get("seas", []))

    session["available_borders"] = sorted(all_border_options)
    session["available_seas"] = sorted(all_seas)

    print("All borders:", session["available_borders"])
    print("All seas:", session["available_seas"])


def normalize(name):
    return name.lower().strip()


def process_guess(guess, session):
    guess = guess.strip()
    country = session["country_name"]
    data = border_map.get(country, {})
    correct_borders = data.get("borders", [])
    correct_seas = data.get("seas", [])

    # Remove guess from options
    if guess in session.get("available_options", []):
        session["available_options"].remove(guess)
    if guess in session.get("available_seas", []):
        session["available_seas"].remove(guess)

    if guess in correct_borders:
        if guess not in session["correct_guesses"]:
            session["correct_guesses"].append(guess)
    elif guess in correct_seas:
        if guess not in session["correct_seas"]:
            session["correct_seas"].append(guess)
    else:
        if guess not in session["wrong_guesses"]:
            session["wrong_guesses"].append(guess)
            session["remaining_guesses"] -= 1

    print("Correct guesses:", session["correct_borders"])
    print("Correc sea guess:", session["correct_seas"])
    print("Wrong guesses:", session["wrong_guesses"])


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


def process_country_guess(guess, session):
    guess = guess.strip()
    correct_borders = border_map.get(session["country_name"], {}).get("borders", [])

    if guess in correct_borders and guess not in session["correct_borders"]:
        session["correct_borders"].append(guess)
    elif guess not in correct_borders and guess not in session["wrong_guesses"]:
        session["wrong_guesses"].append(guess)
        session["remaining_guesses"] -= 1


def process_sea_guess(guess, session):
    guess = guess.strip()
    correct_seas = border_map.get(session["country_name"], {}).get("seas", [])

    if guess in correct_seas and guess not in session["correct_seas"]:
        session["correct_seas"].append(guess)
    elif guess not in correct_seas and guess not in session["wrong_guesses"]:
        session["wrong_guesses"].append(guess)
        session["remaining_guesses"] -= 1


def get_game_state(session):
    # set country name
    country_name = session.get("country_name")

    # border_options = get_border_options(session)
    country_data = border_map.get(country_name, {})    
    country_geojson = get_country_shape(country_name)
    hard_mode = session.get("hard_mode", False)

    # gather guesses
    correct_borders = session.get("correct_guesses", [])
    remaining_guesses = session.get("remaining_guesses", 0)
    wrong_guesses = session.get("wrong_guesses", [])

    # gather border data
    border_names = border_map.get(country_name, [])
    border_options = session.get("available_borders", [])
    expected_borders = country_data.get("borders", [])
    expected_seas = country_data.get("seas", [])

    # gather sea data
    correct_seas = session.get("correct_seas", [])
    expected_seas = country_data.get("seas", [])
    sea_options = session.get("available_seas", [])
    sea_shapes = get_shapes(session.get("correct_seas", []))

    # Map shapes based on current guesses
    correct_shapes = get_shapes(correct_borders)
    wrong_shapes = get_shapes(wrong_guesses)

    # game over logic
    game_over = (
        remaining_guesses <= 0
        or set(correct_borders) == set(expected_borders)
        and set(correct_seas) == set(expected_seas)
    )

    # If game is over, show all correct answers in the final map
    final_shapes = get_shapes(border_names) if game_over else []

    return {
        "all_correct": expected_borders + expected_seas,
        "attempts_left": remaining_guesses,
        "border_count": len(border_names),
        "border_options": border_options,
        "correct_seas": correct_seas,
        "correct_borders": correct_borders,
        "correct_count": len(correct_borders + correct_seas),
        "correct_borders": correct_borders,
        "correct_shapes": correct_shapes,
        "country_geojson": country_geojson,
        "country_name": country_name,
        "final_shapes": final_shapes,
        "game_over": game_over,
        "hard_mode": hard_mode,
        "sea_options": sea_options,
        "sea_shapes": sea_shapes,
        "wrong_guesses": wrong_guesses,
        "wrong_shapes": wrong_shapes,
    }


# def get_border_options(session):
#     guessed = set(session.get("correct_guesses", []) + session.get("wrong_guesses", []))
#     return [opt for opt in session.get("available_options", []) if opt not in guessed]


# def get_correct_answers(session):
#     return border_map.get(session.get("country_name"), [])


# def load_geojson():
#     return geojson_data


# def get_country_shape(name):
#     return next(
#         (f for f in geojson_data["features"] if f["properties"].get("name") == name),
#         None,
#     )


# def get_shapes(names):
#     return [f for f in geojson_data["features"] if f["properties"].get("name") in names]
