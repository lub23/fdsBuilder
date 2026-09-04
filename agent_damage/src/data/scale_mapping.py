#!/usr/bin/env python3
"""Scale mapping: authoritative small/medium/large building dimensions.

``scale_dimensions`` inside ``facilities/*.json`` declares the concrete
length/width/height for each scale.  This module loads that table once and
exposes both the lookup (scale -> dimensions, for generating a scene) and the
resolution (given a building's actual dimensions, which scale it maps to),
which is what links a new FDS scenario to the per-scale surrogate model.

The rendered table lives in ``docs/scale_mapping.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

SCALE_KEYS: tuple[str, str, str] = ("small", "medium", "large")
DEFAULT_FACILITIES_DIR = Path(__file__).resolve().parents[3] / "facilities"


class ScaleMapping:
    """Dimension table indexed by facility file stem and building name."""

    def __init__(self, facilities_dir: Path = DEFAULT_FACILITIES_DIR):
        self.facilities_dir = Path(facilities_dir)
        # facility -> building -> scale -> {"length","width","height","stories"}
        self.table: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}
        self._load()

    def _load(self) -> None:
        for json_path in sorted(self.facilities_dir.glob("*.json")):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            stem = json_path.stem
            facility: Dict[str, Dict[str, Dict[str, float]]] = {}
            for building in data.get("buildings", []):
                dims = building.get("scale_dimensions")
                if not isinstance(dims, dict):
                    continue
                normalized = {
                    scale: {
                        "length": float(dims[scale]["length"]),
                        "width": float(dims[scale]["width"]),
                        "height": float(dims[scale]["height"]),
                        "stories": float(dims[scale].get("stories", 1)),
                    }
                    for scale in SCALE_KEYS
                    if scale in dims
                }
                if normalized:
                    facility[str(building.get("name", ""))] = normalized
            if facility:
                self.table[stem] = facility

    def available(self, facility_name: str) -> bool:
        return facility_name in self.table

    def building_names(self, facility_name: str) -> list[str]:
        return list(self.table.get(facility_name, {}))

    def dimensions(
        self, facility_name: str, building_name: str, scale: str
    ) -> Optional[Dict[str, float]]:
        return self.table.get(facility_name, {}).get(building_name, {}).get(scale)

    def resolve_scale(
        self,
        facility_name: str,
        building_name: str,
        length: float,
        width: float,
        height: float,
    ) -> Tuple[str, Dict[str, float]]:
        """Return the scale key whose dimensions best match the given ones.

        Matching normalises each dimension by the scale table's own range so
        no single axis dominates, then picks the closest candidate.  Facilities
        with a single fixed scale always resolve to it.
        """
        candidates = self.table.get(facility_name, {}).get(building_name)
        if not candidates:
            raise KeyError(f"no scale_dimensions for {facility_name}/{building_name}")
        if len(candidates) == 1:
            scale = next(iter(candidates))
            return scale, candidates[scale]
        best_scale, best_dist, best_dims = None, float("inf"), None
        for scale, dims in candidates.items():
            lengths = [dims["length"] for d in candidates.values()]
            widths = [dims["width"] for d in candidates.values()]
            heights = [dims["height"] for d in candidates.values()]
            length_span = max(lengths) - min(lengths) or 1.0
            width_span = max(widths) - min(widths) or 1.0
            height_span = max(heights) - min(heights) or 1.0
            score = (
                abs(length - dims["length"]) / length_span
                + abs(width - dims["width"]) / width_span
                + abs(height - dims["height"]) / height_span
            )
            if score < best_dist:
                best_dist, best_scale, best_dims = score, scale, dims
        assert best_scale is not None and best_dims is not None
        return best_scale, best_dims