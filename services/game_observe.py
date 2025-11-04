import requests
import os

OBSERVE_API_URL = "https://118473891588.collect.observeinc.com/v1/http"
OBSERVE_API_TOKEN = os.getenv("OBSERVE_API_TOKEN", "")


def send_to_observe(payload: dict):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OBSERVE_API_TOKEN}"
    }
    try:
        # resp = requests.post(OBSERVE_API_URL, headers=headers, json=payload, timeout=5)
        # resp.raise_for_status()
        print("Not sending to Observe anymore, POC completed")
    except requests.exceptions.RequestException as e:
        print("❌ Failed to send to Observe:", e)
