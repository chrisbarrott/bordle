# app.py
from datetime import date, timedelta
import os
import uuid
from flask import (
    Flask,
    jsonify,
    make_response,
    render_template,
    request,
    redirect,
    send_file,
    send_from_directory,
    url_for,
    session,
)
from services.game_database_connections import (
    get_db_connection,
    get_game_number,
    get_games_today,
    get_leaderboard_data,
    get_total_games,
)
from services.game_logic import (
    get_or_create_player_uid,
    initialize_game,
    get_game_state,
    process_guess,
    reset_game,
)
import json
from dotenv import load_dotenv
from services.game_logger import setup_logger
import mimetypes


# Setup logger
logger = setup_logger()

# Setup Flask app
app = Flask(__name__)

# Ensure .geojson files are served with a geo+json MIME type
mimetypes.add_type('application/geo+json', '.geojson')

# Session configuration
app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 1 day
app.permanent_session_lifetime = timedelta(seconds=86400)  # Also works

# Secret key for session signing (keep this constant across deploys)
app.secret_key = os.getenv("FLASK_SECRET_KEY")  # Set securely in production

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
    bordle_stats = analytics()

    return render_template(
        "landing.html",
        # stats=stats,
        bordle_stats=bordle_stats,
        game_number=game_number,
        games_today=games_today,
        total_games=total_games,
        today_success_rate=today_success_rate,
    )


# Handle mode toggle and start game
@app.route("/set_mode_and_play", methods=["POST"])
def set_mode_and_play():
    # hard_mode checkbox is only present if checked
    session["hard_mode"] = bool(request.form.get("hard_mode"))
    
    # show borders option
    session["show_border_lines"] = bool(request.form.get("show_border_lines"))
    logger.info(f"Set show_border_lines to {session['show_border_lines']} in session.")

    # show borders option
    session["border_hint_declined"] = False
    logger.info("Set border_hint_declined to False in session.")

    # Only initialize the game if it hasn't already started
    if "country_name" not in session:
        initialize_game(session)

    return redirect(url_for("game"))


@app.route("/check_played", methods=["POST"])
def check_played():
    game_number = get_game_number()

    # You need to track session/game data on the server
    played_games = session.get("played_games", [])

    if game_number in played_games:
        return jsonify({"blockPlay": True})

    # Optionally add it (but might want to do this on victory instead)
    session["played_games"] = played_games + [game_number]

    return jsonify({"blockPlay": False})


@app.route("/api/set_show_borders", methods=["POST"])
def set_show_borders():
    data = request.json
    logger.info("User accepted borders hint")
    session["show_border_lines"] = bool(data["enabled"])
    return jsonify(success=True)


# API endpoint to record that user declined borders hint
@app.route("/api/borders_hint_declined", methods=["POST"])
def borders_hint_declined():
    logger.info("User declined borders hint")
    session["borders_hint_declined"] = True
    return jsonify(ok=True)


# Main game page
@app.route("/game", methods=["GET", "POST"])
def game():
    # Get or create player UID (cookie-based)
    player_uid, is_new_player = get_or_create_player_uid()

    # init the game if a new day
    today = str(date.today())

    if "game_date" not in session or session["game_date"] != today:
        initialize_game(session, player_uid)

    # First time or GET
    if "country_name" not in session:
        session["hard_mode"] = bool(request.form.get("hard_mode"))
        session["show_border_lines"] = bool(request.form.get("show_border_lines"))
        logger.info(f"Set show_border_lines to {session['show_border_lines']} in session.")
        initialize_game(session)

    # If form posted a guess
    if request.method == "POST":
        guess = request.form.get("guess", "").strip()
        process_guess(guess, session)
        return redirect(url_for("game"))

    # Build game state
    game_state = get_game_state(session)
    games_today, today_success_rate = get_games_today()
    total_games = get_total_games()
    bordle_stats = analytics()

    # logger.info(f"game_state keys: {game_state.keys()}")

    # Render template
    resp = make_response(
        render_template(
            "index.html",
            **game_state,
            iso_map=iso_map,
            player_uid=player_uid,
            bordle_stats=bordle_stats,
            games_today=games_today,
            total_games=total_games,
            today_success_rate=today_success_rate,
            borders_hint_declined=session.get("borders_hint_declined", False),
        )
    )

    # Set cookie ONLY if new
    if is_new_player:
        resp.set_cookie(
            "player_uid",
            player_uid,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            secure=True,
            samesite="Lax"
        )

    return resp

@app.route("/stats")
def stats():
    # Fetch or reuse the same data
    bordle_stats = analytics()
    games_today = get_games_today()
    total_games = get_total_games()
    games_today, today_success_rate = get_games_today()
    game_number = get_game_number()

    return render_template(
        "stats.html",
        bordle_stats=bordle_stats,
        games_today=games_today,
        total_games=total_games,
        today_success_rate=today_success_rate,
        game_number=game_number,
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


@app.route("/leaderboard_data")
def leaderboard_data():
    try:
        data = get_leaderboard_data()
        return jsonify(data)
    except Exception as e:
        logger.warning(f"Error loading leaderboard data: {e}")
        return jsonify({"error": "Failed to load leaderboard data"}), 500


@app.route("/api/leaderboard")
def leaderboard_api():
    return jsonify(get_leaderboard_data())


@app.route("/sitemap.xml")
def sitemap():
    return send_from_directory("static", "sitemap.xml")


@app.route("/robots.txt")
def robots():
    return send_from_directory("static", "robots.txt")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


@app.route("/download_db")
def download_db():
    # Basic auth to protect the database download
    auth = request.authorization
    download_user = os.getenv("DOWNLOAD_DB_USER")
    download_pass = os.getenv("DOWNLOAD_DB_PASSWORD")
    
    # Validate credentials
    if not download_user or not download_pass or not auth or auth.username != download_user or auth.password != download_pass:
        return {"error": "Unauthorized"}, 401, {"WWW-Authenticate": 'Basic realm="Download DB"'}
    
    return send_file("db/games.db", as_attachment=True)


@app.route("/download_csv")
def download_csv():
    return send_file("db/games.csv", as_attachment=True)


@app.route("/analytics")
def analytics():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get today's stats
    cursor.execute(
        "SELECT successes, failures FROM game_stats WHERE game_date = DATE('now', 'localtime')"
    )
    row = cursor.fetchone()
    successes_today, failures_today = row if row else (0, 0)

    games_today = successes_today + failures_today
    success_rate = (
        round(successes_today / games_today * 100, 2) if games_today > 0 else 0.0
    )

    # Get total successes and failures across all time
    cursor.execute("SELECT SUM(successes), SUM(failures) FROM game_stats")
    row = cursor.fetchone()
    total_successes, total_failures = row if row else (0, 0)

    total_games = (total_successes or 0) + (total_failures or 0)

    conn.close()

    return {
        "games_today": games_today,
        "total_games": total_games,
        "success_rate": success_rate,
        "game_number": get_game_number(),
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


# Added observability for WhatsApp share events
@app.route("/api/observability/share", methods=["POST"])
def log_share_event():
    data = request.get_json(force=True)

    whatsapp_share_event = {
        "env": os.getenv("FLASK_ENV", "production"),
        "event": "WHATSAPP_SHARE_EVENT",
        "game_number": data.get("gameNumber"),
        "encoded_message": data.get("result"),
        "game_result": data.get("gameResult"),
        "country_name": session.get("country_name", "unknown"),
        "player_uid": request.cookies.get("player_uid"),
        "player_country": session.get("player_country", "unknown"),
        "player_region": session.get("player_region", "unknown"),
        "player_city": session.get("player_city", "unknown"),
        "hard_mode": session.get("hard_mode", False),
    }
    logger.info(json.dumps(whatsapp_share_event))

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    if os.getenv("FLASK_ENV") == "development":
        app.run(debug=True)
