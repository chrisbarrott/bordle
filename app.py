# app.py
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from services.game_logic import (
    initialize_game,
    get_game_state,
    process_guess,
    reset_game,
)
import json

app = Flask(__name__)
app.secret_key = "supersecret"  # Set securely in production

with open("static/map_data/border_map.json") as f:
    border_map = json.load(f)


@app.route("/")
def index():
    if "country_name" not in session:
        initialize_game(session)

    game_state = get_game_state(session)

    return render_template("index.html", **game_state)


@app.route("/submit", methods=["POST"])
def submit():
    guess = request.form.get("guess", "").strip()
    if "available_options" not in session:
        return redirect(url_for("index"))

    process_guess(guess, session)
    return redirect(url_for("index"))


@app.route("/border-data/<country>")
def border_data(country):
    geometry = border_map.get(country)
    return jsonify(geometry or {})


@app.route("/reset")
def reset_session():
    reset_game(session)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
