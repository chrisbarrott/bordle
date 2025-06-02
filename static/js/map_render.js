document.addEventListener("DOMContentLoaded", () => {
  const map = L.map("map", {
    center: [20, 0],
    zoom: 2,
    minZoom: 1,
    maxZoom: 10,
    zoomControl: true,
    attributionControl: false,
  });

  // White background instead of tiles
  document.getElementById("map").style.background = "#ffffff";

  // Helper function to add GeoJSON layers with a specific color
  function addLayer(shape, color) {
    if (!shape) return;
    L.geoJSON(shape, {
      style: {
        color: color,        // Border color
        fillColor: color,    // Fill color
        weight: 2,
        fillOpacity: 0.7,    // Controls how opaque the fill is
      },
    }).addTo(map);
  }

  // Add main country in black
  addLayer(countryShape, "black");

  // Add correct guesses in green
  addLayer(correctShapes, "green");

  // Add incorrect guesses in red
  addLayer(wrongShapes, "red");

  // Fit bounds to all shapes
  const allLayers = [];
  if (countryShape) allLayers.push(L.geoJSON(countryShape));
  if (correctShapes) allLayers.push(L.geoJSON(correctShapes));
  if (wrongShapes) allLayers.push(L.geoJSON(wrongShapes));

  if (allLayers.length > 0) {
    const group = L.featureGroup(allLayers);
    map.fitBounds(group.getBounds().pad(0.2));
  }
});
