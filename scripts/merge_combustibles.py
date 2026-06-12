#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merge similar combustibles: update COMBUSTIBLE_LIBRARY and all facility JSONs.

- Removes old (merged) keys from COMBUSTIBLE_LIBRARY in models/materials.py
- In each facility JSON, replaces old keys with new keys within each
  combustibles array, and merges duplicate entries by adding counts.
- specialized_components arrays are NOT touched (they reference SPECIALIZED_COMPONENTS).
"""

import ast
import json
import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Merge Map: old_key → new_key ──────────────────────────────────────────
MERGE_MAP: dict[str, str] = {
    # Group 1: 木制家具 → WOODEN_FURNITURE
    "WOOD_TABLE": "WOODEN_FURNITURE",
    "WOOD_CHAIR": "WOODEN_FURNITURE",
    "WOOD_FURNITURE": "WOODEN_FURNITURE",
    "MEETING_TABLE": "WOODEN_FURNITURE",
    "OFFICE_COMPOSITE_FURNITURE": "WOODEN_FURNITURE",
    "OFFICE_FURNITURE": "WOODEN_FURNITURE",

    # Group 2: 木制包装/托盘 → WOODEN_PALLET
    "WOOD_PALLET": "WOODEN_PALLET",
    "WOODEN_BOX": "WOODEN_PALLET",
    "TEMP_TIMBER_WORKS": "WOODEN_PALLET",
    "PACKING_BOX": "WOODEN_PALLET",
    "PACKING_MATERIAL": "WOODEN_PALLET",

    # Group 3: 纸制品 → PAPER_STACK
    "PAPER_ARCHIVE": "PAPER_STACK",
    "PAPER_BOX": "PAPER_STACK",
    "CARDBOARD_BOX": "PAPER_STACK",
    "DENSE_ARCHIVE": "PAPER_STACK",
    "BOOKSHELF": "PAPER_STACK",
    "DISPLAY_PROP_MODEL": "PAPER_STACK",

    # Group 4: 电缆 → CABLE_BUNDLE
    "CABLE": "CABLE_BUNDLE",
    "CABLE_REEL": "CABLE_BUNDLE",
    "CABLE_TRAY": "CABLE_BUNDLE",
    "CABLE_BRIDGE": "CABLE_BUNDLE",
    "CABLE_INSULATION": "CABLE_BUNDLE",
    "CONTROL_CABLE": "CABLE_BUNDLE",
    "CONTROL_CABLE_BRIDGE": "CABLE_BUNDLE",
    "FIRE_PUMP_CABLE": "CABLE_BUNDLE",
    "MONITOR_CABLE": "CABLE_BUNDLE",
    "NETWORK_CABLE": "CABLE_BUNDLE",

    # Group 5: 电气设备 → ELECTRICAL_EQUIPMENT
    "SWITCH_CABINET": "ELECTRICAL_EQUIPMENT",
    "ELECTRICAL_PLASTIC": "ELECTRICAL_EQUIPMENT",
    "ELECTRICAL_PANEL": "ELECTRICAL_EQUIPMENT",
    "ELECTRICAL_CABINET": "ELECTRICAL_EQUIPMENT",
    "CONTROL_CABINET": "ELECTRICAL_EQUIPMENT",
    "SERVER_CABINET": "ELECTRICAL_EQUIPMENT",
    "ELECTRONICS_CONSOLE": "ELECTRICAL_EQUIPMENT",
    "FIRE_CONTROL_HOST": "ELECTRICAL_EQUIPMENT",

    # Group 6: 橡胶材料 → RUBBER_MATERIAL
    "RUBBER_POLYMER_PARTS": "RUBBER_MATERIAL",
    "RUBBER_HOSE": "RUBBER_MATERIAL",
    "RUBBER_HOSE_ASSEMBLY": "RUBBER_MATERIAL",
    "RUBBER_LINED_PIPE": "RUBBER_MATERIAL",
    "RUBBER_PART": "RUBBER_MATERIAL",
    "RUBBER_PIPE_INSULATION": "RUBBER_MATERIAL",
    "RUBBER_CONVEYOR_BELT": "RUBBER_MATERIAL",
    "CONVEYOR_BELT": "RUBBER_MATERIAL",
    "POLYMER_MATERIAL": "RUBBER_MATERIAL",
    "FRP_RUBBER_PANEL": "RUBBER_MATERIAL",

    # Group 7: 塑料 → PLASTIC_PACKAGING
    "PLASTIC_BIN": "PLASTIC_PACKAGING",
    "PLASTIC_EQUIPMENT": "PLASTIC_PACKAGING",
    "PLASTIC_SHEETS": "PLASTIC_PACKAGING",
    "PLASTIC_FILM": "PLASTIC_PACKAGING",
    "FOAM_PACKAGING": "PLASTIC_PACKAGING",
    "ESD_PACKAGING_MATERIAL": "PLASTIC_PACKAGING",
    "ADHESIVE_SEALANT_SET": "PLASTIC_PACKAGING",
    "PREPREG_MATERIAL": "PLASTIC_PACKAGING",

    # Group 8: 油品/油桶 → LUBE_OIL_DRUM
    "INDUSTRIAL_OIL_DRUM": "LUBE_OIL_DRUM",
    "LUBE_OIL": "LUBE_OIL_DRUM",
    "LUBRICATION_OIL": "LUBE_OIL_DRUM",
    "HYDRAULIC_OIL": "LUBE_OIL_DRUM",
    "MINERAL_OIL": "LUBE_OIL_DRUM",
    "RUST_PREVENTION_OIL": "LUBE_OIL_DRUM",
    "CUTTING_FLUID_IBC": "LUBE_OIL_DRUM",
    "GRINDING_SLUDGE_BIN": "LUBE_OIL_DRUM",

    # Group 9: 油箱 → HYDRAULIC_TANK
    "HYDRAULIC_OIL_TANK": "HYDRAULIC_TANK",
    "LUBE_OIL_TANK": "HYDRAULIC_TANK",
    "SEAL_OIL_TANK": "HYDRAULIC_TANK",
    "DAILY_OIL_TANK": "HYDRAULIC_TANK",
    "CELL_SIDE_HYDRAULIC_OIL": "HYDRAULIC_TANK",
    "CRANE_HYDRAULIC_TANK": "HYDRAULIC_TANK",
    "HEAVY_OIL_TANK": "HYDRAULIC_TANK",
    "DIESEL_TANK": "HYDRAULIC_TANK",

    # Group 10: 油浸电气 → OIL_TRANSFORMER
    "TRANSFORMER_OIL_TANK": "OIL_TRANSFORMER",
    "OIL_CIRCUIT_BREAKER": "OIL_TRANSFORMER",
    "IGNITION_OIL_DEVICE": "OIL_TRANSFORMER",

    # Group 11: 溶剂 → ORGANIC_SOLVENT_DRUM
    "COATING_AGENT_DRUM": "ORGANIC_SOLVENT_DRUM",
    "COATING_SOLVENT": "ORGANIC_SOLVENT_DRUM",
    "PAINT_THINNER_DRUM": "ORGANIC_SOLVENT_DRUM",
    "PAINT_SOLVENT": "ORGANIC_SOLVENT_DRUM",
    "PAINT_DRUM": "ORGANIC_SOLVENT_DRUM",
    "SOLVENT": "ORGANIC_SOLVENT_DRUM",
    "SOLVENT_CLEANER": "ORGANIC_SOLVENT_DRUM",
    "HAZARDOUS_CHEMICAL": "ORGANIC_SOLVENT_DRUM",

    # Group 12: 化工品 → CHEMICAL_DRUM
    "PROCESS_CHEMICAL_CONTAINER": "CHEMICAL_DRUM",
    "CHEMICAL_REAGENT": "CHEMICAL_DRUM",
    "CHEMICAL_SAMPLE": "CHEMICAL_DRUM",

    # Group 13: 织物 → TEXTILE_ROLL
    "CURTAIN": "TEXTILE_ROLL",
    "CARPET_FINISH": "TEXTILE_ROLL",
    "ACOUSTIC_PANEL": "TEXTILE_ROLL",
    "UPHOLSTERED_SEAT": "TEXTILE_ROLL",
    "FABRIC_SOFA": "TEXTILE_ROLL",
    "MATTRESS": "TEXTILE_ROLL",
    "OILY_WASTE_BIN": "TEXTILE_ROLL",
    "OILY_RAGS": "TEXTILE_ROLL",

    # Group 14: 办公用品 → OFFICE_SUPPLIES
    "OFFICE_CHAIR": "OFFICE_SUPPLIES",
    "OFFICE_EQUIPMENT": "OFFICE_SUPPLIES",

    # Group 15: 金属 → METAL_PARTS
    "METAL_SCRAP": "METAL_PARTS",
    "SPARE_PARTS_METAL": "METAL_PARTS",
    "ACCESSORIES": "METAL_PARTS",
    "ASSEMBLY_PARTS": "METAL_PARTS",
    "TOOL_BOX": "METAL_PARTS",
    "FINISHED_PRODUCT": "METAL_PARTS",

    # Group 16: 涂层/表面 → SURFACE_COATING_LAYER
    "BITUMEN_MEMBRANE": "SURFACE_COATING_LAYER",
    "FIBER_INSULATION_LAYER": "SURFACE_COATING_LAYER",
    "POLISHING_PASTE_BIN": "SURFACE_COATING_LAYER",
}

# Keys to keep (any key NOT in this set as a value in the map will be removed)
KEEP_KEYS = set(MERGE_MAP.values())

# ── Per-Facility Merge Map (second round: 5-6 types per facility) ──────────
# Each facility maps some post-merge keys into broader retained keys.
# KEY = filename stem (without .json)
PER_FACILITY_MERGE: dict[str, dict[str, str]] = {
    "aerospace": {
        "PLASTIC_PACKAGING": "PAPER_STACK",
        "ELECTRICAL_EQUIPMENT": "CABLE_BUNDLE",
        "WOODEN_FURNITURE": "WOODEN_PALLET",
        "LIGHTWEIGHT_PARTITION": "WOODEN_PALLET",
        "LUBE_OIL_DRUM": "ORGANIC_SOLVENT_DRUM",
        "LIQUID_FUEL_DRUM": "ORGANIC_SOLVENT_DRUM",
        "RUBBER_MATERIAL": "CABLE_BUNDLE",
    },
    "airport_hangar": {
        "PLASTIC_PACKAGING": "PAPER_STACK",
        "WOODEN_FURNITURE": "WOODEN_PALLET",
        "LIGHTWEIGHT_PARTITION": "WOODEN_PALLET",
        "LUBE_OIL_DRUM": "ORGANIC_SOLVENT_DRUM",
        "TEXTILE_ROLL": "PAPER_STACK",
        "SURFACE_COATING_LAYER": "PAPER_STACK",
    },
    "alcoa": {
        "LUBE_OIL_DRUM": "HYDRAULIC_TANK",
        "CHEMICAL_DRUM": "HYDRAULIC_TANK",
        "LAB_EQUIPMENT": "CABLE_BUNDLE",
    },
    "frymaster_corporation": {},
    "gleason_cutting_tools_corporation": {},
    "harbison_fischer": {
        "ORGANIC_SOLVENT_DRUM": "LUBE_OIL_DRUM",
        "TEXTILE_ROLL": "PAPER_STACK",
    },
    "machinery_manufacturing": {
        "WOODEN_FURNITURE": "PAPER_STACK",
        "TEXTILE_ROLL": "PAPER_STACK",
        "ORGANIC_SOLVENT_DRUM": "LUBE_OIL_DRUM",
        "OILY_SLUDGE_CONTAINER": "LUBE_OIL_DRUM",
        "CHEMICAL_DRUM": "LUBE_OIL_DRUM",
        "RUBBER_MATERIAL": "ELECTRICAL_EQUIPMENT",
        "COMBUSTIBLE_GAS_CYLINDER": "METAL_DUST_COLLECTOR",
    },
    "materion_buffalo": {
        "WOODEN_FURNITURE": "WOODEN_PALLET",
        "TEXTILE_ROLL": "PAPER_STACK",
        "RUBBER_MATERIAL": "PLASTIC_PACKAGING",
        "ORGANIC_SOLVENT_DRUM": "LUBE_OIL_DRUM",
    },
    "materion_newton": {},
    "metallurgical_facilities": {
        "COAL_STACK": "CARBON_MATERIAL_STACK",
        "COAL_DUST_HOPPER": "CARBON_MATERIAL_STACK",
        "COMBUSTIBLE_GAS_CYLINDER": "METAL_DUST_COLLECTOR",
        "WOODEN_FURNITURE": "PAPER_STACK",
        "TEXTILE_ROLL": "PAPER_STACK",
        "PLASTIC_PACKAGING": "PAPER_STACK",
        "SURFACE_COATING_LAYER": "PAPER_STACK",
        "ORGANIC_SOLVENT_DRUM": "LUBE_OIL_DRUM",
        "LIQUID_FUEL_DRUM": "LUBE_OIL_DRUM",
        "RUBBER_MATERIAL": "ELECTRICAL_EQUIPMENT",
    },
    "warrick_power_plant": {
        "ELECTRICAL_EQUIPMENT": "CABLE_BUNDLE",
        "OFFICE_SUPPLIES": "PAPER_STACK",
        "WOODEN_FURNITURE": "PAPER_STACK",
        "DECORATION_MATERIAL": "PAPER_STACK",
        "EMERGENCY_SUPPLIES": "PAPER_STACK",
        "ORGANIC_SOLVENT_DRUM": "LUBE_OIL_DRUM",
        "CHEMICAL_DRUM": "LUBE_OIL_DRUM",
        "DIESEL_DRUM": "LUBE_OIL_DRUM",
        "PLASTIC_PACKAGING": "RUBBER_MATERIAL",
        "HYDRAULIC_TANK": "OIL_TRANSFORMER",
        "COAL_STACK": "WOODEN_PALLET",
        "COAL_DUST_HOPPER": "WOODEN_PALLET",
    },
}

# ── Part 1: Remove old keys from COMBUSTIBLE_LIBRARY in materials.py ───────


def _entry_end(lines: list[str], start: int) -> int:
    """Find the end line (exclusive) of a dict entry starting at `start`.

    The entry looks like:
        "KEY": {
            ...
        },
    Returns the index of the line AFTER the closing }, (or `)
    """
    depth = 0
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        for ch in stripped:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
        if depth == 0 and stripped.endswith(","):
            return i + 1
        if depth == 0 and stripped == "}":
            return i + 1
    return len(lines)


def remove_keys_from_library():
    """Remove old/merged keys from COMBUSTIBLE_LIBRARY."""
    filepath = ROOT / "models" / "materials.py"
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Find all entries in COMBUSTIBLE_LIBRARY
    lib_start = None
    lib_end = None
    for i, line in enumerate(lines):
        if line.strip().startswith("COMBUSTIBLE_LIBRARY"):
            lib_start = i
        if lib_start is not None and line.strip() == "}":
            lib_end = i + 1  # exclusive

    if lib_start is None or lib_end is None:
        print("ERROR: Could not find COMBUSTIBLE_LIBRARY in materials.py")
        sys.exit(1)

    # Extract entries from the library
    # Each entry starts with a line like: "    KEY_NAME": {
    key_pat = re.compile(r'^\s{4}"([A-Z_]+)":\s*\{')

    entries: list[tuple[int, int, str]] = []  # (start_line, end_line, key)
    i = lib_start + 1
    while i < lib_end:
        line = lines[i]
        m = key_pat.match(line)
        if m:
            key = m.group(1)
            end = _entry_end(lines, i)
            entries.append((i, end, key))
            i = end
        else:
            i += 1

    # Find entries to remove (old keys that are merged into another)
    keys_to_remove = set()
    for old_key, new_key in MERGE_MAP.items():
        if old_key != new_key:
            keys_to_remove.add(old_key)

    # Remove entries from the line list (process in reverse order to preserve indices)
    to_remove_entries = [(s, e) for s, e, k in entries if k in keys_to_remove]
    for start, end in reversed(to_remove_entries):
        del lines[start:end]

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)

    removed_count = len(to_remove_entries)
    print(f"  materials.py: removed {removed_count} old keys from COMBUSTIBLE_LIBRARY")


# ── Part 2: Transform facility JSONs ──────────────────────────────────────


def _merge_combustibles(entries: list, extra_map: dict[str, str] | None = None) -> list | None:
    """Replace old keys, sum counts for duplicates. Returns None if no change.

    First applies the global MERGE_MAP, then the optional extra_map
    (used for per-facility second-round merges).
    """
    if not entries:
        return None

    changed = False
    merged: dict[str, dict] = {}
    order: list[str] = []  # preserve insertion order

    for entry in entries:
        old_key = entry.get("key", "")
        new_key = MERGE_MAP.get(old_key, old_key)
        if extra_map:
            new_key = extra_map.get(new_key, new_key)
        if new_key != old_key:
            changed = True

        count = entry.get("count", 1)

        if new_key in merged:
            merged[new_key]["count"] = (
                merged[new_key].get("count", 1) + count
            )
            changed = True
        else:
            merged[new_key] = dict(entry)
            merged[new_key]["key"] = new_key
            order.append(new_key)

    if not changed:
        return None

    result = [merged[k] for k in order]
    return result


def _process_story(story: dict, extra_map: dict[str, str] | None = None) -> bool:
    """Process combustibles in a single story dict. Returns True if modified."""
    modified = False

    story_comb = _merge_combustibles(story.get("combustibles", []), extra_map)
    if story_comb is not None:
        story["combustibles"] = story_comb
        modified = True

    for fc in story.get("fire_compartments", []):
        fc_comb = _merge_combustibles(fc.get("combustibles", []), extra_map)
        if fc_comb is not None:
            fc["combustibles"] = fc_comb
            modified = True

    for fcr in story.get("fire_compartment_ratios", []):
        fcr_comb = _merge_combustibles(fcr.get("combustibles", []), extra_map)
        if fcr_comb is not None:
            fcr["combustibles"] = fcr_comb
            modified = True

        for fc in fcr.get("fire_compartments", []):
            fc_comb = _merge_combustibles(fc.get("combustibles", []), extra_map)
            if fc_comb is not None:
                fc["combustibles"] = fc_comb
                modified = True

    return modified


def transform_json(filepath: Path) -> bool:
    """Transform one facility JSON. Returns True if modified."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Per-facility merge map (second-round: 5-6 types per facility)
    fname = filepath.stem  # e.g. "aerospace", "alcoa"
    extra_map = PER_FACILITY_MERGE.get(fname, {})

    modified = False

    for building in data.get("buildings", []):
        for story in building.get("stories", []):
            if _process_story(story, extra_map):
                modified = True
        for story in building.get("stories_template", []):
            if _process_story(story, extra_map):
                modified = True

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return modified


def _get_comb_keys(text: str) -> set[str]:
    """Extract all distinct combustible keys from JSON text."""
    import re
    return set(re.findall(r'"key":\s*"([A-Z_]+)"', text))


def transform_all_jsons():
    """Transform all facility JSONs (applies global + per-facility merge maps)."""
    facilities_dir = ROOT / "facilities"
    modified_count = 0
    total_merged_types = 0

    for fpath_str in sorted(glob.glob(str(facilities_dir / "*.json"))):
        fpath = Path(fpath_str)
        text = fpath.read_text(encoding="utf-8")
        before_keys = _get_comb_keys(text)
        before_count = len(before_keys)

        modified = transform_json(fpath)

        text2 = fpath.read_text(encoding="utf-8")
        after_keys = _get_comb_keys(text2)
        after_count = len(after_keys)

        json_name = fpath.name
        if modified:
            fname = fpath.stem
            extra = PER_FACILITY_MERGE.get(fname, {})
            extra_desc = f" (per-facility: {len(extra)} mappings)" if extra else ""
            print(f"  {json_name}: {before_count} → {after_count} combustible types{extra_desc}")
            if before_count - after_count > 0:
                merged_types = before_keys - after_keys
                print(f"           merged: {sorted(merged_types)}")
            modified_count += 1
            total_merged_types += before_count - after_count
        else:
            print(f"  {json_name}: unchanged ({before_count} types)")

    print(f"  Files modified: {modified_count}, total type reduction: {total_merged_types}")


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    print("=== Step 1: Removing orphan keys from COMBUSTIBLE_LIBRARY ===")
    remove_keys_from_library()

    print()
    print("=== Step 2: Applying per-facility second-round merges ===")
    transform_all_jsons()

    print()
    print("=== Done ===")


if __name__ == "__main__":
    main()
