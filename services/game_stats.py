import json

# Load border map once
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)


def get_stats(session):
    games_played = session.get("games_played", 0)
    games_won = session.get("games_won", 0)
    win_percentage = round((games_won / games_played) * 100) if games_played > 0 else 0
    return {
        "games_played": games_played,
        "games_won": games_won,
        "win_percentage": win_percentage
    }


def get_game_state(session):
    border_names = border_map.get(session["country_name"], [])
    has_won = set(session["correct_guesses"]) == set(border_names)

    if session["remaining_guesses"] <= 0 or has_won:
        update_stats(session, has_won)

    return {
        "stats": {
            "games_played": session.get("games_played", 0),
            "games_won": session.get("games_won", 0),
            "success_rate": round(
                100 * session.get("games_won", 0) / max(1, session.get("games_played", 0)), 1
            ),
        },
    }


def update_stats(session, won):
    session["games_played"] = session.get("games_played", 0) + 1
    if won:
        session["games_won"] = session.get("games_won", 0) + 1
