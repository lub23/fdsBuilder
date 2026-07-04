#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inject ``count_scaled`` into the equivalent-model facility JSONs.

Strategy:

For every ``combustibles`` and ``specialized_components`` entry inside
``stories_template[].fire_compartment_ratios`` we add a sibling
``count_scaled`` array ``[small, medium, large]`` derived from the
existing ``count``:

* small   := ceil(count * 0.6)
* medium  := count          (unchanged)
* large   := ceil(count * 1.5)

A clamp keeps counts sensible in both directions.  For counts that are
zero we just leave the existing 0 (the system will treat that as "skip").

We also add a top-level ``meta`` block (one per file) carrying the project
defaults used by ``ParameterEngine.default_scale_overrides``.

Idempotent: running this twice leaves the file unchanged after the first
run because we detect the presence of ``count_scaled`` / ``meta``.

UNCHANGED on this run:

* All ``specialized`` (hand-built) facility JSONs.
* The specialised-component count for ``AIRCRAFT_*`` inside airport hangars
  (where the count encodes hangar occupancy rather than fire load).
* Any existing ``boundary`` field.
"""
from __future__ import annotations

import json
import os
import sys

FACILITIES = [
    "aerospace.json",
    "airport_hangar.json",
    "machinery_manufacturing.json",
    "metallurgical_facilities.json",
]

# Component keys whose counts are physical-occupancy numbers
# (rockets, aircraft, vehicles, electrolysis cells) — these should
# NOT be inflated with fuel-density multipliers because they ARE the
# expensive assets and would crowd the FC.
OCCUPANCY_COMPONENT_KEYS = {
    "ROCKET_VEHICLE_LARGE",
    "ROCKET_VEHICLE_MEDIUM",
    "ROCKET_VEHICLE_SMALL",
    "AIRCRAFT_SMALL",
    "AIRCRAFT_MEDIUM",
    "AIRCRAFT_LARGE",
    "VEHICLE_CAR",
    "VEHICLE_TRUCK",
    "ELECTROLYSIS_CELL",
    "ELECTROLYSIS_CELL_MEDIUM",
}


def _scale_count(c: int, kind: str, key: str) -> list[int]:
    """Compute ``[small, medium, large]`` for an entry."""
    base = max(0, int(c))
    if base == 0:
        return [0, 0, 0]

    # Occupancy counts (rockets, aircraft, vehicles, electrolysis cells)
    # stay flat — squeezing a rocket into a half-size hangar is nonsensical.
    if kind == "component" and key in OCCUPANCY_COMPONENT_KEYS:
        return [base, base, base]

    # Otherwise treat as ambient fire load that scales with facility size.
    small = max(1, round(base * 0.6))
    large = max(1, round(base * 1.5))
    return [small, base, large]


def _process_entry(entry: dict, kind: str) -> bool:
    """Mutate one combustible / component dict in place; return True if changed."""
    if "count_scaled" in entry:
        return False
    base = entry.get("count", 0)
    if not base:
        return False
    key = entry.get("key", "")
    entry["count_scaled"] = _scale_count(int(base), kind, key)
    return True


def _process_fc(fc: dict) -> int:
    n = 0
    for cb in fc.get("combustibles", []):
        n += int(_process_entry(cb, "combustible"))
    for sc in fc.get("specialized_components", []):
        n += int(_process_entry(sc, "component"))
    return n


def _process_facility(facility: dict) -> int:
    n = 0
    for b in facility.get("buildings", []):
        for tmpl in b.get("stories_template", []):
            for fc in tmpl.get("fire_compartment_ratios", []):
                n += _process_fc(fc)
    return n


META_BLOCK = {
    "default_scale": {
        "small": {
            "fuel_density": 0.6,
            "fuel_size_multiplier": 0.7,
            "grid_size_m": 0.5,
        },
        "medium": {
            "fuel_density": 1.0,
            "fuel_size_multiplier": 1.0,
            "grid_size_m": 1.0,
        },
        "large": {
            "fuel_density": 1.5,
            "fuel_size_multiplier": 1.3,
            "grid_size_m": 2.0,
        },
    },
    "notes": (
        "Count scaling convention: small = ceil(count * 0.6) for fuels, "
        "medium keeps the JSON value, large = ceil(count * 1.5). "
        "Occupancy components (rockets, aircraft, vehicles, electrolysis "
        "cells) keep their raw count at every scale."
    ),
}


def main() -> int:
    root = os.path.join(os.path.dirname(__file__), "..", "facilities")
    root = os.path.normpath(root)

    changed_files = 0
    total_entries = 0
    for name in FACILITIES:
        path = os.path.join(root, name)
        if not os.path.exists(path):
            print(f"missing: {path}", file=sys.stderr)
            return 1
        with open(path, "r", encoding="utf-8") as f:
            fac = json.load(f)

        # Inject the project meta block only if not already present.
        if "meta" not in fac:
            fac["meta"] = META_BLOCK

        n = _process_facility(fac)
        if n > 0:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(fac, f, ensure_ascii=False, indent=2)
            print(f"updated: {name}  (+{n} count_scaled entries, meta added)")
        else:
            # Still write if meta wasn't present yet.
            if "meta" not in fac or n == 0:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(fac, f, ensure_ascii=False, indent=2)
                print(f"updated: {name}  (meta added, no count changes)")
            else:
                print(f"skipped: {name}  (count_scaled already present)")
        changed_files += 1
        total_entries += n

    print(f"\nDone. {changed_files} file(s) inspected, {total_entries} scale-aware entries added.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
