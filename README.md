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

```bash
git clone https://github.com/chrisbarrott/bordle.git
cd bordle
Install dependencies

We recommend using a virtual environment:

bash
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
│   └── styles/
│       └── style.css           # Custom CSS (uses Tailwind base)
├── templates/
│   ├── index.html              # Main game UI
│   └── components/             # Reusable UI modals (win/fail/stats)
├── data/
│   └── countries_shapes.json   # GeoJSON country shapes
├── game_logic.py               # Core game state and processing
└── generate_border_map.py      # Script to generate `border_map.json`
🧠 How It Works
A country is randomly selected each day.

Players must guess bordering countries using a dropdown.

Each guess is checked against spatial border data.

Map updates show correct (green) and incorrect (red) guesses.

A Leaflet map is shown at game end with interactivity and labels.

💡 Customization
You can:

Add a database to track user stats.

Add continent-based filters.

Introduce sea/river border challenges (experimental).

Track streaks and leaderboards.

📝 License
MIT License

🙌 Acknowledgements
Natural Earth for world map data.

GeoPandas and Shapely for spatial analysis.

Leaflet.js for interactive mapping.

Inspired by Wordle.
