"""Pytest fixtures shared across the whole test suite.

Strategy
--------
* The Postgres connector is never called during tests — we patch
  ``services.game_logic.*`` and ``services.game_db_logic.*`` at their
  point-of-use so real network I/O never happens.
* ``daily_game_cache`` is seeded directly with deterministic values so
  ``_refresh_if_stale()`` never triggers a real Postgres call.
* ``border_map`` in ``game_logic`` is replaced with a minimal dict
  centred on France so every test uses predictable geography.
* External HTTP calls (ip-api.com, GeoJSON look-ups) are stubbed out.
"""

import logging
import os
from unittest.mock import patch

# Daemon threads (e.g. the midnight cache-refresh thread) may try to log after
# pytest tears down its stream handlers.  Suppress the resulting "Logging error"
# noise — the records are simply dropped, which is the correct behaviour.
logging.raiseExceptions = False

import pytest

# ── env vars must be set before any app/service modules are imported ───────────
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key-bordle")
os.environ.setdefault("FLASK_ENV", "uat")
os.environ.setdefault("DB_TYPE", "postgres")

# ── deferred imports (after env vars are configured) ──────────────────────────
from app import app as flask_app          # noqa: E402
from services import game_cache           # noqa: E402
from services import game_logic           # noqa: E402
from tests.helpers import TEST_COUNTRY, TEST_BORDERS, TEST_GAME_NUMBER, TEST_DATE  # noqa: E402


# ── app / client fixtures ──────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key-bordle"
    flask_app.config["WTF_CSRF_ENABLED"] = False
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


# ── autouse fixtures — applied to every test automatically ────────────────────

@pytest.fixture(autouse=True)
def _seed_cache():
    """Populate the in-memory cache so it never tries to hit Postgres."""
    cache = game_cache.daily_game_cache
    cache._game_number = TEST_GAME_NUMBER
    cache._country_info = {"country_code": "FR", "country_name": TEST_COUNTRY}
    cache._date = TEST_DATE   # real date object — suppresses _refresh_if_stale()
    yield


@pytest.fixture(autouse=True)
def _patch_border_map():
    """Replace the module-level border_map with a minimal test fixture."""
    with patch.dict(game_logic.border_map, {TEST_COUNTRY: list(TEST_BORDERS)}, clear=True):
        yield


@pytest.fixture(autouse=True)
def _patch_geo():
    """Stub out all external HTTP / GeoJSON calls."""
    with (
        patch("services.game_logic.get_user_ip", return_value="1.2.3.4"),
        patch("services.game_logic.get_user_location", return_value=("UK", "England", "London")),
        patch("services.game_logic.get_country_shape", return_value={}),
        patch("services.game_logic.get_shapes", return_value=[]),
    ):
        yield
