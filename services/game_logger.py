import logging
import logging_loki
import os
import json
from pythonjsonlogger import jsonlogger
from dotenv import load_dotenv

load_dotenv()


def setup_logger():
    ENV = os.getenv("FLASK_ENV")
    GRAFANA_USER = os.getenv("GRAFANA_USERNAME")
    GRAFANA_API_TOKEN = os.getenv("GRAFANA_API_TOKEN")
    GRAFANA_URL = os.getenv("GRAFANA_URL")

    logger = logging.getLogger("bordle")
    logger.setLevel(logging.INFO)

    if not logger.handlers:

        # ---------- 1. Console handler (nice readable logs) ----------
        console_handler = logging.StreamHandler()
        console_formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # ---------- 2. Loki handler (must be RAW json) ----------
        loki_handler = logging_loki.LokiHandler(
            url=GRAFANA_URL,
            auth=(GRAFANA_USER, GRAFANA_API_TOKEN),
            tags={"app": "bordle", "env": ENV},
            version="1",
        )

        # IMPORTANT:
        # Loki must get ONLY the JSON without timestamp, level, name, etc
        loki_handler.setFormatter(logging.Formatter("%(message)s"))

        logger.addHandler(loki_handler)

    return logger


logger = setup_logger()


# -------- Helper for structured logs --------
def log_event(event_type: str, **fields):
    """
    Sends structured JSON logs to Loki with extracted fields.
    """
    payload = {"event": event_type, **fields}

    # This is the *raw* JSON Loki will parse as fields
    logger.info(json.dumps(payload))
