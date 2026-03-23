"""Tests for stats recording inside get_game_state().

Focus areas:
- Win / Loss both trigger all three record_postgres_* calls
- Idempotency: flags already set → stat recorders NOT called again
- Partial recording: only the missing flag's recorder is called
- upsert_game_state is called (to lock flags) after first recording
- In-progress game never triggers recording
"""

from unittest.mock import patch, MagicMock

import pytest

from services.game_logic import get_game_state
from tests.helpers import (
    TEST_PLAYER_UID,
    TEST_COUNTRY,
    TEST_BORDERS,
    TEST_GAME_NUMBER,
    make_state,
)

# ── helper ─────────────────────────────────────────────────────────────────────

_PLAYER_STATS_RETURN = {
    "games_played": 1,
    "games_won": 1,
    "current_streak": 1,
    "best_streak": 1,
    "player_country": "UK",
    "player_city": "London",
    "migrated": False,
    "last_updated": "2026-03-22",
}


def _call_get_game_state(app, persisted_state):
    """
    Run get_game_state() inside a Flask request context with all DB calls
    mocked out.  Returns (result_dict, mock_upsert, mock_game, mock_player, mock_country).
    """
    with (
        patch("services.game_logic.load_game_state", return_value=persisted_state),
        patch("services.game_logic.create_game_state_row", return_value=persisted_state),
        patch("services.game_logic.upsert_game_state") as mock_upsert,
        patch("services.game_logic.record_postgres_game_stats", return_value=True) as mock_game,
        patch(
            "services.game_logic.record_postgres_player_stats",
            return_value=_PLAYER_STATS_RETURN,
        ) as mock_player,
        patch("services.game_logic.record_postgres_country_stats", return_value=True) as mock_country,
    ):
        with app.test_request_context(
            "/game",
            headers={"Cookie": f"player_uid={TEST_PLAYER_UID}"},
        ):
            session = {
                "player_uid": TEST_PLAYER_UID,
                "country_name": TEST_COUNTRY,
                "game_number": TEST_GAME_NUMBER,
                "hard_mode": False,
                # Pre-fill location so _get_player_location() skips the HTTP call
                "player_data": ("UK", "England", "London"),
            }
            result = get_game_state(session)

    return result, mock_upsert, mock_game, mock_player, mock_country


# ── win recording ──────────────────────────────────────────────────────────────

class TestWinRecording:
    def test_all_three_recorders_called_on_win(self, app):
        won = make_state(
            guess_history=list(TEST_BORDERS),
            game_over=True,
            game_result="Win",
            game_result_recorded=False,
            player_stats_recorded=False,
            leaderboard_recorded=False,
        )
        _, _, mock_game, mock_player, mock_country = _call_get_game_state(app, won)

        mock_game.assert_called_once_with(True)
        mock_player.assert_called_once()
        assert mock_player.call_args.args[0] is True   # success=True
        mock_country.assert_called_once()

    def test_upsert_called_with_all_flags_true_after_win(self, app):
        """After recording, upsert_game_state must persist all three flags=True."""
        won = make_state(
            guess_history=list(TEST_BORDERS),
            game_over=True,
            game_result="Win",
            game_result_recorded=False,
            player_stats_recorded=False,
            leaderboard_recorded=False,
        )
        _, mock_upsert, _, _, _ = _call_get_game_state(app, won)

        mock_upsert.assert_called_once()
        kwargs = mock_upsert.call_args.kwargs
        assert kwargs["game_result_recorded"] is True
        assert kwargs["player_stats_recorded"] is True
        assert kwargs["leaderboard_recorded"] is True

    def test_game_result_is_win_in_returned_state(self, app):
        won = make_state(
            guess_history=list(TEST_BORDERS),
            game_over=True,
            game_result="Win",
        )
        result, *_ = _call_get_game_state(app, won)
        assert result["game_result"] == "Win"
        assert result["game_over"] is True


# ── loss recording ─────────────────────────────────────────────────────────────

class TestLossRecording:
    def test_all_three_recorders_called_on_loss(self, app):
        lost = make_state(
            guess_history=["Canada", "Mexico", "Brazil", "Argentina", "Chile"],
            wrong_guesses=["Canada", "Mexico", "Brazil", "Argentina", "Chile"],
            game_over=True,
            game_result="Loss",
            game_result_recorded=False,
            player_stats_recorded=False,
            leaderboard_recorded=False,
        )
        _, _, mock_game, mock_player, mock_country = _call_get_game_state(app, lost)

        mock_game.assert_called_once_with(False)
        mock_player.assert_called_once()
        assert mock_player.call_args.args[0] is False   # success=False
        mock_country.assert_called_once()

    def test_game_result_is_loss_in_returned_state(self, app):
        lost = make_state(
            guess_history=["Canada", "Mexico", "Brazil", "Argentina", "Chile"],
            game_over=True,
            game_result="Loss",
        )
        result, *_ = _call_get_game_state(app, lost)
        assert result["game_result"] == "Loss"


# ── idempotency ────────────────────────────────────────────────────────────────

class TestIdempotency:
    def test_no_recorders_called_when_all_flags_already_set(self, app):
        """Page refresh after a completed game must not double-count stats."""
        already_recorded = make_state(
            guess_history=list(TEST_BORDERS),
            game_over=True,
            game_result="Win",
            game_result_recorded=True,
            player_stats_recorded=True,
            leaderboard_recorded=True,
        )
        _, _, mock_game, mock_player, mock_country = _call_get_game_state(app, already_recorded)

        mock_game.assert_not_called()
        mock_player.assert_not_called()
        mock_country.assert_not_called()

    def test_only_missing_recorders_run_on_partial_flags(self, app):
        """
        If game_result was already recorded but player/leaderboard weren't,
        only those two should be called.
        """
        partial = make_state(
            guess_history=list(TEST_BORDERS),
            game_over=True,
            game_result="Win",
            game_result_recorded=True,   # already done
            player_stats_recorded=False,
            leaderboard_recorded=False,
        )
        _, _, mock_game, mock_player, mock_country = _call_get_game_state(app, partial)

        mock_game.assert_not_called()      # already recorded
        mock_player.assert_called_once()   # still pending
        mock_country.assert_called_once()  # still pending

    def test_in_progress_game_never_records_stats(self, app):
        """No stat recorder should be called while the game is still in progress."""
        in_progress = make_state(
            guess_history=[TEST_BORDERS[0]],
            game_over=False,
        )
        _, _, mock_game, mock_player, mock_country = _call_get_game_state(app, in_progress)

        mock_game.assert_not_called()
        mock_player.assert_not_called()
        mock_country.assert_not_called()

    def test_upsert_not_called_for_in_progress_game(self, app):
        in_progress = make_state(
            guess_history=[TEST_BORDERS[0]],
            game_over=False,
        )
        _, mock_upsert, _, _, _ = _call_get_game_state(app, in_progress)
        mock_upsert.assert_not_called()


# ── streak logic (via SQL upsert query, verified through mock call args) ───────

class TestStreakSql:
    """
    The actual streak arithmetic lives in the SQL upsert query, not in Python.
    These tests verify that record_postgres_player_stats() is called with the
    correct success flag so the SQL CASE expression fires correctly.
    """

    def test_win_passes_success_true_to_player_stats(self, app):
        won = make_state(
            guess_history=list(TEST_BORDERS),
            game_over=True,
            game_result="Win",
        )
        _, _, _, mock_player, _ = _call_get_game_state(app, won)
        assert mock_player.call_args.args[0] is True

    def test_loss_passes_success_false_to_player_stats(self, app):
        lost = make_state(
            guess_history=["Canada", "Mexico", "Brazil", "Argentina", "Chile"],
            wrong_guesses=["Canada", "Mexico", "Brazil", "Argentina", "Chile"],
            game_over=True,
            game_result="Loss",
        )
        _, _, _, mock_player, _ = _call_get_game_state(app, lost)
        assert mock_player.call_args.args[0] is False
