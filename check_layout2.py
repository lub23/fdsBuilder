import json

# Analyze harbison_fischer according to md coordinates
with open("data/facilities/harbison_fischer.json", encoding="utf-8") as f:
    d = json.load(f)

print("=== Current JSON vs MD Required ===")
print()
print("According to MD file:")
print(
    "1. Main_Production_Hall: x[0,78], y[0,210] -> L=210(Y), W=78(X), offset=(39,105)"
)
print(
    "2. Incoming_Inspection (B): x[0,54], y[210,255] -> L=45(Y), W=54(X), offset=(27,232.5)"
)
print(
    "3. Southeast_Auxiliary (E): x[78,117], y[0,42] -> L=42(Y), W=39(X), offset=(97.5,21)"
)
print(
    "4. Office_Complex (D): x[78,134], y[70,132] -> L=62(Y), W=56(X), offset=(106,101)"
)
print(
    "5. Material_Surface_Treatment (C): x[78,113], y[132,229] -> L=97(Y), W=35(X), offset=(95.5,180.5)"
)
print()
print("Current JSON:")
for k, v in d["sub_types"].items():
    off = v.get("offset", {})
    length = v.get("building", {}).get("length", {}).get("min", 0)
    width = v.get("building", {}).get("width", {}).get("min", 0)
    print(f"  {k}: offset=({off.get('x', 0)},{off.get('y', 0)}), L={length}, W={width}")
