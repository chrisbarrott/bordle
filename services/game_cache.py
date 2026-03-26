"""Daily game cache.

Fetches game_number and country_of_the_day once at startup and refreshes
automatically when the date rolls over, so individual requests never pay
the Postgres round-trip cost for these two values.
"""
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict

from .game_db_logic import get_current_game_number, get_country_of_the_day
from .game_logger import setup_logger

logger = setup_logger()

UK_TZ = ZoneInfo("Europe/London")


class DailyGameCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._date: Optional[date] = None
        self._game_number: int = 0
        self._country_info: Optional[Dict[str, str]] = None
        self._refresh_thread_started = False

    @staticmethod
    def _today_uk_date() -> date:
        return datetime.now(UK_TZ).date()

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
        today = self._today_uk_date()
        try:
            country_info = get_country_of_the_day(today)
            game_number = get_current_game_number()
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
        if self._date != self._today_uk_date():
            self.refresh()

    def start_background_refresh(self) -> None:
        """Start a daemon thread that wakes at midnight to refresh the cache."""
        if self._refresh_thread_started:
            return

        thread = threading.Thread(target=self._midnight_loop, daemon=True, name="daily-cache-refresh")
        thread.start()
        self._refresh_thread_started = True
        logger.info("[DAILY_CACHE] Background refresh thread started")

    def _midnight_loop(self) -> None:
        while True:
            now_uk = datetime.now(UK_TZ)
            next_midnight_uk = datetime.combine(now_uk.date() + timedelta(days=1), datetime.min.time(), tzinfo=UK_TZ)
            seconds_until_midnight = max(1, int((next_midnight_uk - now_uk).total_seconds()) + 5)
            time.sleep(seconds_until_midnight)
            self.refresh()


# Module-level singleton used throughout the app.
daily_game_cache = DailyGameCache()
