# 🌍 Bordle

**Bordle** is a geography-based daily guessing game where players are shown the outline of a mystery country and must guess its **bordering countries**. You have a limited number of attempts to guess them all — one game per day!

![Bordle Screenshot](static/images/bordle_logo.png)

---

## 🎮 Features

- Interactive daily geography challenge
- Random UN-recognized country each day (out of 195)
- Guess bordering countries with dropdown assistance
- Visual map feedback for correct and incorrect guesses
- Hard mode that hides the name of the main country
- End-of-game interactive map with zoom, pan, and color-coded feedback
- Stylish, responsive UI with Tailwind CSS
- State persistence via Flask sessions

---

## 🚀 Getting Started

### 🔧 Requirements

- Python 3.8+
- Flask
- GeoPandas
- Shapely
- Vega / Leaflet (via CDN for map rendering)
- Jinja2 (comes with Flask)

### 📦 Installation

1. **Clone the repository**

bash
git clone https://github.com/chrisbarrott/bordle.git
cd bordle
Install dependencies

We recommend using a virtual environment:

```bash
Copy
Edit
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
Run the game

bash
Copy
Edit
flask run
Then navigate to http://127.0.0.1:5000 in your browser.

🗺️ Data Sources
Country outlines are sourced from Natural Earth.

Border data is computed from spatial overlaps using GeoPandas.

Only UN-recognized countries are included (195 total).

---

📁 Project Structure
php
Copy
Edit
bordle/
├── app.py                      # Flask application
├── static/
│   ├── images/                 # Logo and static images
│   ├── map_data/
│   │   └── border_map.json     # Country border relationships
│   └── css/
│       └── styles.css           # Custom CSS (uses Tailwind base)
├── templates/
│   ├── index.html              # Main game UI
│   └── components/             # Reusable UI modals (win/fail/stats)
├── data/
│   └── countries_shapes.json   # GeoJSON country shapes
├── game_logic.py               # Core game state and processing
└── generate_border_map.py      # Script to generate `border_map.json`'

---
 How It Works
A country is randomly selected each day.

Players must guess bordering countries using a dropdown.

Each guess is checked against spatial border data.

Map updates show correct (green) and incorrect (red) guesses.

A Leaflet map is shown at game end with interactivity and labels.

---
💡 Customization
You can:

Add a database to track user stats.

Add continent-based filters.

Introduce sea/river border challenges (experimental).

Track streaks and leaderboards.

---
🙌 Acknowledgements
Natural Earth for world map data.

GeoPandas and Shapely for spatial analysis.

Leaflet.js for interactive mapping.

Inspired by Wordle.

---

## 🗃️ Postgres Migration & Utilities

The codebase now supports using PostgreSQL as an alternative to the embedded SQLite
file. You can keep **dev**, **uat** and **prod** data in the *same* database by
prefixing table names with the `FLASK_ENV` value (e.g. `uat_player_stats`).

**Configuration:**

- Set `DB_TYPE=postgres` and provide a connection string in `POSTGRES_DSN` or
  `DATABASE_URL`.
- Tables are created automatically with the appropriate prefix; existing
  SQLite-based functions will continue to work once the environment variables
  are set.

**Helper scripts (in `scripts/`):**

| Script                             | Purpose |
|------------------------------------|---------|
| `validate_postgres_connection.py`  | Simple check that the Postgres server is reachable, prints version, time,
|                                    | and any environment-specific `player_stats` row count. |
| `migrate_sqlite_to_postgres.py`    | Copy all tables and data from `db/games.db` into Postgres, adding the
|                                    | current environment prefix. Intended for one-off migrations. |

Usage example::

    DB_TYPE=postgres FLASK_ENV=uat POSTGRES_DSN="postgres://user:pass@host/db" python scripts/validate_postgres_connection.py
    DB_TYPE=postgres FLASK_ENV=uat POSTGRES_DSN="..." python scripts/migrate_sqlite_to_postgres.py

The `game_database_connections` module contains abstraction helpers (`run_query`,
`table_name`) so much of the application logic works identically against both
backends.


