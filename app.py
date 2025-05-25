import json, random

from flask import Flask, render_template, request, jsonify, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "supersecret"  # Set securely in production

with open("static/map_data/border_map.json") as f:
    border_map = json.load(f)

all_guessable_options = sorted(
    {name for borders in border_map.values() for name in borders}
)


@app.route("/")
def index():
    # Load border map and country shapes
    with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
        border_map = json.load(f)

    with open("data/countries_shapes.json", "r", encoding="utf-8") as f:
        geojson_data = json.load(f)

    # Initialise session state if not set
    if "country_name" not in session:
        session["country_name"] = random.choice(list(border_map.keys()))
        session["remaining_guesses"] = 5
        session["correct_guesses"] = []
        session["wrong_guesses"] = []
        session["available_options"] = sorted(list(set(sum(border_map.values(), []))))


    country_name = session["country_name"]
    border_names = border_map.get(country_name, [])

    # Remove previously guessed countries from available options
    session["available_options"] = [
        o for o in session["available_options"]
        if o not in session["correct_guesses"] + session["wrong_guesses"]
    ]

    # Get GeoJSON of the main country
    country_geojson = next(
        (f for f in geojson_data["features"]
         if f["properties"].get("name") == country_name),
        None
    )

    # GeoJSON for correct guesses (borders)
    correct_shapes = [
        f for f in geojson_data["features"]
        if f["properties"].get("name") in session["correct_guesses"]
    ]

    # GeoJSON for incorrect guesses
    wrong_shapes = [
        f for f in geojson_data["features"]
        if f["properties"].get("name") in session["wrong_guesses"]
    ]

    print("Correct guesses:", session["correct_guesses"])
    print("Correct shapes:", [f["properties"]["name"] for f in correct_shapes])

    return render_template(
        "index.html",
        country_name=country_name,
        border_count=len(border_names),
        country_geojson=country_geojson,
        correct_shapes=[correct_shapes],
        wrong_shapes=wrong_shapes,
        border_options=session["available_options"],
        attempts_left=session["remaining_guesses"],
        wrong_guesses=session["wrong_guesses"],
    )


@app.route("/submit", methods=["POST"])
def submit():
    guess = request.form.get("guess", "").strip()

    if "available_options" not in session:
        return redirect(url_for("index"))

    # Always sort before rendering
    dropdown_options = sorted(session["available_options"])

    # Remove guess from available options and sort
    if guess in dropdown_options:
        session["available_options"].remove(guess)
        session["available_options"] = sorted(session["available_options"])

    # Check if guess is correct or not
    country_name = session["country_name"]
    if guess in border_map.get(country_name, []):
        if guess not in session["correct_guesses"]:
            session["correct_guesses"].append(guess)
    else:
        if guess not in session["wrong_guesses"]:
            session["wrong_guesses"].append(guess)
            session["remaining_guesses"] -= 1

    return redirect(url_for("index"))


@app.route("/border-data/<country>")
def border_data(country):
    geometry = border_map.get(country)
    if geometry:
        return jsonify(geometry)
    return jsonify({})


@app.route('/reset')
def reset_session():
    session.clear()
    return redirect(url_for('index'))


def normalize(name):
    return name.lower().strip()


if __name__ == "__main__":
    app.run(debug=True)
