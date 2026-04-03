import json

files = [
    "data/facilities/harbison_fischer.json",
    "data/facilities/alcoa.json",
    "data/facilities/frymaster_corporation.json",
    "data/facilities/gleason_cutting_tools_corporation.json",
    "data/facilities/materion_buffalo.json",
    "data/facilities/materion_newton.json",
]

for f in files:
    print(f"=== {f} ===")
    with open(f, "r", encoding="utf-8") as fp:
        d = json.load(fp)
    for k, v in d.get("sub_types", {}).items():
        off = v.get("offset", {})
        length = v.get("building", {}).get("length", {}).get("min", 0)
        width = v.get("building", {}).get("width", {}).get("min", 0)
        print(
            f"  {k}: offset=({off.get('x', 0)}, {off.get('y', 0)}), L={length}, W={width}"
        )
    print()
