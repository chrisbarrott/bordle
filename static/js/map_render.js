document.addEventListener("DOMContentLoaded", () => {
  const map = L.map("map", {
    center: [20, 0],
    zoom: 2,
    minZoom: 1,
    maxZoom: 10,
    zoomControl: false, // use custom +/- controls
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
    // Blue background for ocean (always)
    document.getElementById("map").style.background = "#67b1fc";
  
    // Fetch and render a single GeoJSON outlines file from the static folder
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error('Failed to load border outlines');
        return r.json();
      })
      .then((geo) => {
        L.geoJSON(geo, { style: { color: '#777', weight: 1, fillOpacity: 0 } }).addTo(map);
      })
      .catch(() => {});

    // Load all countries in white as base layer
    fetch('/static/map_data/border_outlines.geojson')
      .then((r) => {
        if (!r.ok) throw new Error('Failed to load countries');
        return r.json();
      })
      .then((geo) => {
        L.geoJSON(geo, {
          style: {
            color: "#5f5f5f",     // Gray border
            fillColor: "#ffffff", // White fill
            weight: 1,
            fillOpacity: 0.8,
          },
        }).addTo(map);
      })
      .catch(() => console.log("[Map] Could not load base countries layer"));  
  }

  // Expose for external callers (e.g., hint prompt)
  window.addBorderOutlines = addBorderOutlines;

  if (window.SHOW_BORDER_LINES) {
    if (window.addBorderOutlines) {
      console.log("[Map] Adding border outlines as per game state.");
      window.addBorderOutlines('/static/map_data/border_outlines.geojson');
    }
  }
  
  // Add main country in black
  addLayer(countryShape, "black");

  // Add correct guesses in green
  addLayer(correctShapes, "green");

  // Add incorrect guesses in red
  addLayer(wrongShapes, "red");

  // Wire up custom zoom buttons (if present)
  const zi = document.getElementById('zoom-in');
  const zo = document.getElementById('zoom-out');
  if (zi) zi.addEventListener('click', () => map.zoomIn());
  if (zo) zo.addEventListener('click', () => map.zoomOut());

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
