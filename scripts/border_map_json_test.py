import json

with open("data/border_map.json") as f:
    border_map = json.load(f)

print("Total entries:", len(border_map))
print("Example: India borders", border_map.get("India"))
