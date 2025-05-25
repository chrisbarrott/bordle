function renderMap() {
  const layers = [];

  // Base country in black
  if (countryShape) {
    layers.push({
      data: { values: countryShape },
      mark: { type: "geoshape", fill: "black", stroke: "white" }
    });
  }

  // Correct guesses in green
  if (correctShapes && correctShapes.length > 0) {
    correctShapes.forEach(shape => {
      layers.push({
        data: { values: shape },
        mark: { type: "geoshape", fill: "green", stroke: "white" }
      });
    });
  }

  // Incorrect guesses in red
  if (wrongShapes && wrongShapes.length > 0) {
    wrongShapes.forEach(shape => {
      layers.push({
        data: { values: shape },
        mark: { type: "geoshape", fill: "red", stroke: "white" }
      });
    });
  }

  const spec = {
    $schema: "https://vega.github.io/schema/vega-lite/v5.json",
    width: "container",
    height: 250,
    projection: { type: "equalEarth" },
    layer: layers
  };

  console.log("Country Shape:", countryShape);
  console.log("Correct Shapes:", correctShapes);
  console.log("Wrong Shapes:", wrongShapes);

  vegaEmbed("#map", spec, { actions: false });
}

document.addEventListener("DOMContentLoaded", renderMap);