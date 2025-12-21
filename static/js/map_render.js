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

  // Optionally load global border outlines (no fill)
  function addBorderOutlines(url) {
    // Fetch and render a single GeoJSON outlines file from the static folder
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error('Failed to load border outlines');
        return r.json();
      })
      .then((geo) => {
        L.geoJSON(geo, { style: { color: '#888', weight: 1, fillOpacity: 0 } }).addTo(map);
      })
      .catch(() => {});
  }

  // Add main country in black
  addLayer(countryShape, "black");

  // Add correct guesses in green
  addLayer(correctShapes, "green");

  // Add incorrect guesses in red
  addLayer(wrongShapes, "red");

  // Add border outlines if requested (flag provided by template)
  if (typeof showBorders !== 'undefined' && showBorders) {
    // Load from the static folder
    addBorderOutlines('/static/map_data/border_outlines.geojson');
  } else {
    // showBorders not enabled; no outlines will be loaded
  }

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
