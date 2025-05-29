import os

import geopandas as gpd

# Countries
countries = gpd.read_file("data/ne_10m_admin_0_countries/ne_10m_admin_0_countries.shp")
countries.to_file("data/ne_10m_admin_0_countries.geojson", driver="GeoJSON")

# Seas
# seas = gpd.read_file("data/ne_10m_geography_marine_polys/ne_10m_geography_marine_polys.shp")
# seas.to_file("data/ne_10m_geography_marine_polys.geojson", driver="GeoJSON")

# Load the EEZ shapefile
print(os.listdir("data/World_EEZ_v12_20231025"))

# eez = gpd.read_file("data/World_EEZ_v12_20231025/eez_boundaries_v12.shp")
# eez.to_file("data/eez.geojson", driver="GeoJSON")
