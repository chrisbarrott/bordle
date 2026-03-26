from unittest.mock import patch

from services.game_cache import DailyGameCache


def test_refresh_gets_country_before_counting_game_number():
    cache = DailyGameCache()
    call_order = []

    def _country_stub(target_date):
        call_order.append(("country", target_date))
        return {"country_code": None, "country_name": "Togo"}

    def _game_number_stub():
        call_order.append(("game_number", None))
        return 294

    with (
        patch.object(cache, "_today_uk_date", return_value="2026-03-26"),
        patch("services.game_cache.get_country_of_the_day", side_effect=_country_stub),
        patch("services.game_cache.get_current_game_number", side_effect=_game_number_stub),
    ):
        cache.refresh()

    assert call_order == [
        ("country", "2026-03-26"),
        ("game_number", None),
    ]
    assert cache._game_number == 294
    assert cache._country_info == {"country_code": None, "country_name": "Togo"}