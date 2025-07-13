from shapely.geometry import shape, mapping
import json

with open('data/countries_shapes.json') as f:
    data = json.load(f)

somalia_shapes = []
new_features = []

for feature in data['features']:
    name = feature['properties']['name']
    if name in ['Somalia', 'Somaliland']:
        somalia_shapes.append(shape(feature['geometry']))
    else:
        new_features.append(feature)

# Merge geometries
from shapely.ops import unary_union
merged_geom = unary_union(somalia_shapes)

# Add the merged Somalia
new_features.append({
    "type": "Feature",
    "properties": { "name": "Somalia" },
    "geometry": mapping(merged_geom)
})

# Write to new file
with open('data/countries_shapes.json', 'w') as f:
    json.dump({ "type": "FeatureCollection", "features": new_features }, f)