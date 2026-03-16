from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import request, session

import json
import math
import os
import smtplib
import uuid

from services.game_database_connections import (
    init_db,
    load_daily_game_state,
    record_game_result,
    record_world_leaderboard_result,
    save_daily_game_state,
)
from services.game_cache import daily_game_cache
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
def initialize_game(session, player_uid=None):
    # Build database if required
    init_db()

    # Set today so we can run a new init each day
    session["game_date"] = str(date.today())

    # Use cookie-based player UID if not passed in
    if not player_uid:
        player_uid = request.cookies.get("player_uid")

    # Pull today's game data
    country_info = daily_game_cache.country_info
    if country_info and isinstance(country_info, dict):
        session["country_name"] = country_info.get("country_name") or country_info.get("country_code")
    else:
        # Fallback to previous value or None
        session["country_name"] = country_info

    session["game_number"] = daily_game_cache.game_number

    today = str(date.today())
    session["game_date"] = today

    # --- Check for in-progress game first ---
    in_progress = load_daily_game_state(player_uid)
    if in_progress:
        # Guess history
        session["guess_history"] = in_progress["guess_history"]
        session["wrong_guesses"] = in_progress["wrong_guesses"]
        session["game_over"] = in_progress["game_over"]

        # Recompute derived fields
        correct_borders = border_map[session["country_name"]]
        session["correct_guesses"] = [
            guess for guess in session["guess_history"] if guess in correct_borders
        ]
        session["borders_remaining"] = len(correct_borders) - len(session["correct_guesses"])
        session["remaining_guesses"] = 5 - len(session["guess_history"])
        session["game_result"] = (
            "Won" if session["game_over"] and set(session["correct_guesses"]) == set(correct_borders)
            else "Started"
        )
        session["hard_mode"] = in_progress.get("hard_mode", False)
        session["game_result_recorded"] = in_progress.get("game_result_recorded", False)
        session["guessed_main_country"] = in_progress.get("guessed_main_country", False)

    else:
        # No in-progress game, start fresh
        correct_borders = border_map[session["country_name"]]
        session["borders_remaining"] = len(correct_borders)
        session["remaining_guesses"] = 5

        # Game result tracking
        session["game_result_recorded"] = False
        session["game_result"] = "Started"
        session["game_over"] = False

        # Initialize guess lists
        session["correct_guesses"] = []
        session["wrong_guesses"] = []
        session["guessed_main_country"] = False

    # Default session values for a new game
    session["available_options"] = sorted(get_all_drop_down_options())
    session["all_countries"] = session["available_options"].copy()
    session["show_border_lines"] = session.get("show_border_lines", False)
    session["borders_hint_declined"] = False
    correct_borders = border_map[session["country_name"]]
    session["border_count"] = len(correct_borders)

    # Player IP info
    session["user_ip"] = get_user_ip()
    session["player_data"] = get_user_location(session["user_ip"])#

    hard_mode = session.get("hard_mode", False)
    if not hard_mode:
        if session["country_name"] in session["available_options"]:
            session["available_options"].remove(session["country_name"])
    else:
        # Hard mode: remove main country if already guessed
        if session.get("guessed_main_country") and session["country_name"] in session["available_options"]:
            session["available_options"].remove(session["country_name"])

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

    # Store result in the database
    player_uid = request.cookies.get("player_uid")
    save_daily_game_state(player_uid, False)


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
        borders.get("game_number") == daily_game_cache.game_number
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
    Player UID: {request.cookies.get('player_uid', 'anonymous')}
    Player Country: {session.get('player_country', 'Unknown')}
    Player City: {session.get('player_city', 'Unknown')}
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


def get_game_state(session):
    # set game number
    game_number = daily_game_cache.game_number
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
    borders_hint_declined = session.get("borders_hint_declined", False)
    remaining_guesses = session.get("remaining_guesses", 0)
    wrong_guesses = session.get("wrong_guesses", [])
    guessed_main_country = session.get("guessed_main_country")
    game_result_recorded = session.get("game_result_recorded", False)
    guess_history = session.get("guess_history", [])  # FIXED: no tuple
    game_over = session.get("game_over", False)
    game_result = session.get("game_result", "In progress")
    guess_country = session.get("guess_country", "")

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

    # Get player_uid from cookies if not provided
    player_uid = request.cookies.get("player_uid")
    if game_over:
        save_daily_game_state(player_uid, game_over)

    # Record result only once per session
    if game_over and game_result_recorded is False:
        if set(correct_guesses) == set(border_names):
            # Update world leaderboard first (idempotent check), then record aggregated game result
            record_world_leaderboard_result(True, player_uid)

            # record game result second (to ensure accurate remaining guesses)
            record_game_result(True, remaining_guesses, player_uid)

            # Update session game result
            game_result = "Win"
            session["game_result"] = game_result

        elif remaining_guesses <= 0:
            # Update world leaderboard first (idempotent check), then record aggregated game result
            record_world_leaderboard_result(False, player_uid)

            # record game result second (to ensure accurate remaining guesses)
            record_game_result(False, remaining_guesses, player_uid)

            # Update session game result
            game_result = "Loss"
            session["game_result"] = game_result

        # Mark as recorded
        session["game_result_recorded"] = True
        save_daily_game_state(player_uid, game_over)

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
        "border_hint_declined": borders_hint_declined,
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
    }
