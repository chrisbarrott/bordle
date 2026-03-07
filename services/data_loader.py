import geopandas as gpd


def load_countries():
    # Load shapefile
    countries = gpd.read_file("data/countries.geojson")

    # Filter unrecognised states
    countries = countries[
        (countries["SOVEREIGNT"] == countries["ADMIN"])
        & (countries["TYPE"] == "Sovereign country")
    ]
    countries = countries.reset_index(drop=True)
    return countries


# Load EEZ data
def load_eez_data(countries):
    eez = gpd.read_file("data/eez.geojson")
    eez = eez.to_crs(countries.crs)  # Match CRS
    return eez


# Group EEZ by sea names
def load_sea_zones(eez):
    sea_zones = eez[["TERRITORY1", "geometry"]].dissolve(by="TERRITORY1")
    sea_zones = sea_zones[sea_zones.is_valid]
    sea_zones = sea_zones.reset_index().rename(columns={"TERRITORY1": "name"})
    return sea_zones


# Get the country neighbours
def get_neighbours(country_name, countries):
    if country_name not in countries["ADMIN"].values:
        raise ValueError(f"{country_name} not found")

    target = countries[countries["ADMIN"] == country_name].geometry.iloc[0]

    neighbors = countries[countries.geometry.touches(target)]
    return sorted(neighbors["ADMIN"].tolist())


# Get the sea boarders
def get_sea_borders(country_name, countries, sea_zones):
    country = countries[countries["ADMIN"] == country_name]
    if country.empty:
        raise ValueError(f"{country_name} not found")

    country_geom = country.geometry.iloc[0]
    touching_seas = sea_zones[sea_zones.geometry.intersects(country_geom)]

    return sorted(touching_seas.index.tolist())


# Spatial join to find bordering countries
def build_border_map(countries_gdf):
    border_map = {}

    for idx, country in countries_gdf.iterrows():
        borders = []
        for idx2, other in countries_gdf.iterrows():
            if country["ISO_A3"] == other["ISO_A3"]:
                continue
            if country.geometry.touches(other.geometry):
                borders.append(other["SOVEREIGNT"])
        border_map[country["SOVEREIGNT"]] = borders

    return border_map


def add_sea_borders(border_map, countries_gdf, seas_gdf):
    for idx, country in countries_gdf.iterrows():
        sea_borders = seas_gdf[seas_gdf.geometry.touches(country.geometry)]
        sea_names = sea_borders["name"].tolist()
        border_map[country["SOVEREIGNT"]].extend(sea_names)

    return border_map
