import json

from services.data_loader import (
    add_sea_borders,
    build_border_map,
    load_countries,
    load_eez_data,
    load_sea_zones,
)

# Load GeoJSONs
countries = load_countries()
eez = load_eez_data(countries)
seas = load_sea_zones(eez)
border_map = build_border_map(countries)
border_map = add_sea_borders(border_map, countries, seas)

with open("data/border_map.json", "w") as f:
    json.dump(border_map, f, indent=2)
