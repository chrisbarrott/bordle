import json
import os

from flask import request
import requests
from shapely.geometry import shape

# Load border map once
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    border_map = json.load(f)

# Load border map once
with open("static/map_data/country_drop_down.json", "r", encoding="utf-8") as f:
    country_drop_down = json.load(f)

# Load GeoJSON shapes once
with open("data/countries_shapes.json", "r", encoding="utf-8") as f:
    geojson_data = json.load(f)


def load_geojson():
    return geojson_data


def add_centroids(geojson_features):
    for feature in geojson_features:
        geom = shape(feature["geometry"])
        centroid = geom.centroid
        feature["properties"]["centroid_lon"] = centroid.x
        feature["properties"]["centroid_lat"] = centroid.y
    return geojson_features


def get_country_shape(name):
    features = [f for f in geojson_data["features"] if f["properties"].get("name") == name]
    return add_centroids(features)[0] if features else None


def get_shapes(names):
    features = [f for f in geojson_data["features"] if f["properties"].get("name") in names]
    return add_centroids(features)


def get_border_options(session):
    guessed = set(session.get("correct_guesses", []) + session.get("wrong_guesses", []))
    return [opt for opt in session.get("available_options", []) if opt not in guessed]


def get_correct_answers(session):
    return border_map.get(session.get("country_name"), [])


def get_all_countries(border_map):
    all_countries = set(border_map.keys())
    return all_countries


def get_all_drop_down_options():
    with open("static/map_data/country_drop_down.json", 'r', encoding='utf-8') as f:
        return json.load(f)


def get_user_location(ip: str):
    """Lookup approximate location from an IP address."""
    if ip in ("127.0.0.1", "::1"):
        # Localhost or internal test
        return {"country": "Localhost", "region": "Local", "city": "Localhost"}

    # Example free API (ipinfo.io, ipapi.co, or ipwho.is)
    url = f"https://ipapi.co/{ip}/json/"
    response = requests.get(url, timeout=5)

    if response.status_code != 200:
        print(f"⚠️ Geo lookup failed: HTTP {response.status_code}")
        return {}

    try:
        data = response.json()
    except json.JSONDecodeError:
        print(f"⚠️ Geo lookup failed: invalid JSON from {url}")
        return {}

    return {
        "country": data.get("country_name", "Unknown"),
        "region": data.get("region", "Unknown"),
        "city": data.get("city", "Unknown")
    }


def get_user_ip():
    """
    Extract the user's real IP address.
    Works even if the app is behind a proxy (e.g., Render, Cloudflare).
    """
    # X-Forwarded-For may contain multiple IPs – client first, proxy last
    forwarded_for = request.headers.get('X-Forwarded-For', None)
    if forwarded_for:
        ip = forwarded_for.split(',')[0].strip()
    else:
        ip = request.remote_addr
    return ip
