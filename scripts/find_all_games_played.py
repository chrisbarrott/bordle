import os
import json
import sqlite3

# --- Existing config ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')
os.makedirs(DB_FOLDER, exist_ok=True)
DB_PATH = os.path.join(DB_FOLDER, 'games.db')

# Load dropdown options (list of all possible countries)
with open("static/map_data/country_drop_down.json", "r", encoding="utf-8") as f:
    dropdown_options = set(json.load(f))


# --- New logic ---
def list_countries_played():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all played countries from the database
    cursor.execute("SELECT country FROM daily_game")
    played_countries = {row[0] for row in cursor.fetchall()}
    conn.close()

    # Compare against dropdown list
    results = []
    for country in sorted(dropdown_options):
        status = "✅" if country in played_countries else "❌"
        results.append((country, status))

    # Print results neatly
    print(f"{'Country':<40}Status")
    print("-" * 50)
    for country, status in results:
        print(f"{country:<40}{status}")

    # Optional: return the list if you want to use it elsewhere
    return results


if __name__ == "__main__":
    list_countries_played()
