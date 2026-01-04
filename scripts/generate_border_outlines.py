#!/usr/bin/env python
"""
Generate border_outlines.geojson from Natural Earth country shapes.
This creates a simplified GeoJSON with country boundaries only (no fills).
"""

import json
import geopandas as gpd
from pathlib import Path

# Load Natural Earth shapefile
world = gpd.read_file("data/ne_10m_admin_0_countries/ne_10m_admin_0_countries.shp")

# Optional: simplify geometries to reduce file size
# Tolerance depends on your zoom level (in degrees; 0.01 is ~1km at equator)
world["geometry"] = world["geometry"].simplify(tolerance=0.05)

# Keep only essential properties (ADMIN name and geometry)
world = world[["ADMIN", "geometry"]].copy()

# Convert to GeoJSON
geojson_data = json.loads(world.to_json())

# Save to static map data directory
output_path = Path("data/border_outlines.geojson")
output_path.parent.mkdir(parents=True, exist_ok=True)

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(geojson_data, f, ensure_ascii=False)

print(f"✅ Saved {output_path}")
print(f"   Features: {len(geojson_data['features'])}")
print(f"   File size: {output_path.stat().st_size / 1024:.1f} KB")
