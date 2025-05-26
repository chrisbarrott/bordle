import json
import math
import random

# Load border map once
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)

# Load GeoJSON shapes once
with open("data/countries_shapes.json", "r", encoding="utf-8") as f:
    geojson_data = json.load(f)


def reset_game(session):
    session.clear()


def initialize_game(session):
    session["country_name"] = random.choice(list(border_map.keys()))
    session["remaining_guesses"] = 5
    session["correct_guesses"] = []
    session["wrong_guesses"] = []
    session["available_options"] = sorted(list(set(sum(border_map.values(), []))))


def normalize(name):
    return name.lower().strip()


def load_geojson():
    return geojson_data


def get_country_shape(name):
    return next(
        (f for f in geojson_data["features"] if f["properties"].get("name") == name),
        None,
    )


def get_shapes(names):
    return [f for f in geojson_data["features"] if f["properties"].get("name") in names]


def process_guess(guess, session):
    # Always sort before rendering
    dropdown_options = sorted(session["available_options"])

    # Remove guess from available options and sort
    if guess in dropdown_options:
        session["available_options"].remove(guess)
        session["available_options"] = sorted(session["available_options"])

    # Check if guess is correct or not
    country_name = session["country_name"]
    if guess in border_map.get(country_name, []):
        if guess not in session["correct_guesses"]:
            session["correct_guesses"].append(guess)
    else:
        if guess not in session["wrong_guesses"]:
            session["wrong_guesses"].append(guess)
            session["remaining_guesses"] -= 1

    print("Correct guesses:", session["correct_guesses"])
    print("Wrong guesses:", session["wrong_guesses"])


def get_border_options(session):
    guessed = set(session.get("correct_guesses", []) + session.get("wrong_guesses", []))
    return [opt for opt in session.get("available_options", []) if opt not in guessed]


def get_correct_answers(session):
    return border_map.get(session.get("country_name"), [])


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
    country_name = session.get("country_name")
    correct_guesses = session.get("correct_guesses", [])
    wrong_guesses = session.get("wrong_guesses", [])
    remaining_guesses = session.get("remaining_guesses", 0)

    available_options = get_border_options(session)
    country_geojson = get_country_shape(country_name)
    border_names = border_map.get(country_name, [])

    # Map shapes based on current guesses
    correct_shapes = get_shapes(correct_guesses)
    wrong_shapes = get_shapes(wrong_guesses)

    game_over = remaining_guesses <= 0 or set(correct_guesses) == set(border_names)

    # If game is over, show all correct answers in the final map
    final_shapes = get_shapes(border_names) if game_over else []

    return {
        "country_name": country_name,
        "border_count": len(border_names),
        "country_geojson": country_geojson,
        "correct_shapes": correct_shapes,
        "wrong_shapes": wrong_shapes,
        "border_options": available_options,
        "attempts_left": remaining_guesses,
        "correct_guesses": correct_guesses,
        "wrong_guesses": wrong_guesses,
        "game_over": game_over,
        "final_shapes": final_shapes,
        "all_correct": border_names,
        "correct_count": len(correct_guesses),
    }
