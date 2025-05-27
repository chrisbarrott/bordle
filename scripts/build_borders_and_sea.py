# Workaround: Load the GeoJSON file as raw JSON and manually simplify geometries for serialization

from shapely.geometry import shape, mapping
from shapely.geometry.multipolygon import MultiPolygon

import geopandas as gpd
import fiona
import json

# Load raw geometries from Natural Earth using Fiona instead of GeoPandas
path = gpd.datasets.get_path('naturalearth_lowres')
with fiona.open(path) as src:
    features = list(src)

# Build a simplified feature list
simplified_features = []
for feat in features:
    country_name = feat["properties"]["name"]
    geom = shape(feat["geometry"])
    if isinstance(geom, MultiPolygon):
        geom = max(geom.geoms, key=lambda g: g.area)
    simplified_features.append({
        "type": "Feature",
        "properties": {"name": country_name},
        "geometry": mapping(geom)
    })

# Add sea polygons
for sea_name, poly in seas.items():
    simplified_features.append({
        "type": "Feature",
        "properties": {"name": sea_name},
        "geometry": mapping(poly)
    })

# Final GeoJSON
geojson_data = {
    "type": "FeatureCollection",
    "features": simplified_features
}

# Save to file
output_path = "/data/border_map_with_seas.json"
with open(output_path, "w") as f:
    json.dump(geojson_data, f)

output_path
