from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import request, session

import json
import math
import os
import smtplib
import uuid

from services.game_database_postgres import (
    get_game_number,
    get_today_country,
    ensure_schema,
    load_daily_game_state,
    record_game_result,
    record_world_leaderboard_result,
    save_daily_game_state,
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
def initialize_game(player_state: dict, player_uid=None):
    # Build database if required
    # Ensure schema exists without running housekeeping cleanup on every request
    ensure_schema()

    # Use cookie-based player UID if not passed in
    if not player_uid:
        player_uid = request.cookies.get("player_uid")

    # Pull today's game data
    player_state["country_name"] = get_today_country()
    player_state["game_number"] = get_game_number()

    today = str(date.today())
    player_state["game_date"] = today

    # --- Check for in-progress game first ---
    in_progress = load_daily_game_state(player_uid)
    if in_progress:
        # Guess history
        player_state["guess_history"] = in_progress["guess_history"]
        player_state["wrong_guesses"] = in_progress["wrong_guesses"]
        player_state["game_over"] = in_progress["game_over"]

        # Recompute derived fields
        correct_borders = border_map[player_state["country_name"]]
        player_state["correct_guesses"] = [
            guess for guess in player_state["guess_history"] if guess in correct_borders
        ]
        player_state["borders_remaining"] = len(correct_borders) - len(
            player_state["correct_guesses"]
        )
        player_state["remaining_guesses"] = 5 - len(player_state["guess_history"])
        player_state["game_result"] = (
            "Won"
            if player_state["game_over"]
            and set(player_state["correct_guesses"]) == set(correct_borders)
            else "Started"
        )
        player_state["hard_mode"] = in_progress.get("hard_mode", False)
        player_state["game_result_recorded"] = in_progress.get("game_result_recorded", False)
        player_state["guessed_main_country"] = in_progress.get("guessed_main_country", False)

    else:
        # No in-progress game, start fresh
        correct_borders = border_map[player_state["country_name"]]
        player_state["borders_remaining"] = len(correct_borders)
        player_state["remaining_guesses"] = 5

        # Game result tracking
        player_state["game_result_recorded"] = False
        player_state["game_result"] = "Started"
        player_state["game_over"] = False

        # Initialize guess lists
        player_state["correct_guesses"] = []
        player_state["wrong_guesses"] = []
        player_state["guessed_main_country"] = False

    # Default values for a new game
    player_state["available_options"] = sorted(get_all_drop_down_options())
    player_state["all_countries"] = player_state["available_options"].copy()
    player_state["show_border_lines"] = player_state.get("show_border_lines", False)
    player_state["borders_hint_declined"] = False
    correct_borders = border_map[player_state["country_name"]]
    player_state["border_count"] = len(correct_borders)

    # Player IP info
    player_state["user_ip"] = get_user_ip()
    player_state["player_data"] = get_user_location(player_state["user_ip"])  #

    hard_mode = player_state.get("hard_mode", False)
    if not hard_mode:
        if player_state["country_name"] in player_state["available_options"]:
            player_state["available_options"].remove(player_state["country_name"])
    else:
        # Hard mode: remove main country if already guessed
        if (
            player_state.get("guessed_main_country")
            and player_state["country_name"] in player_state["available_options"]
        ):
            player_state["available_options"].remove(player_state["country_name"])

    logger.info(f"Game initialized for player {player_uid}")


# Cookie to track player UID
def get_or_create_player_uid():
    uid = request.cookies.get("player_uid")

    if uid:
        return uid, False

    return str(uuid.uuid4()), True


# Game reset (hidden)
def reset_game(session):
    session.clear()


def normalize(name):
    return name.lower().strip()


def process_guess(guess, player_state: dict):
    # Always sort before rendering
    dropdown_options = sorted(player_state.get("available_options", []))

    # Set the guess
    player_state["guess_country"] = guess

    # Remove guess from available options and sort
    if guess in dropdown_options:
        player_state["available_options"].remove(guess)
        player_state["available_options"] = sorted(player_state["available_options"])

    # Check if guess is correct or not
    country_name = player_state["country_name"]

    # Hard mode: if guessing the correct country
    if player_state.get("hard_mode", True):
        correct_country = normalize(player_state.get("country_name", ""))
        if guess.lower() == correct_country.lower():
            player_state["guessed_main_country"] = True

            # Remove from available options
            if player_state["country_name"] in player_state.get("available_options", []):
                player_state["available_options"].remove(player_state["country_name"])
            return

    if guess in border_map.get(country_name, []):
        if guess not in player_state["correct_guesses"]:
            player_state["correct_guesses"].append(guess)
            player_state["borders_remaining"] -= 1  # Decrease borders remaining
    else:
        if guess not in player_state["wrong_guesses"]:
            player_state["wrong_guesses"].append(guess)
            player_state["remaining_guesses"] -= 1

    # Track guesses in order
    if "guess_history" not in player_state:
        player_state["guess_history"] = []

    # Add guess in order for share functionality
    if guess not in player_state["guess_history"]:
        player_state["guess_history"].append(guess)

    # Persist in-progress state, but skip this write if the guess ended the game.
    # End-of-game persistence is handled in get_game_state() where result flags are set.
    border_names = border_map.get(country_name, [])
    game_over = player_state.get("remaining_guesses", 0) <= 0 or set(
        player_state.get("correct_guesses", [])
    ) == set(border_names)
    if not game_over:
        player_uid = request.cookies.get("player_uid")
        save_daily_game_state(player_uid, False, state=player_state)


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
        borders.get("enabled") is True
        and borders.get("game_number") == get_game_number()
    )


def send_contact_email(name, email, subject, message):
    """Send contact form submission via email using SMTP"""
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    recipient_email = os.getenv("CONTACT_EMAIL")

    # Skip if email config not set
    if not all([smtp_server, smtp_user, smtp_password, recipient_email]):
        logger.warning("Email configuration not set. Skipping email send.")
        return

    try:
        # Create message
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = recipient_email
        msg["Subject"] = f"Bordle Contact: {subject}"

        # Email body
        body = f"""
    New contact form submission from Bordle:

    Name: {name}
    Email: {email}
    Subject: {subject}

    Message:
    {message}

    ---
    Player UID: {request.cookies.get("player_uid", "anonymous")}
    Player Country: {session.get("player_country", "Unknown")}
    Player City: {session.get("player_city", "Unknown")}
    """
        msg.attach(MIMEText(body, "plain"))

        # Send email
        with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info(f"Contact email sent for subject: {subject}")

    except Exception as e:
        logger.error(f"Error sending contact email: {str(e)}")
        raise



def get_game_state(player_state: dict):
    # set game number
    game_number = get_game_number()
    player_state["game_number"] = game_number

    # get the country name
    country_name = player_state.get("country_name")

    all_countries = player_state.get("all_countries")
    available_options = get_border_options(player_state)
    border_names = border_map.get(country_name, [])
    borders_remaining = player_state.get("borders_remaining", 0)
    border_count = player_state.get("border_count", 0)
    correct_guesses = player_state.get("correct_guesses", [])
    country_geojson = get_country_shape(country_name)
    hard_mode = player_state.get("hard_mode", False)
    show_border_lines = player_state.get("show_border_lines", False)
    borders_hint_declined = player_state.get("borders_hint_declined", False)
    remaining_guesses = player_state.get("remaining_guesses", 0)
    wrong_guesses = player_state.get("wrong_guesses", [])
    guessed_main_country = player_state.get("guessed_main_country")
    game_result_recorded = player_state.get("game_result_recorded", False)
    guess_history = player_state.get("guess_history", [])  # FIXED: no tuple
    game_over = player_state.get("game_over", False)
    game_result = player_state.get("game_result", "In progress")
    guess_country = player_state.get("guess_country", "")

    # Unpack player_data tuple into session for easy access
    country, region, city = player_state.get(
        "player_data", ("Unknown", "Unknown", "Unknown")
    )
    player_state["player_country"] = country
    player_state["player_region"] = region
    player_state["player_city"] = city

    # Map shapes based on current guesses
    correct_shapes = get_shapes(correct_guesses)
    wrong_shapes = get_shapes(wrong_guesses)

    game_over = remaining_guesses <= 0 or set(correct_guesses) == set(border_names)

    # Get player_uid from cookies if not provided
    player_uid = request.cookies.get("player_uid")

    # Record result only once per session
    if game_over and game_result_recorded is False:
        if set(correct_guesses) == set(border_names):
            # Update world leaderboard first (idempotent check), then record aggregated game result
            record_world_leaderboard_result(True, player_uid)

            # record game result second (to ensure accurate remaining guesses)
            record_game_result(True, remaining_guesses, player_uid)

            # Update player_state game result
            game_result = "Win"
            player_state["game_result"] = game_result

        elif remaining_guesses <= 0:
            # Update world leaderboard first (idempotent check), then record aggregated game result
            record_world_leaderboard_result(False, player_uid)

            # record game result second (to ensure accurate remaining guesses)
            record_game_result(False, remaining_guesses, player_uid)

            # Update player_state game result
            game_result = "Loss"
            player_state["game_result"] = game_result

        # Mark as recorded
        player_state["game_result_recorded"] = True

    else:
        logger.info(
            f"Game over: {game_over} or result recorded: {game_result_recorded}"
        )
        game_result = player_state.get("game_result", "In progress")

    # If game is over, show all correct answers in the final map
    final_shapes = get_shapes(border_names) if game_over else []

    game_state = {
        "all_correct": border_names,
        "attempts_left": remaining_guesses,
        "border_count": border_count,
        "borders_remaining": borders_remaining,
        "border_hint_declined": borders_hint_declined,
        "correct_count": len(correct_guesses),
        "correct_guesses": correct_guesses,
        "country_name": country_name,
        "game_result": game_result,
        "game_result_recorded": player_state.get("game_result_recorded", False),
        "game_over": game_over,
        "game_number": game_number,
        "guess_country": guess_country,
        "guess_history": guess_history,
        "guessed_main_country": guessed_main_country,
        "hard_mode": hard_mode,
        "player_country": player_state.get("player_country"),
        "player_region": player_state.get("player_region"),
        "player_city": player_state.get("player_city"),
        "show_border_lines": show_border_lines,
        "wrong_guesses": wrong_guesses,
        "player_uid": player_uid,
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
        "border_hint_declined": borders_hint_declined,
        "correct_count": len(correct_guesses),
        "correct_guesses": correct_guesses,
        "correct_shapes": correct_shapes,
        "country_geojson": country_geojson,
        "country_name": country_name,
        "final_shapes": final_shapes,
        "game_result": game_result,
        "game_result_recorded": player_state.get("game_result_recorded", False),
        "game_over": game_over,
        "game_number": game_number,
        "guess_country": guess_country,
        "guess_history": guess_history,
        "guessed_main_country": guessed_main_country,
        "hard_mode": hard_mode,
        "show_border_lines": show_border_lines,
        "wrong_guesses": wrong_guesses,
        "wrong_shapes": wrong_shapes,
        "player_country": player_state["player_country"],
        "player_region": player_state["player_region"],
        "player_city": player_state["player_city"],
    }
