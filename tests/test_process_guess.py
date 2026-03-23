"""Tests for process_guess() — easy mode, hard mode, game-over guard.

Each test calls process_guess() directly inside a Flask request context
(so request.cookies is available) with all Postgres calls mocked.
"""

from unittest.mock import patch, call

import pytest

from services.game_logic import process_guess
from tests.helpers import (
    TEST_PLAYER_UID,
    TEST_COUNTRY,
    TEST_BORDERS,
    TEST_GAME_NUMBER,
    make_state,
)


# ── helper ─────────────────────────────────────────────────────────────────────

def _run_guess(app, guess, persisted_state, *, session_hard_mode=False):
    """
    Call process_guess() inside a real Flask request context.

    Returns the MagicMock for upsert_game_state so callers can inspect
    what was written back to the database.
    """
    with (
        patch("services.game_logic.load_game_state", return_value=persisted_state),
        patch("services.game_logic.create_game_state_row", return_value=persisted_state),
        patch("services.game_logic.upsert_game_state") as mock_upsert,
    ):
        with app.test_request_context(
            "/submit",
            method="POST",
            headers={"Cookie": f"player_uid={TEST_PLAYER_UID}"},
        ):
            session = {
                "player_uid": TEST_PLAYER_UID,
                "country_name": TEST_COUNTRY,
                "game_number": TEST_GAME_NUMBER,
                "hard_mode": session_hard_mode,
            }
            process_guess(guess, session)

    return mock_upsert


# ── easy mode ──────────────────────────────────────────────────────────────────

class TestEasyMode:
    def test_correct_border_added_to_history(self, app):
        mock_upsert = _run_guess(app, TEST_BORDERS[0], make_state())
        mock_upsert.assert_called_once()
        assert TEST_BORDERS[0] in mock_upsert.call_args.kwargs["guess_history"]

    def test_correct_border_not_in_wrong_guesses(self, app):
        mock_upsert = _run_guess(app, TEST_BORDERS[0], make_state())
        assert TEST_BORDERS[0] not in mock_upsert.call_args.kwargs["wrong_guesses"]

    def test_wrong_guess_added_to_wrong_guesses(self, app):
        mock_upsert = _run_guess(app, "Canada", make_state())
        assert "Canada" in mock_upsert.call_args.kwargs["wrong_guesses"]

    def test_wrong_guess_also_in_guess_history(self, app):
        mock_upsert = _run_guess(app, "Canada", make_state())
        assert "Canada" in mock_upsert.call_args.kwargs["guess_history"]

    def test_win_when_all_borders_guessed(self, app):
        """Guessing the final missing border should set game_over=True, game_result='Win'."""
        initial = make_state(guess_history=list(TEST_BORDERS[:-1]))
        mock_upsert = _run_guess(app, TEST_BORDERS[-1], initial)
        kwargs = mock_upsert.call_args.kwargs
        assert kwargs["game_over"] is True
        assert kwargs["game_result"] == "Win"

    def test_loss_after_five_wrong_guesses(self, app):
        """Exhausting all 5 attempts without guessing all borders → Loss."""
        wrong_history = ["Canada", "Mexico", "Brazil", "Argentina"]
        initial = make_state(guess_history=wrong_history, wrong_guesses=wrong_history)
        mock_upsert = _run_guess(app, "Chile", initial)   # 5th guess, still wrong
        kwargs = mock_upsert.call_args.kwargs
        assert kwargs["game_over"] is True
        assert kwargs["game_result"] == "Loss"

    def test_completed_game_ignores_further_guesses(self, app):
        """Once game_over=True, any subsequent guess must be silently ignored."""
        completed = make_state(game_over=True)
        mock_upsert = _run_guess(app, TEST_BORDERS[0], completed)
        mock_upsert.assert_not_called()

    def test_duplicate_guess_not_counted_twice(self, app):
        """Submitting the same guess twice should only appear once in guess_history."""
        initial = make_state(guess_history=[TEST_BORDERS[0]])
        mock_upsert = _run_guess(app, TEST_BORDERS[0], initial)
        kwargs = mock_upsert.call_args.kwargs
        assert kwargs["guess_history"].count(TEST_BORDERS[0]) == 1

    def test_game_not_over_with_guesses_remaining(self, app):
        """Guessing one border (of three) should NOT trigger game_over."""
        mock_upsert = _run_guess(app, TEST_BORDERS[0], make_state())
        assert mock_upsert.call_args.kwargs["game_over"] is False


# ── hard mode ──────────────────────────────────────────────────────────────────

class TestHardMode:
    def test_country_guess_sets_guessed_main_country(self, app):
        """In hard mode, guessing the exact country name sets guessed_main_country=True."""
        initial = make_state(hard_mode=True)
        mock_upsert = _run_guess(app, TEST_COUNTRY, initial, session_hard_mode=True)
        mock_upsert.assert_called_once()
        assert mock_upsert.call_args.kwargs["guessed_main_country"] is True

    def test_country_guess_not_added_to_guess_history(self, app):
        """In hard mode the country name itself must NOT appear in guess_history."""
        initial = make_state(hard_mode=True)
        mock_upsert = _run_guess(app, TEST_COUNTRY, initial, session_hard_mode=True)
        assert TEST_COUNTRY not in mock_upsert.call_args.kwargs["guess_history"]

    def test_country_guess_does_not_end_game(self, app):
        """Guessing the country in hard mode keeps game_over=False (borders still needed)."""
        initial = make_state(hard_mode=True)
        mock_upsert = _run_guess(app, TEST_COUNTRY, initial, session_hard_mode=True)
        assert mock_upsert.call_args.kwargs["game_over"] is False

    def test_hard_mode_win_after_country_then_all_borders(self, app):
        """Win only triggers once the country AND all borders have been guessed."""
        initial = make_state(
            hard_mode=True,
            guessed_main_country=True,
            guess_history=list(TEST_BORDERS[:-1]),
        )
        mock_upsert = _run_guess(app, TEST_BORDERS[-1], initial, session_hard_mode=True)
        kwargs = mock_upsert.call_args.kwargs
        assert kwargs["game_over"] is True
        assert kwargs["game_result"] == "Win"

    def test_hard_mode_flag_read_from_db_state_not_session(self, app):
        """hard_mode comes from the persisted DB state, overriding the session value."""
        # DB says hard_mode=True; session says False
        initial = make_state(hard_mode=True)
        mock_upsert = _run_guess(app, TEST_BORDERS[0], initial, session_hard_mode=False)
        assert mock_upsert.call_args.kwargs["hard_mode"] is True

    def test_easy_mode_flag_read_from_db_state(self, app):
        """easy mode (hard_mode=False) is equally sourced from DB state."""
        # DB says hard_mode=False; session says True
        initial = make_state(hard_mode=False)
        mock_upsert = _run_guess(app, TEST_BORDERS[0], initial, session_hard_mode=True)
        assert mock_upsert.call_args.kwargs["hard_mode"] is False
