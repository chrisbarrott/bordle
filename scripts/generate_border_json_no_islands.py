import json
import geopandas as gpd

# Load Natural Earth shapefile (update path as needed)
world = gpd.read_file("data/ne_10m_admin_0_countries/ne_10m_admin_0_countries.shp")

# Optional: Keep only UN-recognized sovereign countries
# world = world[world['SOVEREIGNT'] == world['ADMIN']]
# world = world[world['TYPE'] == 'Sovereign country']
# world = world[world['ADMIN'] != 'Antarctica']

# Filter out Antarctica and non-sovereign entries
world = world[world['ADMIN'] != 'Antarctica']
world = world[world['SOVEREIGNT'].notnull()]

# Dissolve to get unique sovereign entities (e.g. France with its territories)
world = world.dissolve(by="SOVEREIGNT").reset_index()

# Reproject to metric CRS for accurate geometric operations
world = world.to_crs("EPSG:3395")

# Build the border map
border_map = {}

# Build mapping
for idx, country in world.iterrows():
    name = country["SOVEREIGNT"]
    geom = country["geometry"]
    neighbors = []

    for _, other in world.iterrows():
        other_name = other["SOVEREIGNT"]
        if name == other_name:
            continue
        if geom.touches(other["geometry"]):
            neighbors.append(other_name)

    # Exclude island nations (i.e., no land neighbors)
    if neighbors:
        border_map[name] = sorted(neighbors)

# Save result to JSON
with open("border_map.json", "w", encoding="utf-8") as f:
    json.dump(border_map, f, indent=2, ensure_ascii=False)

print(f"Saved border_map.json with {len(border_map)} land-bordering countries.")