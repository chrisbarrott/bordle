import logging
import logging_loki
import os


# Setup Loki logger
def setup_logger():
    # Read env vars
    ENV = os.getenv('FLASK_SECRET_ENV')  # Set securely in production
    GRAFANA_USER = os.getenv('GRAFANA_USERNAME')
    GRAFANA_API_TOKEN = os.getenv('GRAFANA_API_TOKEN')
    GRAFANA_URL = os.getenv('GRAFANA_URL')

    if not all([ENV, GRAFANA_USER, GRAFANA_API_TOKEN, GRAFANA_URL]):
        raise RuntimeError("Loki environment variables are not all set!")

    # Create logger
    logger = logging.getLogger("bordle")
    logger.setLevel(logging.INFO)

    # Loki handler
    handler = logging_loki.LokiHandler(
        url=GRAFANA_URL,
        auth=(GRAFANA_USER, GRAFANA_API_TOKEN),
        tags={"app": "bordle", "env": ENV},
        version="1",
    )

    # Only add one handler (avoid duplicates when reloading)
    if not logger.handlers:
        logger.addHandler(handler)

    return logger
