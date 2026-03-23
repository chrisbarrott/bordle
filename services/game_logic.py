from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import request, session

import json
import math
import os
import smtplib
import uuid
from zoneinfo import ZoneInfo

from services.game_cache import daily_game_cache
from services.game_db_logic import (
    create_game_state_row,
    load_game_state,
    upsert_game_state,
    record_postgres_game_stats,
    record_postgres_country_stats,
    record_postgres_player_stats,
)
from services.game_get_data import (
    get_country_shape,
    get_shapes,
    get_user_ip,
    get_user_location,
)
from services.game_logger import setup_logger

# Setup logger
logger = setup_logger()
UK_TZ = ZoneInfo("Europe/London")


def _uk_today_str() -> str:
    from datetime import datetime

    return datetime.now(UK_TZ).date().isoformat()


def _is_game_won(correct_guesses, border_names) -> bool:
    return set(correct_guesses) == set(border_names)


def _derive_game_result(game_over: bool, is_win: bool) -> str:
    if is_win:
        return "Win"
    if game_over:
        return "Loss"
    return "In progress"

# Load border map once
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)

# Load dropdown options once to avoid repeated file I/O on each request.
with open("static/map_data/country_drop_down.json", "r", encoding="utf-8") as f:
    all_country_options = sorted(json.load(f))


def _get_today_country_name():
    country_info = daily_game_cache.country_info
    if country_info and isinstance(country_info, dict):
        return country_info.get("country_name") or country_info.get("country_code")
    return country_info


def _get_player_location(session):
    player_data = session.get("player_data")
    if not player_data:
        user_ip = get_user_ip()
        player_data = get_user_location(user_ip)
        session["player_data"] = player_data

    return player_data if isinstance(player_data, tuple) else tuple(player_data)


# Game init
def initialize_game(session, player_uid=None):
    # Resolve from explicit arg first, then cookie/session fallbacks.
    player_uid = _resolve_player_uid(session, player_uid)
    if player_uid:
        session["player_uid"] = player_uid

    country_name = _get_today_country_name()
    session["country_name"] = country_name
    session["game_number"] = daily_game_cache.game_number
    session["game_date"] = _uk_today_str()

    # Keep only lightweight UI/session values.
    session["show_border_lines"] = session.get("show_border_lines", False)
    session["borders_hint_declined"] = session.get("borders_hint_declined", False)
    _get_player_location(session)

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


def _resolve_player_uid(session, explicit_player_uid=None):
    if explicit_player_uid:
        return explicit_player_uid
    return request.cookies.get("player_uid") or session.get("player_uid")


def process_guess(guess, session):
    player_uid = _resolve_player_uid(session)
    country_name = _get_today_country_name()
    if not player_uid or not country_name:
        return

    persisted_state = load_game_state(player_uid)
    if not persisted_state:
        persisted_state = create_game_state_row(
            player_uid,
            hard_mode=session.get("hard_mode", False),
            game_number=session.get("game_number", daily_game_cache.game_number),
        )
    if not persisted_state:
        return

    if persisted_state.get("game_over"):
        logger.info(f"Guess ignored for completed game: player_uid={player_uid}")
        return

    guess_history = list(persisted_state.get("guess_history", []))
    wrong_guesses = list(persisted_state.get("wrong_guesses", []))
    guessed_main_country = bool(persisted_state.get("guessed_main_country", False))
    game_result_recorded = bool(persisted_state.get("game_result_recorded", False))
    player_stats_recorded = bool(persisted_state.get("player_stats_recorded", False))
    leaderboard_recorded = bool(persisted_state.get("leaderboard_recorded", False))
    hard_mode = bool(persisted_state.get("hard_mode", session.get("hard_mode", False)))
    correct_borders = border_map.get(country_name, [])

    # Hard mode: if guessing the correct country
    if hard_mode:
        correct_country = normalize(country_name)
        if guess.lower() == correct_country.lower():
            guessed_main_country = True
            upsert_game_state(
                player_uid=player_uid,
                guess_history=guess_history,
                wrong_guesses=wrong_guesses,
                guessed_main_country=guessed_main_country,
                hard_mode=hard_mode,
                game_over=False,
                game_result_recorded=game_result_recorded,
                player_stats_recorded=player_stats_recorded,
                leaderboard_recorded=leaderboard_recorded,
                game_result="In progress",
                game_number=session.get("game_number", daily_game_cache.game_number),
            )
            return

    if guess not in guess_history:
        guess_history.append(guess)
        if guess not in correct_borders and guess not in wrong_guesses:
            wrong_guesses.append(guess)

    correct_guesses = [g for g in guess_history if g in correct_borders]
    remaining_guesses = max(0, 5 - len(guess_history))
    is_win = _is_game_won(correct_guesses, correct_borders)

    game_over_now = remaining_guesses <= 0 or is_win

    # Store result in Postgres as the gameplay source of truth
    upsert_game_state(
        player_uid=player_uid,
        guess_history=guess_history,
        wrong_guesses=wrong_guesses,
        guessed_main_country=guessed_main_country,
        hard_mode=hard_mode,
        game_over=game_over_now,
        game_result_recorded=game_result_recorded,
        player_stats_recorded=player_stats_recorded,
        leaderboard_recorded=leaderboard_recorded,
        game_result=_derive_game_result(game_over_now, is_win),
        game_number=session.get("game_number", daily_game_cache.game_number),
    )


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
    player_uid = _resolve_player_uid(session)
    country_name = _get_today_country_name()
    session["country_name"] = country_name

    # Set game number from cache each render.
    game_number = daily_game_cache.game_number
    session["game_number"] = game_number


    # Load persisted game state from Postgres. This is the source of truth for all game progress and stats.
    persisted_state = load_game_state(player_uid)
    if not persisted_state:
        persisted_state = create_game_state_row(
            player_uid,
            hard_mode=session.get("hard_mode", False),
            game_number=game_number,
        )

    persisted_state = persisted_state or {}

    # Populate session with any missing lightweight values for UI logic (without overwriting heavier game state which is sourced from Postgres).
    guess_history = list(persisted_state.get("guess_history", []))
    wrong_guesses = list(persisted_state.get("wrong_guesses", []))
    hard_mode = bool(persisted_state.get("hard_mode", session.get("hard_mode", False)))
    guessed_main_country = bool(persisted_state.get("guessed_main_country", False))
    game_result_recorded = bool(persisted_state.get("game_result_recorded", False))
    player_stats_recorded = bool(persisted_state.get("player_stats_recorded", False))
    leaderboard_recorded = bool(persisted_state.get("leaderboard_recorded", False))
    border_names = border_map.get(country_name, [])
    border_count = len(border_names)
    correct_guesses = [guess for guess in guess_history if guess in border_names]
    borders_remaining = border_count - len(correct_guesses)
    remaining_guesses = max(0, 5 - len(guess_history))
    is_win = _is_game_won(correct_guesses, border_names)
    all_countries = all_country_options
    available_options = [opt for opt in all_countries if opt not in guess_history]

    # In hard mode, remove the main country from options after it's guessed, and always remove it if guessed in normal mode.
    if not hard_mode and country_name in available_options:
        available_options.remove(country_name)
    if hard_mode and guessed_main_country and country_name in available_options:
        available_options.remove(country_name)

    country_geojson = get_country_shape(country_name)
    show_border_lines = session.get("show_border_lines", False)
    borders_hint_declined = session.get("borders_hint_declined", False)
    game_over = bool(persisted_state.get("game_over", False)) or remaining_guesses <= 0 or is_win
    game_result = _derive_game_result(game_over, is_win)
    guess_country = ""

    # Unpack player_data tuple for response fields.
    country, region, city = _get_player_location(session)

    # Map shapes based on current guesses
    correct_shapes = get_shapes(correct_guesses)
    wrong_shapes = get_shapes(wrong_guesses)

    # Record result only once per DB state.
    if game_over:
        did_win = is_win

        # Only record game result and leaderboard stats once per completed game to avoid duplicates on page refresh.
        if not game_result_recorded:
            game_result_recorded = record_postgres_game_stats(did_win)

        # Record player stats independently — only once per completed game.
        if not player_stats_recorded:
            player_stats_recorded = bool(record_postgres_player_stats(did_win, player_uid, country, city))

        # Only record country stats if game result was successfully recorded to ensure consistency between game results and country stats.
        if not leaderboard_recorded:
            leaderboard_recorded = record_postgres_country_stats(did_win, country, region, city)

        # Derive game result for response based on win/loss state.
        game_result = _derive_game_result(game_over=True, is_win=did_win)

    # Update game state in Postgres if game is over.
    if game_over:
        upsert_game_state(
            player_uid=player_uid,
            guess_history=guess_history,
            wrong_guesses=wrong_guesses,
            guessed_main_country=guessed_main_country,
            hard_mode=hard_mode,
            game_over=game_over,
            game_result_recorded=game_result_recorded,
            player_stats_recorded=player_stats_recorded,
            leaderboard_recorded=leaderboard_recorded,
            game_result=game_result,
            game_number=game_number,
        )

    # If game is over, show all correct answers in the final map
    final_shapes = get_shapes(border_names) if game_over else []

    # Log game state for debugging and analytics
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
        "game_result_recorded": game_result_recorded,
        "player_stats_recorded": player_stats_recorded,
        "leaderboard_recorded": leaderboard_recorded,
        "game_over": game_over,
        "game_number": game_number,
        "guess_country": guess_country,
        "guess_history": guess_history,
        "guessed_main_country": guessed_main_country,
        "hard_mode": hard_mode,
        "player_country": country,
        "player_region": region,
        "player_city": city,
        "show_border_lines": show_border_lines,
        "wrong_guesses": wrong_guesses,
        "player_uid": player_uid,
    }
    logger.info(json.dumps({"event": "game_state", **game_state}))

    # Build response state for frontend rendering
    response_state = dict(game_state)
    response_state.update(
        {
            "all_countries": all_countries,
            "border_options": available_options,
            "correct_shapes": correct_shapes,
            "country_geojson": country_geojson,
            "final_shapes": final_shapes,
            "wrong_shapes": wrong_shapes,
        }
    )
    return response_state
