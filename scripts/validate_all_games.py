import json

# Load country -> border map
with open("static/map_data/border_map.json", "r", encoding="utf-8") as f:
    country_borders = json.load(f)

# Load dropdown options
with open("static/map_data/country_drop_down.json", "r", encoding="utf-8") as f:
    dropdown_options = set(json.load(f))

# Track any borders that are missing from the dropdown
missing_borders = set()

for country, borders in country_borders.items():
    for neighbor in borders:
        if neighbor not in dropdown_options:
            missing_borders.add(neighbor)

if missing_borders:
    print("❌ These borders appear in country lists but are missing from the dropdown:")
    for country in sorted(missing_borders):
        print("-", country)
else:
    print("✅ All countries listed as borders are present in the dropdown list.")

    # --- First check: borders not in dropdown ---
missing_borders = set()
for borders in country_borders.values():
    for neighbor in borders:
        if neighbor not in dropdown_options:
            missing_borders.add(neighbor)

# --- Second check: dropdown items not in any border list ---
all_borders_used = set()
for borders in country_borders.values():
    all_borders_used.update(borders)

unused_dropdown_items = dropdown_options - all_borders_used

# --- Results ---
if missing_borders:
    print("❌ Borders listed in countries but missing from dropdown:")
    for country in sorted(missing_borders):
        print("-", country)
else:
    print("✅ All listed borders are in the dropdown.")

if unused_dropdown_items:
    print("\n⚠️ Dropdown options not referenced as borders anywhere:")
    for country in sorted(unused_dropdown_items):
        print("-", country)
else:
    print("✅ All dropdown items are referenced in at least one country’s border list.")
