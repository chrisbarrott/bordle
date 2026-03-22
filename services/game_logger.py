import logging
import logging_loki
import os
import json
import atexit
from queue import SimpleQueue
from logging.handlers import QueueHandler, QueueListener
from pythonjsonlogger import json as jsonlogger
from dotenv import load_dotenv

load_dotenv()

_listener = None


def setup_logger():
    global _listener

    ENV = os.getenv("FLASK_ENV")
    GRAFANA_USER = os.getenv("GRAFANA_USERNAME")
    GRAFANA_API_TOKEN = os.getenv("GRAFANA_API_TOKEN")
    GRAFANA_URL = os.getenv("GRAFANA_URL")

    logger = logging.getLogger("bordle")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        # Build sink handlers first.
        sink_handlers = []

        # ---------- 1. Console handler ----------
        console_handler = logging.StreamHandler()
        console_formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        sink_handlers.append(console_handler)

        # ---------- 2. Loki handler ----------
        if GRAFANA_URL and GRAFANA_USER and GRAFANA_API_TOKEN:
            loki_handler = logging_loki.LokiHandler(
                url=GRAFANA_URL,
                auth=(GRAFANA_USER, GRAFANA_API_TOKEN),
                tags={"app": "bordle", "env": ENV},
                version="1",
            )
            # Loki should receive raw JSON payload in message.
            loki_handler.setFormatter(logging.Formatter("%(message)s"))
            sink_handlers.append(loki_handler)

        # Route logs through a queue so network handlers never block request threads.
        log_queue = SimpleQueue()
        logger.addHandler(QueueHandler(log_queue))
        _listener = QueueListener(log_queue, *sink_handlers, respect_handler_level=True)
        _listener.start()

        def _stop_listener():
            if _listener is not None:
                _listener.stop()

        atexit.register(_stop_listener)

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
