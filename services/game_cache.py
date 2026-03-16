"""Daily game cache.

Fetches game_number and country_of_the_day once at startup and refreshes
automatically when the date rolls over, so individual requests never pay
the Postgres round-trip cost for these two values.
"""
import threading
import time
from datetime import date
from typing import Optional, Dict

from .game_db_logic import get_current_game_number, get_country_of_the_day
from .game_logger import setup_logger

logger = setup_logger()


class DailyGameCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._date: Optional[date] = None
        self._game_number: int = 0
        self._country_info: Optional[Dict[str, str]] = None

    @property
    def game_number(self) -> int:
        self._refresh_if_stale()
        return self._game_number

    @property
    def country_info(self) -> Optional[Dict[str, str]]:
        self._refresh_if_stale()
        return self._country_info

    def refresh(self) -> None:
        """Fetch both values from Postgres and store them."""
        today = date.today()
        try:
            game_number = get_current_game_number()
            country_info = get_country_of_the_day(today)
            with self._lock:
                self._date = today
                self._game_number = game_number if game_number is not None else 0
                self._country_info = country_info
            logger.info(
                f"[DAILY_CACHE] Refreshed: date={today}, "
                f"game_number={self._game_number}, country={self._country_info}"
            )
        except Exception as e:
            logger.error(f"[DAILY_CACHE] Refresh failed: {e}")

    def _refresh_if_stale(self) -> None:
        if self._date != date.today():
            self.refresh()

    def start_background_refresh(self) -> None:
        """Start a daemon thread that wakes at midnight to refresh the cache."""
        thread = threading.Thread(target=self._midnight_loop, daemon=True, name="daily-cache-refresh")
        thread.start()
        logger.info("[DAILY_CACHE] Background refresh thread started")

    def _midnight_loop(self) -> None:
        while True:
            now = time.localtime()
            seconds_until_midnight = (
                (23 - now.tm_hour) * 3600
                + (59 - now.tm_min) * 60
                + (60 - now.tm_sec)
                + 5  # small buffer past midnight
            )
            time.sleep(seconds_until_midnight)
            self.refresh()


# Module-level singleton used throughout the app.
daily_game_cache = DailyGameCache()
