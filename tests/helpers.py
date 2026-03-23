"""Shared test constants and state-builder helpers.

Kept separate from conftest.py so they can be imported normally
without going through pytest's fixture machinery.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

TEST_PLAYER_UID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TEST_COUNTRY = "France"
# France's real neighbours – all present in the production country_drop_down.json
TEST_BORDERS = ["Germany", "Spain", "Italy"]
TEST_GAME_NUMBER = 42
TEST_DATE = datetime.now(UK_TZ).date()  # real date object → prevents cache stale-refresh


def make_state(**overrides) -> dict:
    """Return a normalised player_game_state dict (mirrors _normalize_player_state)."""
    base = {
        "game_number": TEST_GAME_NUMBER,
        "guess_history": [],
        "wrong_guesses": [],
        "hard_mode": False,
        "guessed_main_country": False,
        "game_over": False,
        "game_result": "In progress",
        "game_result_recorded": False,
        "player_stats_recorded": False,
        "leaderboard_recorded": False,
    }
    base.update(overrides)
    return base


def make_response_state(**overrides) -> dict:
    """Return a full response_state dict that satisfies index.html template rendering."""
    base = {
        **make_state(),
        # game_logic.get_game_state() additions
        "all_correct": list(TEST_BORDERS),
        "attempts_left": 5,
        "border_count": len(TEST_BORDERS),
        "borders_remaining": len(TEST_BORDERS),
        "border_hint_declined": False,
        "correct_count": 0,
        "correct_guesses": [],
        "country_name": TEST_COUNTRY,
        "guess_country": "",
        "player_country": "UK",
        "player_region": "England",
        "player_city": "London",
        "show_border_lines": False,
        "player_uid": TEST_PLAYER_UID,
        # _build_game_response additions
        "all_countries": [TEST_COUNTRY] + list(TEST_BORDERS),
        "border_options": list(TEST_BORDERS),
        "correct_shapes": [],
        "country_geojson": {},
        "final_shapes": [],
        "wrong_shapes": [],
    }
    base.update(overrides)
    return base
