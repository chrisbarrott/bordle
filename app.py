# app.py
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session
)
from services.game_logic import (
    initialize_game,
    get_game_state,
    process_guess,
    process_country_guess,
    process_sea_guess,
    reset_game,
)
import json

from services.game_stats import get_stats

app = Flask(__name__)
app.secret_key = "supersecret"  # Set securely in production

with open("static/map_data/border_map.json") as f:
    border_map = json.load(f)


# Landing page
@app.route("/", methods=["GET"])
def landing():
    if "country_name" in session:
        # Session already initialized; just show the landing page
        pass
    else:
        # No session/game in progress
        reset_game(session)  # Optional: ensure clean start if not present

    # Determine if we are running in hard mode
    # hard_mode = session.get("hard_mode", False)

    # Add the stats props
    stats = get_stats(session)
    game_state = get_game_state(session)

    return render_template("landing.html", **game_state, stats=stats)

# Handle mode toggle and start game
@app.route("/set_mode_and_play", methods=["POST"])
def set_mode_and_play():
    # Only initialize the game if it hasn't already started
    if "country_name" not in session:
        initialize_game(session)

    # hard_mode checkbox is only present if checked
    session["hard_mode"] = bool(request.form.get("hard_mode"))

    return redirect(url_for("game"))


# Main game page
@app.route("/game", methods=["GET", "POST"])
def game():
    # If form posted a guess
    if request.method == "POST":
        guess = request.form.get("guess", "").strip()
        process_guess(guess, session)
        return redirect(url_for("game"))

    # First time or GET
    if "country_name" not in session:
        initialize_game(session)

    # Set the game session
    game_state = get_game_state(session)

    # Add the stats props
    stats = get_stats(session)

    return render_template("index.html", **game_state, stats=stats)


# @app.route("/submit", methods=["POST"])
# def submit():
#     # Handle the guess
#     guess = request.form.get("guess", "").strip()
#     if "available_options" not in session:
#         return redirect(url_for("index.html"))

#     # Use game logic to process the guess
#     process_guess(guess, session)
#     return redirect(url_for("game"))


@app.route("/submit", methods=["POST"])
def submit():
    country_guess = request.form.get("country_guess")
    sea_guess = request.form.get("sea_guess")

    # if "available_options" not in session:
    #     return redirect(url_for("index.html"))

    if country_guess:
        process_country_guess(country_guess, session)
    if sea_guess:
        process_sea_guess(sea_guess, session)

    return redirect(url_for("game"))


@app.route("/reset")
def reset_session():
    reset_game(session)
    return redirect(url_for("landing"))


if __name__ == "__main__":
    app.run(debug=True)
