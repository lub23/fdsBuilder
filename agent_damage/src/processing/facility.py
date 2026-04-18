"""Facility (building group) dataclass with JSON loading."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .building import Building
from .enums import FacilityType


@dataclass
class Facility:
    name: str
    cn_name: str
    facility_type: FacilityType
    buildings: List[Building] = field(default_factory=list)

    @property
    def num_buildings(self) -> int:
        return len(self.buildings)

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        """Axis-aligned bounding box over all buildings: (xmin, xmax, ymin, ymax)."""
        if not self.buildings:
            return (0.0, 0.0, 0.0, 0.0)
        xs_min = [b.boundary[0] for b in self.buildings]
        xs_max = [b.boundary[0] + b.length for b in self.buildings]
        ys_min = [b.boundary[2] for b in self.buildings]
        ys_max = [b.boundary[2] + b.width for b in self.buildings]
        return (min(xs_min), max(xs_max), min(ys_min), max(ys_max))

    @property
    def center(self) -> Tuple[float, float]:
        xmin, xmax, ymin, ymax = self.bbox
        return ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0)

    @classmethod
    def load_from_json(cls, path: Path) -> "Facility":
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data: Dict[str, Any] = json.load(f)

        facility_type = FacilityType.from_filename(path.name)
        buildings = [Building.parse_from_json(b) for b in data.get("buildings", [])]

        return cls(
            name=data.get("name", path.stem),
            cn_name=data.get("cn_name", path.stem),
            facility_type=facility_type,
            buildings=buildings,
        )
