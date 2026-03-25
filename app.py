# app.py

from dotenv import load_dotenv
from datetime import date, datetime, timedelta
import os
from zoneinfo import ZoneInfo

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
from services.game_cache import daily_game_cache
from services.game_db_logic import (
    get_games_today_stats,
    get_leaderboard_data,
    get_total_games_count,
    get_player_stats,
    migrate_player_stats,
)
from services.game_logic import (
    get_or_create_player_uid,
    initialize_game,
    get_game_state,
    process_guess,
    reset_game,
    send_contact_email,
)
import json
from services.game_logger import setup_logger
import mimetypes


# Setup logger
logger = setup_logger()

# Load environment variables from .env file
load_dotenv()

UK_TZ = ZoneInfo("Europe/London")


def _uk_today_str() -> str:
    return datetime.now(UK_TZ).date().isoformat()

def _resolve_player_location_from_session():
    """Return (country, region, city) from session in a backward-compatible way."""
    player_data = session.get("player_data")

    if isinstance(player_data, (list, tuple)) and len(player_data) >= 3:
        return player_data[0], player_data[1], player_data[2]

    if isinstance(player_data, dict):
        return (
            player_data.get("country", "Unknown"),
            player_data.get("region", "Unknown"),
            player_data.get("city", "Unknown"),
        )

    # Fallback for older session shape.
    return (
        session.get("player_country", "Unknown"),
        session.get("player_region", "Unknown"),
        session.get("player_city", "Unknown"),
    )


def get_game_number_from_postgres() -> int:
    return daily_game_cache.game_number

# Setup Flask app
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# Ensure .geojson files are served with a geo+json MIME type
mimetypes.add_type("application/geo+json", ".geojson")

# Session configuration
app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 1 day
app.permanent_session_lifetime = timedelta(seconds=86400)  # Also works

# Load map data once at startup
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)
with open("static/map_data/iso_country_codes.json", "r", encoding="utf-8") as f:
    iso_map = json.load(f)


def _build_game_response(player_uid: str, is_new_player: bool = False):
    game_state = get_game_state(session)
    games_today, today_success_rate = get_games_today_stats()
    total_games = get_total_games_count()
    bordle_stats = analytics()

    resp = make_response(
        render_template(
            "index.html",
            **game_state,
            iso_map=iso_map,
            bordle_stats=bordle_stats,
            games_today=games_today,
            total_games=total_games,
            today_success_rate=today_success_rate,
            borders_hint_declined=session.get("borders_hint_declined", False),
        )
    )

    if is_new_player:
        resp.set_cookie(
            "player_uid",
            player_uid,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            secure=True,
            samesite="Lax",
        )

    return resp

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
    game_number = get_game_number_from_postgres()
    games_today, today_success_rate = get_games_today_stats()
    total_games = get_total_games_count()

    # Add the stats props
    bordle_stats = analytics(game_number=game_number)

    return render_template(
        "landing.html",
        bordle_stats=bordle_stats,
        game_number=game_number,
        games_today=games_today,
        total_games=total_games,
        today_success_rate=today_success_rate,
    )


# Handle mode toggle and start game
@app.route("/set_mode_and_play", methods=["POST"])
def set_mode_and_play():
    player_uid, is_new_player = get_or_create_player_uid()
    
    session["player_uid"] = player_uid
    session["hard_mode"] = bool(request.form.get("hard_mode"))
    session["show_border_lines"] = bool(request.form.get("show_border_lines"))
    session["border_hint_declined"] = False

    resp = make_response(redirect(url_for("game")))

    if is_new_player:
        resp.set_cookie(
            "player_uid",
            player_uid,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            secure=True,
            samesite="Lax",
        )

    return resp


@app.route("/check_played", methods=["POST"])
def check_played():
    game_number = get_game_number_from_postgres()

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
    session["player_uid"] = player_uid

    # init the game if a new day
    today = _uk_today_str()

    if "game_date" not in session or session["game_date"] != today:
        initialize_game(session, player_uid)

    # First time or GET
    if "country_name" not in session:
        session["hard_mode"] = bool(request.form.get("hard_mode"))
        session["show_border_lines"] = bool(request.form.get("show_border_lines"))
        initialize_game(session, player_uid)

    # If form posted a guess
    if request.method == "POST":
        guess = request.form.get("guess", "").strip()
        process_guess(guess, session)
        return _build_game_response(player_uid, is_new_player)

    return _build_game_response(player_uid, is_new_player)


@app.route("/stats")
def stats():
    # Fetch or reuse the same data
    game_number = get_game_number_from_postgres()
    bordle_stats = analytics(game_number=game_number)
    games_today, today_success_rate = get_games_today_stats()
    total_games = get_total_games_count()

    return render_template(
        "stats.html",
        bordle_stats=bordle_stats,
        games_today=games_today,
        total_games=total_games,
        today_success_rate=today_success_rate,
        game_number=game_number,
    )


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/contact/submit", methods=["POST"])
def contact_submit():
    try:
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        # Validate form data
        if not all([name, email, subject, message]):
            return jsonify(
                {"status": "error", "message": "All fields are required"}
            ), 400

        # Log the contact form submission
        contact_event = {
            "event": "CONTACT_FORM_SUBMISSION",
            "name": name,
            "email": email,
            "subject": subject,
            "message": message,
            "timestamp": date.today().isoformat(),
            "player_uid": request.cookies.get("player_uid", "anonymous"),
        }
        logger.info(json.dumps(contact_event))

        # Send email if configured
        try:
            send_contact_email(name, email, subject, message)
        except Exception as e:
            logger.error(f"Failed to send contact email: {str(e)}")
            # Continue anyway - email is optional

        return jsonify(
            {
                "status": "success",
                "message": "Message received! Thank you for your feedback.",
            }
        ), 200

    except Exception as e:
        logger.error(f"Error processing contact form: {str(e)}")
        return jsonify(
            {"status": "error", "message": "An error occurred. Please try again."}
        ), 500


@app.route("/submit", methods=["POST"])
def submit():
    player_uid, is_new_player = get_or_create_player_uid()
    session["player_uid"] = player_uid

    # Handle the guess
    guess = request.form.get("guess", "").strip()

    # handle empty submit
    if guess == "":
        return redirect(url_for("game"))

    if "country_name" not in session:
        initialize_game(session, player_uid)

    # Use game logic to process the guess
    process_guess(guess, session)
    return _build_game_response(player_uid, is_new_player)


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
    if (
        not download_user
        or not download_pass
        or not auth
        or auth.username != download_user
        or auth.password != download_pass
    ):
        return (
            {"error": "Unauthorized"},
            401,
            {"WWW-Authenticate": 'Basic realm="Download DB"'},
        )

    return send_file("db/games.db", as_attachment=True)


@app.route("/download_csv")
def download_csv():
    return send_file("db/games.csv", as_attachment=True)


@app.route("/analytics")
def analytics(game_number=None):
    games_today, success_rate = get_games_today_stats()
    total_games = get_total_games_count()

    if game_number is None:
        game_number = get_game_number_from_postgres()

    return {
        "games_today": games_today,
        "total_games": total_games,
        "success_rate": success_rate,
        "game_number": game_number,
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


@app.route("/api/migrate_stats", methods=["POST"])
def api_migrate_stats():
    try:
        data = request.get_json(force=True)

        # Cookie-only identity source
        player_uid = request.cookies.get("player_uid")
        if not player_uid:
            logger.warning("[API_MIGRATE] ❌ No player_uid cookie found")
            return jsonify(
                {"status": "error", "message": "player_uid cookie required"}
            ), 400

        stats = data.get("stats") or {}
        logger.info(f"[API_MIGRATE] Stats payload: {stats}")

        # Basic validation
        if not isinstance(stats, dict):
            logger.error(f"[API_MIGRATE] ❌ Invalid stats payload type: {type(stats)}")
            return jsonify({"status": "error", "message": "invalid stats payload"}), 400

        res = migrate_player_stats(player_uid, stats)

        return jsonify(res)
    except Exception as e:
        logger.error(f"[API_MIGRATE] ❌ Error migrating stats: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "internal error"}), 500


@app.route("/api/player_stats", methods=["GET"])
def api_player_stats():
    """Return the current player's stats from the database."""
    # Allow explicit player_uid via query param (helpful when cookie may not be present)
    player_uid = request.args.get("player_uid") or request.cookies.get("player_uid")
    if not player_uid:
        return jsonify({"status": "not_found"}), 404
    stats = get_player_stats(player_uid)
    if stats:
        success_rate = (
            round((stats["games_won"] / stats["games_played"]) * 100)
            if stats["games_played"] > 0
            else 0
        )
        return jsonify(
            {
                "status": "found",
                "games_played": stats["games_played"],
                "games_won": stats["games_won"],
                "current_streak": stats["current_streak"],
                "best_streak": stats["best_streak"],
                "success_rate": success_rate,
                "player_country": stats.get("player_country", "Unknown"),
                "player_city": stats.get("player_city", "Unknown"),
                "last_updated": stats.get("last_updated"),
            }
        )
    return jsonify({"status": "not_found"}), 404


@app.route("/api/player_stats_debug", methods=["GET"])
def debug_player_stats():
    """Debug endpoint to check current player stats and migration status."""
    player_uid = request.cookies.get("player_uid")

    if not player_uid:
        return jsonify(
            {"status": "error", "message": "no player_uid cookie found"}
        ), 400

    logger.info(f"[DEBUG_STATS] Checking stats for player {player_uid}")

    stats = get_player_stats(player_uid)

    if stats:
        logger.info(f"[DEBUG_STATS] ✅ Found stats: {stats}")
        return jsonify({"player_uid": player_uid, "stats": stats, "status": "found"})
    else:
        logger.info(f"[DEBUG_STATS] ⚠️ No stats found for {player_uid}")
        return jsonify({"player_uid": player_uid, "stats": None, "status": "not_found"})


# Added observability for WhatsApp share events
@app.route("/api/observability/share", methods=["POST"])
def log_share_event():
    data = request.get_json(force=True)
    player_country, player_region, player_city = _resolve_player_location_from_session()

    whatsapp_share_event = {
        "env": os.getenv("FLASK_ENV", "production"),
        "event": "WHATSAPP_SHARE_EVENT",
        "game_number": data.get("gameNumber"),
        "encoded_message": data.get("result"),
        "game_result": data.get("gameResult"),
        "country_name": session.get("country_name", "unknown"),
        "player_uid": request.cookies.get("player_uid"),
        "player_country": player_country,
        "player_region": player_region,
        "player_city": player_city,
        "hard_mode": session.get("hard_mode", False),
    }
    logger.info(json.dumps(whatsapp_share_event))

    return jsonify({"status": "ok"}), 200


@app.route("/api/observability/player_recovery", methods=["POST"])
def log_player_recovery():
    """Log when a player_uid is recovered from localStorage/IndexedDB instead of cookie."""
    try:
        data = request.get_json(force=True)

        recovery_event = {
            "event": "PLAYER_UID_RECOVERY",
            "player_uid": data.get("player_uid"),
            "source": data.get("source"),  # 'localStorage', 'indexeddb', 'generated'
            "timestamp": data.get("timestamp"),
            "ip_address": request.remote_addr,
        }
        logger.warning(f"[PLAYER_RECOVERY] {json.dumps(recovery_event)}")

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"[PLAYER_RECOVERY] Error logging recovery: {e}")
        return jsonify({"status": "ok"}), 200  # Always return 200 (non-critical)


# Warm the cache at startup so the first request doesn't pay the Postgres cost.
try:
    daily_game_cache.refresh()
    daily_game_cache.start_background_refresh()
except Exception as _cache_err:
    logger.warning(f"[DAILY_CACHE] Startup warm failed: {_cache_err}")


if __name__ == "__main__":
    flask_env = os.getenv("FLASK_ENV", "production").lower()
    debug_mode = flask_env in ["development", "local"]
    app.run(debug=debug_mode)
