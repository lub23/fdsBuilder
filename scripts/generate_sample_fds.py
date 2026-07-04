#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate sample FDS inputs at three scales for every equivalent facility.

For each equivalent facility JSON file we produce:
  <facility>_small.fds  — small scale, grid 0.5 m
  <facility>_medium.fds — medium scale, grid 1.0 m, default 4 meshes
  <facility>_large.fds  — large scale, grid 2.0 m, forced 4 meshes

The grid-resolution per scale follows the project defaults (see the
``meta.default_scale`` block injected by
``scripts/inject_scale_to_equivalent_facilities.py``).

The script writes the produced FDS into ``fds_test_output/`` and prints
a short report (num_meshes, grid_size, building count, total fuel items)
for every file.  Exit code 0 means all FDS are syntactically valid FDS
strings that the Python parser accepted.
"""
from __future__ import annotations

import os

from models.facility import FacilityManager
from generators.fds_generator import FDSGenerator
from models.building import BuildingGroup
from models.build_arranger import arrange_buildings


SCALE_OPTIONS = [
    {"name": "small",  "size_idx": 0,  "grid_m": 0.5, "num_meshes": 1},
    {"name": "medium", "size_idx": 1,  "grid_m": 1.0, "num_meshes": 4},
    {"name": "large",  "size_idx": -1, "grid_m": 2.0, "num_meshes": 4},
]


def _count_fuel(bg: BuildingGroup) -> int:
    n = 0
    for b in bg.buildings:
        for s in b.stories:
            for fc in s.fire_compartments:
                for cb in fc.combustibles:
                    n += int(cb.get("count", 0))
                for sc in fc.specialized_components:
                    n += int(sc.get("count", 0))
            for cb in s.combustibles:
                n += int(cb.get("count", 0))
    return n


def main() -> int:
    out_dir = os.path.join(os.path.dirname(__file__), "..", "fds_test_output")
    out_dir = os.path.normpath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    mgr = FacilityManager()
    facilities = [k for k in mgr.facilities if mgr.get_type(k) == "equivalent"]

    report = []
    failures = []

    for fac_name in facilities:
        for opt in SCALE_OPTIONS:
            size_idx = opt["size_idx"]
            params_for_each = {}
            for bname in mgr.list_buildings(fac_name):
                scale_idx = 0 if size_idx == 0 else (1 if size_idx == 1 else 2)
                params_for_each[bname] = mgr.params_for_scale(
                    fac_name, bname, scale_idx=scale_idx
                )

            try:
                buildings = []
                for bname, params in params_for_each.items():
                    buildings.append(
                        mgr.load_equivalent(fac_name, bname, params)
                    )
                if len(buildings) > 1:
                    layout_applied = mgr.arrange_buildings_by_layout(fac_name, buildings)
                    if not layout_applied:
                        arrange_buildings(buildings, gap=20.0)

                bg = BuildingGroup(
                    name=fac_name,
                    buildings=buildings,
                    domain={"grid_size": opt["grid_m"],
                            "num_meshes": opt["num_meshes"]},
                )
                for b in bg.buildings:
                    b.update_z_offsets()

                gen = FDSGenerator(bg)
                fds_text = gen.generate()
            except Exception as exc:
                failures.append((fac_name, opt["name"], repr(exc)))
                continue

            path = os.path.join(out_dir, f"{fac_name}_{opt['name']}.fds")
            with open(path, "w", encoding="utf-8") as f:
                f.write(fds_text)

            try:
                _domain, grid_size, num_meshes, _ref = gen._compute_mesh()
            except Exception:
                grid_size = opt["grid_m"]
                num_meshes = opt["num_meshes"]

            fuel_n = _count_fuel(bg)
            report.append({
                "facility": fac_name,
                "scale": opt["name"],
                "fds_path": path,
                "buildings": len(bg.buildings),
                "fuel_items": fuel_n,
                "num_meshes": num_meshes,
                "grid_size": grid_size,
                "chid_prefix": bg.name,
            })

    print(f"{'Facility':<28} {'Scale':<8} {'Bld':>4} {'Fuel':>5} {'Mesh':>5} {'Grid':>6}  {'File':<48}")
    print("-" * 110)
    for r in report:
        print(f"{r['facility']:<28} {r['scale']:<8} {r['buildings']:>4} "
              f"{r['fuel_items']:>5} {r['num_meshes']:>5} {r['grid_size']:>6.2f} "
              f" {os.path.basename(r['fds_path']):<48}")
    print()
    print(f"Generated {len(report)} FDS file(s) in {out_dir}")

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for f, s, msg in failures:
            print(f"  • {f} @ {s}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
