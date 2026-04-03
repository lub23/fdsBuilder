import json

# Check harbison_fischer with more details
with open("data/facilities/harbison_fischer.json", encoding="utf-8") as f:
    d = json.load(f)

print("=== harbison_fischer.json detailed ===")
for k, v in d["sub_types"].items():
    off = v.get("offset", {})
    length = v.get("building", {}).get("length", {}).get("min", 0)
    width = v.get("building", {}).get("width", {}).get("min", 0)
    print(f"{k}:")
    print(f"  offset: x={off.get('x', 0)}, y={off.get('y', 0)}")
    print(f"  building: L={length}, W={width}")

    # Calculate expected render position
    x_off = off.get("x", 0)
    y_off = off.get("y", 0)
    # In 3D viewer, building center is at (x_offset, y_offset)
    # So x_min = x_offset - L/2, x_max = x_offset + L/2
    x_min = x_off - length / 2
    x_max = x_off + length / 2
    y_min = y_off - width / 2
    y_max = y_off + width / 2
    print(f"  3D bounds: x[{x_min:.1f}, {x_max:.1f}], y[{y_min:.1f}, {y_max:.1f}]")
    print()
