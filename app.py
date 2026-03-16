# app.py
from datetime import date, timedelta
import os

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
from services.game_database_postgres import (
    ensure_schema,
    get_game_number,
    get_games_today,
    get_landing_stats,
    get_leaderboard_data,
    get_total_games,
    migrate_player_stats,
    get_player_stats,
    load_daily_game_state,
)
from services.game_database_postgres import warm_caches
from services.game_logic import (
    get_or_create_player_uid,
    initialize_game,
    get_game_state,
    process_guess,
    reset_game,
    send_contact_email,
)
import json
from dotenv import load_dotenv
from services.game_logger import setup_logger
import mimetypes
import threading
import time

import services.game_database_postgres as pgdb


# Setup logger
logger = setup_logger()


def _start_cache_warmer() -> None:
    """Spawn a daemon thread: warm caches at startup, then again each UK midnight."""
    import time
    import pytz
    from datetime import datetime, timedelta

    def _run():
        warm_caches()  # immediate warm-up on startup
        while True:
            uk = pytz.timezone("Europe/London")
            now_uk = datetime.now(uk)
            next_midnight = (now_uk + timedelta(days=1)).replace(
                hour=0, minute=0, second=10, microsecond=0
            )
            sleep_secs = max((next_midnight - now_uk).total_seconds(), 1)
            logger.info(f"[CACHE_WARMER] next refresh in {int(sleep_secs)}s")
            time.sleep(sleep_secs)
            warm_caches()

    # Only start the background cache warmer when explicitly enabled to
    # avoid multiple Gunicorn workers all hammering the DB at startup.
    # Set the environment variable `CACHE_WARMER=1` for a single instance.
    if os.getenv("CACHE_WARMER", "0") == "1":
        # Guard against Flask debug-mode double-reload spawning two threads
        if not any(t.name == "cache_warmer" for t in threading.enumerate()):
            t = threading.Thread(target=_run, name="cache_warmer", daemon=True)
            t.start()
            logger.info("[CACHE_WARMER] background thread started")
    else:
        logger.info("[CACHE_WARMER] disabled (set CACHE_WARMER=1 to enable)")


_start_cache_warmer()

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
    # Render landing immediately using in-process caches when available.
    # Avoid any blocking schema or cleanup work on the request path.
    if "country_name" not in session:
        reset_game(session)

    # Try to use cached landing stats (fast-path). If cache missing, show
    # minimal page and warm caches asynchronously.
    try:
        now = time.monotonic()
        with pgdb._LANDING_STATS_LOCK:
            cache = pgdb._LANDING_STATS_CACHE
            ts = pgdb._LANDING_STATS_CACHE_TS
            ttl = pgdb._LANDING_STATS_CACHE_TTL
            if cache is not None and (now - ts) < ttl:
                game_number, games_today, today_success_rate, total_games = cache
            else:
                # Fall back to daily-game cache if available (no DB round-trip)
                daily = pgdb._DAILY_GAME_CACHE
                if daily and daily.get("game_number") is not None:
                    game_number = int(daily["game_number"])
                else:
                    game_number = 0
                games_today = total_games = today_success_rate = 0

                # Warm caches in background so subsequent requests are fast
                if not any(t.name == "landing_cache_warmer" for t in threading.enumerate()):
                    t = threading.Thread(target=pgdb.warm_caches, name="landing_cache_warmer", daemon=True)
                    t.start()
    except Exception:
        game_number = 0
        games_today = total_games = today_success_rate = 0

    bordle_stats = {
        "games_today": games_today,
        "total_games": total_games,
        "success_rate": today_success_rate,
        "game_number": game_number,
    }

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
    # hard_mode checkbox is only present if checked
    session["hard_mode"] = bool(request.form.get("hard_mode"))
    
    # show borders option
    session["show_border_lines"] = bool(request.form.get("show_border_lines"))

    # show borders option
    session["border_hint_declined"] = False

    # Only initialize the game if it hasn't already started
    if "country_name" not in session:
        # Create transient player_state and initialize (will persist on first guess)
        player_state = {}
        initialize_game(player_state)

    return redirect(url_for("game"))


@app.route("/check_played", methods=["POST"])
def check_played():
    player_uid = request.cookies.get("player_uid")
    if not player_uid:
        return jsonify({"blockPlay": False})

    state = load_daily_game_state(player_uid)
    if state and (state.get("game_over") or state.get("game_result_recorded")):
        return jsonify({"blockPlay": True})

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

    # Load player_state from DB (stateless servers: player state is in Postgres)
    if player_uid:
        player_state = load_daily_game_state(player_uid) or {}
    else:
        player_state = {}

    # Carry UI preferences from session into player_state if present
    if session.get("hard_mode") is not None:
        player_state["hard_mode"] = session.get("hard_mode")
    if session.get("show_border_lines") is not None:
        player_state["show_border_lines"] = session.get("show_border_lines")

    # Ensure today's game values and derived fields are initialized
    initialize_game(player_state, player_uid)

    # If form posted a guess
    if request.method == "POST":
        guess = request.form.get("guess", "").strip()
        process_guess(guess, player_state)
        return redirect(url_for("game"))

    # Build game state
    game_state = get_game_state(player_state)
    try:
        game_number, games_today, today_success_rate, total_games = get_landing_stats()
    except Exception as e:
        logger.warning(f"[GAME] could not fetch landing stats: {e}")
        game_number, games_today, today_success_rate, total_games = (
            session.get("game_number", 0), 0, 0, 0
        )
    bordle_stats = {
        "games_today": games_today,
        "total_games": total_games,
        "success_rate": today_success_rate,
        "game_number": game_number,
    }

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
            borders_hint_declined=player_state.get("borders_hint_declined", False),
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
    # Fetch all landing/stats values in a single DB call (cached)
    try:
        game_number, games_today, today_success_rate, total_games = get_landing_stats()
    except Exception as e:
        logger.warning(f"[STATS] could not fetch landing stats: {e}")
        game_number, games_today, today_success_rate, total_games = 0, 0, 0, 0

    bordle_stats = {
        "games_today": games_today,
        "total_games": total_games,
        "success_rate": today_success_rate,
        "game_number": game_number,
    }

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
            return jsonify({"status": "error", "message": "All fields are required"}), 400

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

        return jsonify({"status": "success", "message": "Message received! Thank you for your feedback."}), 200

    except Exception as e:
        logger.error(f"Error processing contact form: {str(e)}")
        return jsonify({"status": "error", "message": "An error occurred. Please try again."}), 500


@app.route("/submit", methods=["POST"])
def submit():
    # Handle the guess
    guess = request.form.get("guess", "").strip()

    # handle empty submit
    if guess == "":
        return redirect(url_for("game"))

    # Load player_state for current user
    player_uid = request.cookies.get("player_uid")
    player_state = load_daily_game_state(player_uid) or {}

    if "available_options" not in player_state:
        return redirect(url_for("index.html"))

    # Use game logic to process the guess
    process_guess(guess, player_state)
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
    
    if os.getenv("DB_TYPE", "sqlite").lower() == "postgres":
        return jsonify({"error": "download_db is only available for sqlite deployments"}), 400

    return send_file("db/games.db", as_attachment=True)


@app.route("/download_csv")
def download_csv():
    return send_file("db/games.csv", as_attachment=True)


@app.route("/analytics")
def analytics():
    game_number, games_today, success_rate, total_games = get_landing_stats()
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


@app.route('/api/migrate_stats', methods=['POST'])
def api_migrate_stats():
    try:
        data = request.get_json(force=True)

        # Cookie-only identity source
        player_uid = request.cookies.get('player_uid')
        if not player_uid:
            logger.warning("[API_MIGRATE] ❌ No player_uid cookie found")
            return jsonify({"status": "error", "message": "player_uid cookie required"}), 400

        stats = data.get('stats') or {}
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


@app.route('/api/player_stats', methods=['GET'])
def api_player_stats():
    """Return the current player's stats from the database."""
    player_uid = request.cookies.get('player_uid')
    if not player_uid:
        return jsonify({"status": "not_found"}), 404
    stats = get_player_stats(player_uid)
    if stats:
        success_rate = round((stats["games_won"] / stats["games_played"]) * 100) if stats["games_played"] > 0 else 0
        return jsonify({
            "status": "found",
            "games_played": stats["games_played"],
            "games_won": stats["games_won"],
            "current_streak": stats["current_streak"],
            "best_streak": stats["best_streak"],
            "success_rate": success_rate,
            "player_country": stats.get("player_country", "Unknown"),
            "player_city": stats.get("player_city", "Unknown"),
            "last_updated": stats.get("last_updated"),
        })
    return jsonify({"status": "not_found"}), 404


@app.route('/api/player_stats_debug', methods=['GET'])
def debug_player_stats():
    """Debug endpoint to check current player stats and migration status."""
    player_uid = request.cookies.get('player_uid')
    
    if not player_uid:
        return jsonify({"status": "error", "message": "no player_uid cookie found"}), 400
    
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


if __name__ == "__main__":
    env = (os.getenv("FLASK_ENV") or "local").lower()
    if env in {"local", "development"}:
        app.run(debug=True)
