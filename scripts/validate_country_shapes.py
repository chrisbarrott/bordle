import json


# Load GeoJSON shapes once
with open("static/map_data/country_drop_down.json", "r", encoding="utf-8") as f:
    all_countries = json.load(f)

# Load GeoJSON shapes once
with open("data/countries_shapes.json", "r", encoding="utf-8") as f:
    geojson = json.load(f)


# Extract country names from GeoJSON features
geojson_countries = set(
    feature['properties'].get("name") for feature in geojson['features']
)
print(f"{len(geojson_countries)}")

# Find countries missing from the GeoJSON
missing = sorted(set(all_countries) - geojson_countries)

if missing:
    print("⚠️ Missing countries (no GeoJSON match):")
    for country in missing:
        print(f" - {country}")
else:
    print("✅ All countries are present in the GeoJSON!")
