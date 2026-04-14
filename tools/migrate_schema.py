#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration script: convert facility JSON files and building_config.json
from the old schema to the new dataclass-based schema.

Usage:
    python -m tools.migrate_schema          # migrate all files
    python -m tools.migrate_schema --dry-run  # preview without writing
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FACILITIES_DIR = Path(__file__).resolve().parent.parent / "data" / "facilities"
BUILDING_CONFIG = Path(__file__).resolve().parent.parent / "building_config.json"
BACKUP_DIR = FACILITIES_DIR / "_backup"

EQUIVALENT_FILES = {
    "aerospace",
    "airport_hangar",
    "machinery_manufacturing",
    "metallurgical_facilities",
}

WALL_INDEX_MAP = {0: "y_min", 1: "y_max", 2: "x_min", 3: "x_max"}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def resolve_value(p) -> float | int:
    """Extract a single numeric value from various representations.

    Accepts:
      - plain number
      - {"value": N, "unit": "m"} -> N
      - {"min": N, "max": N, ...} where min==max -> N
      - {"min": N, "max": M, ...} where min!=max -> min (fallback)
    """
    if isinstance(p, (int, float)):
        return p
    if isinstance(p, dict):
        if "value" in p:
            return p["value"]
        lo, hi = p.get("min"), p.get("max")
        if lo is not None and hi is not None:
            if lo == hi:
                return lo
            return lo  # fallback: use min
    return 0


def resolve_range_array(p) -> list[float]:
    """Convert a range dict to [min, max] or [min, max, median].

    Input: {"min": 50, "max": 120, "median": -1, "mean": -1, "unit": "m"}
    Output: [50, 120]  (or [50, 120, 85] if median > 0)
    """
    if isinstance(p, (int, float)):
        return [p, p]
    if isinstance(p, dict):
        lo = p.get("min", 0)
        hi = p.get("max", 0)
        result = [lo, hi]
        med = p.get("median", -1)
        if med is not None and med > 0:
            result.append(med)
        return result
    return [0, 0]


def position_to_w_offset(position: float, width: float, wall_length: float) -> float:
    """Convert 0-1 center-ratio position to absolute left-edge offset.

    w_offset = position * wall_length - width / 2
    """
    return position * wall_length - width / 2


def wall_index_to_wall_str(idx: int) -> str:
    """Map integer wall index to named wall string.

    0 -> "y_min", 1 -> "y_max", 2 -> "x_min", 3 -> "x_max"
    """
    return WALL_INDEX_MAP.get(idx, f"wall_{idx}")


# ---------------------------------------------------------------------------
# Specialized model migration
# ---------------------------------------------------------------------------

def _get_fc_wall_length(fc_boundary: list[float], wall: str) -> float:
    """Get the wall length for a fire compartment boundary given a wall name.

    fc_boundary = [x_min, x_max, y_min, y_max]
    For x_min/x_max walls -> span along y -> y_max - y_min
    For y_min/y_max walls -> span along x -> x_max - x_min
    """
    x_min, x_max, y_min, y_max = fc_boundary
    if wall in ("x_min", "x_max"):
        return y_max - y_min
    else:  # y_min, y_max
        return x_max - x_min


def _migrate_fc_opening_specialized(opening: dict, fc_boundary: list[float]) -> dict:
    """Convert a single opening from old FC format to new boundary-based format."""
    wall = opening["wall"]
    o_type = opening["type"]
    position = opening.get("position", 0.5)
    o_width = opening.get("width", 1.0)
    o_height = opening.get("height", 1.0)
    z_bottom = opening.get("z_bottom", 0)

    wall_length = _get_fc_wall_length(fc_boundary, wall)
    w_offset = position_to_w_offset(position, o_width, wall_length)

    result = {
        "wall": wall,
        "type": o_type,
        "boundary": [round(w_offset, 4), o_width, z_bottom, o_height],
    }
    # Preserve extra fields like "description"
    for k in opening:
        if k not in ("wall", "type", "position", "width", "height", "z_bottom"):
            result[k] = opening[k]
    return result


def migrate_specialized(old_data: dict) -> dict:
    """Convert a specialized facility JSON to the new schema.

    Transforms:
      - sub_types dict -> buildings array
      - building.length/width -> boundary [offset_x, length, offset_y, width]
      - FC x_ratio/y_ratio -> absolute boundary
      - Opening position -> boundary w_offset
      - Wraps FCs in story structure
    """
    cn_name = old_data.get("cn_name", "")
    result = {
        "type": "specialized",
        "cn_name": cn_name,
        "buildings": [],
    }

    sub_types = old_data.get("sub_types", {})
    for name, sub in sub_types.items():
        bld_info = sub.get("building", {})
        offset = sub.get("offset", {"x": 0, "y": 0})
        offset_x = offset.get("x", 0)
        offset_y = offset.get("y", 0)

        length_val = resolve_value(bld_info.get("length", 0))
        width_val = resolve_value(bld_info.get("width", 0))
        height_val = resolve_value(bld_info.get("height", 0))
        stories_val = resolve_value(bld_info.get("stories", 1))
        stories_count = max(1, int(stories_val))

        wall_thickness = sub.get("wall_thickness", 0.3)
        building_cn_name = sub.get("cn_name", "")

        building_boundary = [offset_x, length_val, offset_y, width_val]

        # Per-story height
        story_height = height_val / stories_count if stories_count > 0 else height_val

        # Migrate fire compartments
        old_fcs = sub.get("fire_compartments", [])
        new_fcs = []
        for fc in old_fcs:
            x_ratio = fc.get("x_ratio", [0, 1.0])
            y_ratio = fc.get("y_ratio", [0, 1.0])
            fc_x_min = x_ratio[0] * length_val
            fc_x_max = x_ratio[1] * length_val
            fc_y_min = y_ratio[0] * width_val
            fc_y_max = y_ratio[1] * width_val
            fc_boundary = [
                round(fc_x_min, 4),
                round(fc_x_max, 4),
                round(fc_y_min, 4),
                round(fc_y_max, 4),
            ]

            # Migrate openings within FC
            fc_openings = []
            for opening in fc.get("openings", []):
                fc_openings.append(
                    _migrate_fc_opening_specialized(opening, fc_boundary)
                )

            new_fc = {
                "name": fc.get("name", ""),
                "boundary": fc_boundary,
                "firewall_thickness": fc.get("wall_thickness", 0.3),
                "firewall_material": fc.get("wall_material", "CONCRETE"),
                "openings": fc_openings,
                "combustibles": fc.get("combustibles", []),
                "specialized_components": fc.get("specialized_components", []),
            }
            new_fcs.append(new_fc)

        # If no FCs, create a default one covering entire building
        if not new_fcs:
            new_fcs = [{
                "name": "default",
                "boundary": [0, length_val, 0, width_val],
                "firewall_thickness": wall_thickness,
                "firewall_material": "CONCRETE",
                "openings": [],
                "combustibles": [],
                "specialized_components": [],
            }]

        # Build stories
        stories = []
        for i in range(stories_count):
            story = {
                "name": f"{i + 1}F",
                "height": round(story_height, 4),
                "openings": [],
                "fire_compartments": new_fcs if i == 0 else _default_fcs(length_val, width_val, wall_thickness),
                "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
            }
            stories.append(story)

        building = {
            "name": name,
            "cn_name": building_cn_name,
            "boundary": building_boundary,
            "wall_thickness": wall_thickness,
            "height": height_val,
            "boundary_polygons": None,
            "stories": stories,
        }
        result["buildings"].append(building)

    return result


def _default_fcs(length: float, width: float, wall_thickness: float) -> list[dict]:
    """Generate a default fire compartment covering the entire building footprint."""
    return [{
        "name": "default",
        "boundary": [0, length, 0, width],
        "firewall_thickness": wall_thickness,
        "firewall_material": "CONCRETE",
        "openings": [],
        "combustibles": [],
        "specialized_components": [],
    }]


# ---------------------------------------------------------------------------
# Equivalent model migration
# ---------------------------------------------------------------------------

def _migrate_fc_opening_equivalent(opening: dict, length_val: float, width_val: float) -> dict:
    """Convert an FC opening to ratio-based representation for equivalent models."""
    wall = opening["wall"]
    o_type = opening["type"]
    position = opening.get("position", 0.5)
    o_width = opening.get("width", 1.0)
    o_height = opening.get("height", 1.0)
    z_bottom = opening.get("z_bottom", 0)

    # Determine wall_length for ratio conversion
    if wall in ("x_min", "x_max"):
        wall_length = width_val
    else:
        wall_length = length_val

    w_offset = position_to_w_offset(position, o_width, wall_length)
    w_offset_ratio = w_offset / wall_length if wall_length > 0 else 0
    width_ratio = o_width / wall_length if wall_length > 0 else 0

    result = {
        "wall": wall,
        "type": o_type,
        "w_offset_ratio": round(w_offset_ratio, 6),
        "width_ratio": round(width_ratio, 6),
        "height": o_height,
        "z_bottom": z_bottom,
    }
    for k in opening:
        if k not in ("wall", "type", "position", "width", "height", "z_bottom"):
            result[k] = opening[k]
    return result


def _range_dict_to_opening_ranges(d: dict) -> dict:
    """Convert doors/windows range dicts to range arrays."""
    if not d:
        return {}
    result = {}
    for key in ("width", "height", "count"):
        if key in d:
            result[key] = resolve_range_array(d[key])
    # Carry over z_bottom if present
    if "z_bottom" in d:
        result["z_bottom"] = d["z_bottom"]
    return result


def migrate_equivalent(old_data: dict) -> dict:
    """Convert an equivalent facility JSON to the new schema.

    Transforms:
      - sub_types dict -> buildings array
      - Dimension ranges -> range arrays (length_range, width_range, etc.)
      - Global doors/windows -> stories_template[0].doors/.windows
      - FC x_ratio/y_ratio -> boundary_ratio
      - Opening position -> w_offset_ratio, width_ratio
      - Add empty stories: []
    """
    cn_name = old_data.get("cn_name", "")
    result = {
        "type": "equivalent",
        "cn_name": cn_name,
        "buildings": [],
    }

    sub_types = old_data.get("sub_types", {})
    for name, sub in sub_types.items():
        bld_info = sub.get("building", {})
        offset = sub.get("offset", {"x": 0, "y": 0})

        # Range arrays for dimensions
        length_range = resolve_range_array(bld_info.get("length", 0))
        width_range = resolve_range_array(bld_info.get("width", 0))
        height_range = resolve_range_array(bld_info.get("height", 0))
        stories_range = resolve_range_array(bld_info.get("stories", 1))

        wall_thickness = sub.get("wall_thickness", 0.3)

        # Use max values for FC ratio computation
        length_val = length_range[1] if len(length_range) >= 2 else length_range[0]
        width_val = width_range[1] if len(width_range) >= 2 else width_range[0]

        # Migrate doors/windows to template
        doors_ranges = _range_dict_to_opening_ranges(sub.get("doors", {}))
        windows_ranges = _range_dict_to_opening_ranges(sub.get("windows", {}))

        # Migrate fire compartments to ratio-based
        old_fcs = sub.get("fire_compartments", [])
        new_fcs = []
        for fc in old_fcs:
            x_ratio = fc.get("x_ratio", [0, 1.0])
            y_ratio = fc.get("y_ratio", [0, 1.0])
            boundary_ratio = [
                round(x_ratio[0], 6),
                round(x_ratio[1], 6),
                round(y_ratio[0], 6),
                round(y_ratio[1], 6),
            ]

            # Migrate FC openings to ratios
            fc_openings = []
            for opening in fc.get("openings", []):
                fc_openings.append(
                    _migrate_fc_opening_equivalent(opening, length_val, width_val)
                )

            new_fc = {
                "name": fc.get("name", ""),
                "boundary_ratio": boundary_ratio,
                "firewall_thickness": fc.get("wall_thickness", 0.3),
                "firewall_material": fc.get("wall_material", "CONCRETE"),
                "openings": fc_openings,
                "combustibles": fc.get("combustibles", []),
                "specialized_components": fc.get("specialized_components", []),
            }
            new_fcs.append(new_fc)

        stories_template = [{
            "name": "1F",
            "height_range": height_range,
            "doors": doors_ranges,
            "windows": windows_ranges,
            "fire_compartments": new_fcs,
            "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
        }]

        building = {
            "name": name,
            "cn_name": sub.get("cn_name", ""),
            "description": sub.get("description", ""),
            "offset": offset,
            "length_range": length_range,
            "width_range": width_range,
            "height_range": height_range,
            "stories_range": stories_range,
            "wall_thickness": wall_thickness,
            "stories_template": stories_template,
            "stories": [],
            "specialized_components": sub.get("specialized_components", []),
        }
        result["buildings"].append(building)

    return result


# ---------------------------------------------------------------------------
# building_config.json migration
# ---------------------------------------------------------------------------

def _migrate_building_config_opening(opening: dict, building_length: float, building_width: float, walls: list[dict] | None = None) -> dict:
    """Convert a building_config opening from wall_index + position to wall str + boundary.

    wall_index: 0=y_min, 1=y_max, 2=x_min, 3=x_max, >=4 = internal wall
    """
    wall_idx = opening.get("wall_index", 0)
    o_type = opening.get("type", "door")
    position = opening.get("position", 0.5)
    o_width = opening.get("width", 1.0)
    o_height = opening.get("height", 1.0)
    z_bottom = opening.get("z_bottom", 0)

    if wall_idx < 4:
        wall_str = wall_index_to_wall_str(wall_idx)
        if wall_str in ("x_min", "x_max"):
            wall_length = building_width
        else:
            wall_length = building_length
    else:
        # Internal wall - use wall geometry if available
        wall_str = f"internal_{wall_idx}"
        wall_length = building_width  # default fallback
        if walls and wall_idx < len(walls):
            w = walls[wall_idx]
            dx = abs(w.get("x2", 0) - w.get("x1", 0))
            dy = abs(w.get("y2", 0) - w.get("y1", 0))
            wall_length = max(dx, dy)

    w_offset = position_to_w_offset(position, o_width, wall_length)

    return {
        "wall": wall_str,
        "type": o_type,
        "boundary": [round(w_offset, 4), o_width, z_bottom, o_height],
    }


def migrate_building_config(old_data: dict) -> dict:
    """Convert building_config.json to the new schema.

    Transforms:
      - length/width -> boundary [0, length, 0, width]
      - stories[].walls -> delete
      - stories[].openings[].wall_index -> wall (str)
      - openings position/width/height/z_bottom -> boundary [w_offset, width, z_bottom, height]
      - stories[].floor_slab -> previous story's roof
      - building-level roof -> last story's roof
      - No fire_compartments -> generate default FC
      - stories[].combustibles -> move into default FC
      - Wrap in {"building_group": {...}}
    """
    # Handle wrapped and unwrapped input
    if "building_group" in old_data:
        bg = old_data["building_group"]
    else:
        bg = old_data

    old_buildings = bg.get("buildings", [])
    new_buildings = []

    for bld in old_buildings:
        bld_name = bld.get("name", "")
        bld_length = bld.get("length", 0)
        bld_width = bld.get("width", 0)
        wall_thickness = bld.get("wall_thickness", 0.3)
        x_offset = bld.get("x_offset", 0)
        y_offset = bld.get("y_offset", 0)

        boundary = [x_offset, bld_length, y_offset, bld_width]
        building_roof = bld.get("roof", {"thickness": 0.2, "material": "CONCRETE"})

        old_stories = bld.get("stories", [])
        new_stories = []

        for s_idx, story in enumerate(old_stories):
            story_name = story.get("name", f"{s_idx + 1}F")
            story_height = story.get("height", 3.0)
            walls = story.get("walls", [])

            # Convert openings
            new_openings = []
            for opening in story.get("openings", []):
                new_openings.append(
                    _migrate_building_config_opening(
                        opening, bld_length, bld_width, walls
                    )
                )

            # Floor slab from this story becomes the roof of the previous story
            floor_slab = story.get("floor_slab", None)

            # Move combustibles into a default fire compartment
            combustibles = story.get("combustibles", [])
            default_fc = {
                "name": "default",
                "boundary": [0, bld_length, 0, bld_width],
                "firewall_thickness": wall_thickness,
                "firewall_material": "CONCRETE",
                "openings": [],
                "combustibles": combustibles,
                "specialized_components": [],
            }

            # Default roof for this story (will be overridden if floor_slab exists on next story)
            story_roof = {"thickness": 0.2, "material": "CONCRETE", "openings": []}

            new_story = {
                "name": story_name,
                "height": story_height,
                "openings": new_openings,
                "fire_compartments": [default_fc],
                "roof": story_roof,
            }
            new_stories.append(new_story)

        # Now wire up floor_slabs -> previous story's roof
        for s_idx, story in enumerate(old_stories):
            floor_slab = story.get("floor_slab", None)
            if floor_slab is not None and s_idx > 0:
                # This story's floor_slab is the roof of the previous story
                prev_roof = {
                    "thickness": floor_slab.get("thickness", 0.2),
                    "material": floor_slab.get("material", "CONCRETE"),
                    "openings": floor_slab.get("openings", []),
                }
                new_stories[s_idx - 1]["roof"] = prev_roof
            elif floor_slab is not None and s_idx == 0:
                # First story's floor slab: keep as ground floor slab info in roof
                # (unusual case, usually first story has no floor_slab from above)
                pass

        # Building-level roof -> last story's roof
        if new_stories and building_roof:
            last_roof = {
                "thickness": building_roof.get("thickness", 0.2),
                "material": building_roof.get("material", "CONCRETE"),
                "openings": building_roof.get("openings", []),
            }
            new_stories[-1]["roof"] = last_roof

        # Compute total height
        total_height = sum(s.get("height", 0) for s in old_stories)

        new_building = {
            "name": bld_name,
            "cn_name": bld_name,
            "boundary": boundary,
            "wall_thickness": wall_thickness,
            "height": total_height,
            "boundary_polygons": None,
            "stories": new_stories,
        }
        new_buildings.append(new_building)

    # Preserve other top-level fields
    new_data = {"building_group": {
        "buildings": new_buildings,
    }}
    # Carry over simulation-level keys from the original data
    for key in ("chid", "heat_source", "domain", "simulation_time", "output"):
        if key in old_data:
            new_data[key] = old_data[key]

    return new_data


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Migrate JSON schema to new format")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    # Ensure backup directory exists
    if not args.dry_run:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    summary = {"specialized": 0, "equivalent": 0, "building_config": 0, "errors": []}

    # Process facility JSON files
    facility_files = sorted(FACILITIES_DIR.glob("*.json"))
    for fpath in facility_files:
        stem = fpath.stem
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                old_data = json.load(f)

            if stem in EQUIVALENT_FILES:
                new_data = migrate_equivalent(old_data)
                summary["equivalent"] += 1
            else:
                new_data = migrate_specialized(old_data)
                summary["specialized"] += 1

            if args.dry_run:
                print(f"[DRY-RUN] Would migrate {fpath.name} ({stem})")
            else:
                # Backup original
                shutil.copy2(fpath, BACKUP_DIR / fpath.name)
                # Write migrated
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(new_data, f, ensure_ascii=False, indent=2)
                print(f"[OK] Migrated {fpath.name}")

        except Exception as e:
            summary["errors"].append(f"{fpath.name}: {e}")
            print(f"[ERROR] {fpath.name}: {e}", file=sys.stderr)

    # Process building_config.json
    if BUILDING_CONFIG.exists():
        try:
            with open(BUILDING_CONFIG, "r", encoding="utf-8") as f:
                old_data = json.load(f)

            new_data = migrate_building_config(old_data)
            summary["building_config"] = 1

            if args.dry_run:
                print(f"[DRY-RUN] Would migrate building_config.json")
            else:
                shutil.copy2(BUILDING_CONFIG, BACKUP_DIR / "building_config.json")
                with open(BUILDING_CONFIG, "w", encoding="utf-8") as f:
                    json.dump(new_data, f, ensure_ascii=False, indent=4)
                print(f"[OK] Migrated building_config.json")

        except Exception as e:
            summary["errors"].append(f"building_config.json: {e}")
            print(f"[ERROR] building_config.json: {e}", file=sys.stderr)

    # Print summary
    print("\n--- Migration Summary ---")
    print(f"Specialized facilities migrated: {summary['specialized']}")
    print(f"Equivalent facilities migrated:  {summary['equivalent']}")
    print(f"Building config migrated:        {summary['building_config']}")
    if summary["errors"]:
        print(f"Errors ({len(summary['errors'])}):")
        for err in summary["errors"]:
            print(f"  - {err}")
    else:
        print("No errors.")

    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
