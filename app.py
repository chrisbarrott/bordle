# app.py
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    send_from_directory,
    url_for,
    session
)
from services.game_logic import (
    initialize_game,
    get_game_state,
    process_guess,
    reset_game,
)
import json

from services.game_stats import get_stats

app = Flask(__name__)
app.secret_key = "supersecret"  # Set securely in production

with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)
# print(border_map.keys())

with open("static/map_data/iso_country_codes.json", "r", encoding="utf-8") as f:
    iso_map = json.load(f)

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
    # hard_mode checkbox is only present if checked
    session["hard_mode"] = bool(request.form.get("hard_mode"))

    # Only initialize the game if it hasn't already started
    if "country_name" not in session:
        initialize_game(session)

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

    return render_template("index.html", **game_state, stats=stats, iso_map=iso_map)


@app.route("/submit", methods=["POST"])
def submit():
    # Handle the guess
    guess = request.form.get("guess", "").strip()

    # handle empty submit
    if guess == "":
        return redirect(url_for("game"))

    if "available_options" not in session:
        return redirect(url_for("index.html"))

    # Use game logic to process the guess
    process_guess(guess, session)
    return redirect(url_for("game"))


@app.route("/reset")
def reset_session():
    reset_game(session)
    return redirect(url_for("landing"))


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


if __name__ == "__main__":
    # Dev
    # app.run(debug=True)

    # Prod
    app.run(host='0.0.0.0', port=10000)