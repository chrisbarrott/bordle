import json
import os

# Load GeoJSON shapes once
with open("static/map_data/country_drop_down.json", "r", encoding="utf-8") as f:
    all_countries = json.load(f)

# Load GeoJSON shapes once
with open("static/map_data/iso_country_codes.json", "r", encoding="utf-8") as f:
    borders_data = json.load(f)


def validate_borders():
    missing = []
    invalid = []
    summary = []

    for country in all_countries:
        borders = borders_data.get(country)
        if borders is None:
            missing.append(country)
            summary.append(f"{country}: ❌ MISSING")
        else:
            summary.append(f"{country}: ✅ {len(borders)} borders")

    print(f"\nTotal countries checked: {len(all_countries)}")
    print(f"✅ Valid: {len(all_countries) - len(missing) - len(invalid)}")
    print(f"❌ Missing: {len(missing)}")

    if missing:
        print("Missing countries:")
        for c in missing:
            print(f"  - {c}")

    if invalid:
        print("\nInvalid format countries:")
        for c in invalid:
            print(f"  - {c}")

    return summary

if __name__ == "__main__":
    validate_borders()
