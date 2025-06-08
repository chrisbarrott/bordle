# app.py
from datetime import date, timedelta
import os
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    send_from_directory,
    url_for,
    session
)
import redis
from flask_session import Session
from services.game_database_connections import (
    get_db_connection,
    get_game_number,
    get_games_today,
    get_total_games,
    record_game_result
)
from services.game_logic import (
    initialize_game,
    get_game_state,
    process_guess,
    reset_game,
)
import json
from dotenv import load_dotenv

app = Flask(__name__)

# Use Redis for session storage
# app.config['SESSION_TYPE'] = 'redis'
# app.config['SESSION_REDIS'] = redis.StrictRedis(host='localhost', port=6379)
# app.config['SESSION_PERMANENT'] = True

app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 1 day
app.permanent_session_lifetime = timedelta(seconds=86400)  # Also works

# Secret key for session signing (keep this constant across deploys)
app.secret_key = os.getenv('FLASK_SECRET_KEY')  # Set securely in production

load_dotenv()

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

    # Set game number for session handling and stats
    game_number = get_game_number()
    games_today, today_success_rate = get_games_today()
    total_games = get_total_games()

    # Add the stats props
    # stats = get_player_stats(session)
    # game_state = get_game_state(session)
    bordle_stats = analytics()

    return render_template(
        "landing.html",
        # stats=stats,
        bordle_stats=bordle_stats,
        game_number=game_number,
        games_today=games_today,
        total_games=total_games,
        today_success_rate=today_success_rate
    )


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
    # init the game if a new day
    today = str(date.today())
    if "game_date" not in session or session["game_date"] != today:
        initialize_game(session)

    # First time or GET
    if "country_name" not in session:
        initialize_game(session)

    # If form posted a guess
    if request.method == "POST":
        guess = request.form.get("guess", "").strip()
        process_guess(guess, session)
        return redirect(url_for("game"))

    # Set the game session
    game_state = get_game_state(session)

    # Set game number for session handling and stats
    games_today, today_success_rate = get_games_today()
    total_games = get_total_games()

    # Add the stats props
    # stats = get_player_stats(session)
    bordle_stats = analytics()

    return render_template(
        "index.html",
        **game_state,
        # stats=stats,
        iso_map=iso_map,
        bordle_stats=bordle_stats,
        games_today=games_today,
        total_games=total_games,
        today_success_rate=today_success_rate
    )


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


@app.route("/sitemap.xml")
def sitemap():
    return send_from_directory("static", "sitemap.xml")


@app.route("/robots.txt")
def robots():
    return send_from_directory("static", "robots.txt")


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


@app.route("/analytics")
def analytics():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get today's stats
    cursor.execute("SELECT successes, failures FROM game_stats WHERE game_date = DATE('now', 'localtime')")
    row = cursor.fetchone()
    successes_today, failures_today = row if row else (0, 0)

    games_today = successes_today + failures_today
    success_rate = round(successes_today / games_today * 100, 2) if games_today > 0 else 0.0

    # Get total successes and failures across all time
    cursor.execute("SELECT SUM(successes), SUM(failures) FROM game_stats")
    row = cursor.fetchone()
    total_successes, total_failures = row if row else (0, 0)

    total_games = (total_successes or 0) + (total_failures or 0)

    conn.close()

    return {
        'games_today': games_today,
        'total_games': total_games,
        'success_rate': success_rate
    }


# @app.route('/api/game-result', methods=['POST'])
# def api_record_game_result():
#     data = request.json
#     success = data.get('success', False)
#     record_game_result(success)
#     return jsonify({"status": "success"})


@app.route("/api/stats")
def api_stats():
    stats = analytics()
    return jsonify(stats)


if __name__ == "__main__":
    if os.getenv("FLASK_ENV") == "development":
        app.run(debug=True)
