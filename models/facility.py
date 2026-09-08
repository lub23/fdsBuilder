#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File  : facility.py
@Author: Lubber
@Date  : 2026-03-09
@Version : 2.0
@Desc  : Simplified facility data management for the new JSON schema.
         Specialized buildings load directly via Building.from_dict().
         Equivalent buildings are generated via ParameterEngine.
"""

import json
import os
import sys
from typing import Dict

from models.building import Building
from models.parameter_engine import ParameterEngine


SCALE_KEYS = {
    0: "small",
    1: "medium",
    2: "large",
}
SCALE_INDICES = {value: key for key, value in SCALE_KEYS.items()}


def facilities_dir() -> str:
    """Directory holding facility definitions (JSON + reference FDS files).

    In a PyInstaller bundle package data is copied to the extraction root;
    in a source tree it is the project's ``facilities/`` folder.
    """
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return os.path.join(bundle_root, "facilities")
    return os.path.join(os.path.dirname(__file__), "..", "facilities")


class FacilityManager:
    def __init__(self):
        self.facilities: Dict[str, dict] = {}
        self._load_all(facilities_dir())

    def _load_all(self, data_dir: str):
        """Load all JSON files from ./facilities/"""
        filenames = sorted(f for f in os.listdir(data_dir) if f.endswith(".json"))
        for filename in filenames:
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            stem = filename[:-5]  # remove .json
            self.facilities[stem] = data

    def get_type(self, facility_name: str) -> str:
        """Return 'specialized' or 'equivalent'"""
        return self.facilities[facility_name]["type"]

    def list_buildings(self, facility_name: str) -> list:
        """List building names in a facility"""
        return [b["name"] for b in self.facilities[facility_name]["buildings"]]

    def get_building_data(self, facility_name: str, building_name: str) -> dict:
        """Get raw building dict from facility"""
        return self._find_building(facility_name, building_name)

    def load_specialized(self, facility_name: str, building_name: str) -> Building:
        """Load a specialized building directly (no conversion)"""
        bdata = self._find_building(facility_name, building_name)
        building = Building.from_dict(bdata)
        building.update_z_offsets()
        return building

    def load_equivalent(self, facility_name: str, building_name: str, params: dict,
                        current_offset: tuple[float, float] | None = None,
                        auto_arrange: bool = False,
                        arrange_gap: float = 20.0) -> Building:
        """Generate a building from equivalent model template + user params.

        ``params`` is forwarded to ``ParameterEngine.generate``.  The
        following optional keys are recognised for scale-aware generation:
        - ``scale_idx`` (0/1/2  or -1 for "large")
        - ``fuel_density`` (override for the scale's default density)
        - ``fuel_size_multiplier`` (override)

        ``auto_arrange`` and ``arrange_gap`` are no-ops in this single-load
        API because they need sibling buildings; for batch generation use
        ``load_equivalent_batch`` or call ``arrange_buildings`` explicitly
        on the resulting list.
        """
        bdata = self._find_building(facility_name, building_name)
        building = ParameterEngine.generate(bdata, params, current_offset)
        scale_idx = ParameterEngine.normalise_scale_idx(params.get("scale_idx", 1))
        scale_key = SCALE_KEYS[scale_idx]
        scale_names = bdata.get("scale_names", {})
        if scale_key in scale_names:
            building.cn_name = scale_names[scale_key]
        return building

    def load_equivalent_batch(
        self,
        facility_name: str,
        params_for_building: dict,
        auto_arrange: bool = True,
        arrange_gap: float = 20.0,
    ) -> list:
        """Generate every building in *facility_name* at the given scale.

        ``params_for_building`` maps each building name to its own params
        dict (which must include ``length/width/height/stories`` and
        ``scale_idx``).  When ``auto_arrange`` is true, a facility-level
        ``layout`` is applied first; legacy templates without layout fall
        back to X-axis packing.
        """
        from models.build_arranger import arrange_buildings

        buildings = []
        for bname in self.list_buildings(facility_name):
            params = params_for_building.get(bname)
            if params is None:
                continue
            buildings.append(self.load_equivalent(facility_name, bname, params))

        if auto_arrange and len(buildings) > 1:
            layout_applied = self.arrange_buildings_by_layout(facility_name, buildings)
            if not layout_applied:
                arrange_buildings(buildings, gap=arrange_gap)
        return buildings

    def default_params(self, facility_name: str, building_name: str) -> dict:
        """Get default parameter values for an equivalent model building.
        Returns dict with length, width, height, stories (default values from ranges)
        and their ranges for UI display."""
        bdata = self._find_building(facility_name, building_name)
        params = self.params_for_scale(facility_name, building_name, scale_idx=1)
        params["ranges"] = {
            "length": bdata.get("length_range", [0, 0]),
            "width": bdata.get("width_range", [0, 0]),
            "height": bdata.get("height_range", [0, 0]),
            "stories": bdata.get("stories_range", [1, 1]),
        }
        params["scale_values"] = self.scale_dimension_options(facility_name, building_name)
        return params

    def params_for_scale(
        self,
        facility_name: str,
        building_name: str,
        scale_idx: int = 1,
    ) -> dict:
        """Return concrete generation params for a building at a scale.

        Equivalent JSONs may provide explicit ``scale_dimensions``:
        ``{"small": {...}, "medium": {...}, "large": {...}}``.  Those values
        are preferred over legacy ``*_range`` fields because they make the
        small / medium / large dimensions unambiguous.  If the block is absent,
        the legacy ranges are interpreted as ``[min, max, default]``.
        """
        bdata = self._find_building(facility_name, building_name)
        scale_idx = ParameterEngine.normalise_scale_idx(scale_idx)
        fixed_scale = self.facilities[facility_name].get("meta", {}).get("fixed_scale")
        if fixed_scale in SCALE_INDICES:
            scale_idx = SCALE_INDICES[fixed_scale]
        scale_key = SCALE_KEYS[scale_idx]

        dims = bdata.get("scale_dimensions", {}).get(scale_key)
        if dims:
            params = {
                "length": float(dims["length"]),
                "width": float(dims["width"]),
                "height": float(dims["height"]),
                "stories": int(dims.get("stories", 1)),
                "scale_idx": scale_idx,
            }
        else:
            values = self.scale_dimension_options(facility_name, building_name)
            choice_idx = scale_idx
            params = {
                "length": float(values["length"][choice_idx]),
                "width": float(values["width"][choice_idx]),
                "height": float(values["height"][choice_idx]),
                "stories": int(values["stories"][choice_idx]),
                "scale_idx": scale_idx,
            }

        scale_meta = (
            self.facilities[facility_name]
            .get("meta", {})
            .get("default_scale", {})
            .get(scale_key, {})
        )
        if "fuel_density" in scale_meta:
            params["fuel_density"] = scale_meta["fuel_density"]
        if "fuel_size_multiplier" in scale_meta:
            params["fuel_size_multiplier"] = scale_meta["fuel_size_multiplier"]
        return params

    def scale_dimension_options(self, facility_name: str, building_name: str) -> dict:
        """Return ``{field: (small, medium, large)}`` for UI and generation."""
        bdata = self._find_building(facility_name, building_name)
        scale_dims = bdata.get("scale_dimensions", {})
        if scale_dims:
            return {
                field: tuple(scale_dims[key][field] for key in ("small", "medium", "large"))
                for field in ("length", "width", "height", "stories")
            }

        def from_range(r, *, is_int: bool = False):
            if not r:
                values = (0, 0, 0)
            elif len(r) >= 3:
                values = (r[0], r[2], r[1])
            elif len(r) >= 2:
                values = (r[0], (r[0] + r[1]) / 2, r[1])
            else:
                values = (r[0], r[0], r[0])
            if is_int:
                return tuple(int(round(v)) for v in values)
            return tuple(float(v) for v in values)

        return {
            "length": from_range(bdata.get("length_range", [0, 0])),
            "width": from_range(bdata.get("width_range", [0, 0])),
            "height": from_range(bdata.get("height_range", [0, 0])),
            "stories": from_range(bdata.get("stories_range", [1, 1]), is_int=True),
        }

    def arrange_buildings_by_layout(
        self,
        facility_name: str,
        buildings: list[Building],
    ) -> bool:
        """Apply the facility-level row layout while preserving fixed gaps.

        Layout schema:

        ``{"gap_x": 8, "gap_y": 8, "rows": [["A", "B"], ["C"]]}``

        Names are matched against ``Building.name``.  Any generated building
        missing from the layout is appended as an extra final row.
        """
        layout = self.facilities[facility_name].get("layout", {})
        rows = layout.get("rows")
        if not rows:
            return False

        by_name = {b.name: b for b in buildings}
        placed: set[str] = set()
        gap_x = float(layout.get("gap_x", layout.get("gap", 8.0)))
        gap_y = float(layout.get("gap_y", layout.get("gap", gap_x)))
        origin = layout.get("origin", [0.0, 0.0])
        origin_x = float(origin[0]) if len(origin) > 0 else 0.0
        origin_y = float(origin[1]) if len(origin) > 1 else 0.0

        normalized_rows: list[list[str]] = []
        for row in rows:
            names = [name for name in row if name in by_name]
            if names:
                normalized_rows.append(names)

        layout_names = {name for row in normalized_rows for name in row}
        remaining = [b.name for b in buildings if b.name not in layout_names]
        if remaining:
            normalized_rows.append(remaining)

        y_cursor = origin_y
        for row in normalized_rows:
            x_cursor = origin_x
            row_width = 0.0
            for name in row:
                building = by_name[name]
                building.boundary[0] = x_cursor
                building.boundary[2] = y_cursor
                x_cursor += building.length + gap_x
                row_width = max(row_width, building.width)
                placed.add(name)
            y_cursor += row_width + gap_y

        return bool(placed)

    def resolve_scale(
        self,
        facility_name: str,
        building_name: str,
        length: float,
        width: float,
        height: float,
    ) -> tuple[str | None, dict | None]:
        """Map actual building dimensions to the nearest small/medium/large.

        Uses ``scale_dimensions`` when present, comparing each axis against
        the scale table's own span so no single dimension dominates; falls
        back to the legacy ``*_range`` triplets otherwise.
        """
        bdata = self._find_building(facility_name, building_name)
        scale_dims = bdata.get("scale_dimensions", {})
        if not scale_dims:
            options = self.scale_dimension_options(facility_name, building_name)
            if not any(options["length"]) and not any(options["width"]):
                return None, None
            scale_dims = {
                key: {
                    "length": options["length"][i],
                    "width": options["width"][i],
                    "height": options["height"][i],
                    "stories": options["stories"][i],
                }
                for i, key in enumerate(("small", "medium", "large"))
            }

        def dist(dims: dict) -> float:
            lengths = [d["length"] for d in scale_dims.values()]
            widths = [d["width"] for d in scale_dims.values()]
            heights = [d["height"] for d in scale_dims.values()]
            return (
                abs(length - dims["length"]) / (max(lengths) - min(lengths) or 1.0)
                + abs(width - dims["width"]) / (max(widths) - min(widths) or 1.0)
                + abs(height - dims["height"]) / (max(heights) - min(heights) or 1.0)
            )

        best_key, best_dims, best_dist = None, None, float("inf")
        for key, dims in scale_dims.items():
            distance = dist(dims)
            if distance < best_dist:
                best_key, best_dims, best_dist = key, dims, distance
        return best_key, best_dims

    def _find_building(self, facility_name: str, building_name: str) -> dict:
        """Find a building by name within a facility"""
        for b in self.facilities[facility_name]["buildings"]:
            if b["name"] == building_name:
                return b
        raise ValueError(f"Building '{building_name}' not found in facility '{facility_name}'")
