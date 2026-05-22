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


def _merge_combustibles(entries: list) -> list | None:
    """Replace old keys, sum counts for duplicates. Returns None if no change."""
    if not entries:
        return None

    changed = False
    merged: dict[str, dict] = {}
    order: list[str] = []  # preserve insertion order

    for entry in entries:
        old_key = entry.get("key", "")
        new_key = MERGE_MAP.get(old_key, old_key)
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


def _process_story(story: dict) -> bool:
    """Process combustibles in a single story dict. Returns True if modified."""
    modified = False

    story_comb = _merge_combustibles(story.get("combustibles", []))
    if story_comb is not None:
        story["combustibles"] = story_comb
        modified = True

    for fc in story.get("fire_compartments", []):
        fc_comb = _merge_combustibles(fc.get("combustibles", []))
        if fc_comb is not None:
            fc["combustibles"] = fc_comb
            modified = True

    for fcr in story.get("fire_compartment_ratios", []):
        fcr_comb = _merge_combustibles(fcr.get("combustibles", []))
        if fcr_comb is not None:
            fcr["combustibles"] = fcr_comb
            modified = True

        for fc in fcr.get("fire_compartments", []):
            fc_comb = _merge_combustibles(fc.get("combustibles", []))
            if fc_comb is not None:
                fc["combustibles"] = fc_comb
                modified = True

    return modified


def transform_json(filepath: Path) -> bool:
    """Transform one facility JSON. Returns True if modified."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    modified = False

    for building in data.get("buildings", []):
        for story in building.get("stories", []):
            if _process_story(story):
                modified = True
        for story in building.get("stories_template", []):
            if _process_story(story):
                modified = True

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return modified


def transform_all_jsons():
    """Transform all facility JSONs."""
    facilities_dir = ROOT / "facilities"
    modified_count = 0
    total_entries_removed = 0

    for fpath in sorted(glob.glob(str(facilities_dir / "*.json"))):
        before_keys = set()
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()
        # Count old keys in combustibles context (rough measurement)
        for old_key in MERGE_MAP:
            if old_key != MERGE_MAP[old_key] and f'"key": "{old_key}"' in text:
                before_keys.add(old_key)

        modified = transform_json(fpath)

        after_keys = set()
        text2 = Path(fpath).read_text(encoding="utf-8")
        for old_key in MERGE_MAP:
            if old_key != MERGE_MAP[old_key] and f'"key": "{old_key}"' in text2:
                after_keys.add(old_key)

        json_name = Path(fpath).name
        if before_keys:
            removed = before_keys - after_keys
            print(f"  {json_name}: removed {len(removed)} old key types ({len(before_keys)} → {len(after_keys)})")
            modified_count += 1
            total_entries_removed += len(removed)
        elif modified:
            print(f"  {json_name}: modified (counts merged)")

    print(f"  Total JSON files modified: {modified_count}")


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    print("=== Step 1: Removing merged keys from COMBUSTIBLE_LIBRARY ===")
    remove_keys_from_library()

    print()
    print("=== Step 2: Updating facility JSON files ===")
    transform_all_jsons()

    print()
    print("=== Done ===")


if __name__ == "__main__":
    main()
