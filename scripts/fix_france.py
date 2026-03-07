import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon

# Load the original GeoJSON
gdf = gpd.read_file("data/countries_shapes.json")

# Identify France by name
france_row = gdf[gdf["name"] == "France"].copy()

# Access its geometry
france_geom = france_row.iloc[0].geometry

# If it's a MultiPolygon (usually the case)
if isinstance(france_geom, MultiPolygon):
    # Keep only polygons roughly in Europe (Metropolitan France)
    # This removes French Guiana, Réunion, etc.
    mainland_polys = [
        poly for poly in france_geom.geoms
        if -10 < poly.centroid.x < 10 and 35 < poly.centroid.y < 55
    ]

    # Replace geometry with filtered MultiPolygon
    france_row.iloc[0].geometry = MultiPolygon(mainland_polys)

    # Update the full GeoDataFrame
    gdf.loc[gdf["name"] == "France", "geometry"] = france_row.iloc[0].geometry

    # Save to new file
    gdf.to_file("countries_shapes.json", driver="GeoJSON")
    print("✅ Saved filtered Metropolitan France only.")
else:
    print("❌ France geometry is not a MultiPolygon — unexpected format.")