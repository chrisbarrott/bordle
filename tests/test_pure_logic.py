"""Tests for pure helper functions — no DB, no HTTP, no fixtures needed."""

from services.game_logic import _is_game_won, _derive_game_result


class TestIsGameWon:
    def test_exact_match(self):
        assert _is_game_won(["Germany", "Spain", "Italy"], ["Germany", "Spain", "Italy"])

    def test_order_does_not_matter(self):
        assert _is_game_won(["Spain", "Italy", "Germany"], ["Germany", "Spain", "Italy"])

    def test_partial_guesses_not_won(self):
        assert not _is_game_won(["Germany"], ["Germany", "Spain", "Italy"])

    def test_no_guesses_not_won(self):
        assert not _is_game_won([], ["Germany", "Spain", "Italy"])

    def test_borderless_country_wins_immediately(self):
        """A country with no borders is won as soon as the game starts (empty == empty)."""
        assert _is_game_won([], [])

    def test_superset_of_borders_is_not_a_win(self):
        """Guessing extra countries beyond the border list should not count as a win."""
        assert not _is_game_won(
            ["Germany", "Spain", "Italy", "Austria"],
            ["Germany", "Spain", "Italy"],
        )


class TestDeriveGameResult:
    def test_win(self):
        assert _derive_game_result(game_over=True, is_win=True) == "Win"

    def test_loss(self):
        assert _derive_game_result(game_over=True, is_win=False) == "Loss"

    def test_in_progress(self):
        assert _derive_game_result(game_over=False, is_win=False) == "In progress"
