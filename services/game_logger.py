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
_listener_pid = None


def _stop_listener():
    global _listener, _listener_pid

    if _listener is not None:
        try:
            _listener.stop()
        finally:
            _listener = None
            _listener_pid = None


def setup_logger():
    global _listener, _listener_pid

    ENV = os.getenv("FLASK_ENV")
    GRAFANA_USER = os.getenv("GRAFANA_USERNAME")
    GRAFANA_API_TOKEN = os.getenv("GRAFANA_API_TOKEN")
    GRAFANA_URL = os.getenv("GRAFANA_URL")
    current_pid = os.getpid()

    logger = logging.getLogger("bordle")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Rebuild handlers after a fork so worker processes do not inherit a dead QueueListener.
    if getattr(logger, "_bordle_logger_pid", None) != current_pid:
        _stop_listener()
        logger.handlers.clear()

        console_handler = logging.StreamHandler()
        console_formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # Keep Loki async, but do not put console logging behind the queue.
        if GRAFANA_URL and GRAFANA_USER and GRAFANA_API_TOKEN:
            loki_handler = logging_loki.LokiHandler(
                url=GRAFANA_URL,
                auth=(GRAFANA_USER, GRAFANA_API_TOKEN),
                tags={"app": "bordle", "env": ENV},
                version="1",
            )
            loki_handler.setFormatter(logging.Formatter("%(message)s"))

            log_queue = SimpleQueue()
            logger.addHandler(QueueHandler(log_queue))
            _listener = QueueListener(log_queue, loki_handler, respect_handler_level=True)
            _listener.start()
            _listener_pid = current_pid

        logger._bordle_logger_pid = current_pid

        loki_active = _listener is not None
        logger.info(json.dumps({
            "event": "logger_init",
            "pid": current_pid,
            "env": ENV,
            "loki_active": loki_active,
        }))

    return logger


logger = setup_logger()
atexit.register(_stop_listener)


# -------- Helper for structured logs --------
def log_event(event_type: str, **fields):
    """
    Sends structured JSON logs to Loki with extracted fields.
    """
    payload = {"event": event_type, **fields}

    # This is the *raw* JSON Loki will parse as fields
    logger.info(json.dumps(payload))
