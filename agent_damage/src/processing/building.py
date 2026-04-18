"""Building dataclass with JSON parsing and 18-dim feature vector."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .combustible_stats import combustible_vector


def _midpoint(value: Any, default: float = 0.0) -> float:
    """Reduce a possibly-range-valued spec to a single scalar.

    - `[a, b]` -> (a+b)/2
    - `[a, b, c]` -> c (equivalent-model "expected" value)
    - scalar -> scalar
    - None -> default
    """
    if value is None:
        return float(default)
    if isinstance(value, (list, tuple)):
        if len(value) == 3:
            return float(value[2])
        if len(value) == 2:
            return (float(value[0]) + float(value[1])) / 2.0
        if len(value) == 1:
            return float(value[0])
        return float(default)
    return float(value)


def _extract_opening(section: Optional[Dict[str, Any]], key: str, default: float) -> float:
    if not section:
        return default
    return _midpoint(section.get(key), default)


@dataclass
class Building:
    """Single building unit within a facility."""

    name: str
    cn_name: str
    length: float
    width: float
    height: float
    door_count: int
    door_width: float
    door_height: float
    window_count: int
    window_width: float
    window_height: float
    stories: int
    boundary: List[float]
    combustibles_raw: Dict[str, int] = field(default_factory=dict)

    @property
    def floor_area(self) -> float:
        return self.length * self.width

    @property
    def volume(self) -> float:
        return self.length * self.width * self.height

    @property
    def center_x(self) -> float:
        return self.boundary[0] + self.length / 2.0

    @property
    def center_y(self) -> float:
        return self.boundary[2] + self.width / 2.0

    @property
    def door_area(self) -> float:
        return self.door_count * self.door_width * self.door_height

    @property
    def window_area(self) -> float:
        return self.window_count * self.window_width * self.window_height

    @property
    def wall_area(self) -> float:
        return 2.0 * (self.length * self.height + self.width * self.height)

    @property
    def opening_ratio(self) -> float:
        wa = self.wall_area
        if wa <= 0:
            return 0.0
        return (self.door_area + self.window_area) / wa

    def combustible_vector(self) -> List[float]:
        return combustible_vector(self.combustibles_raw)

    def to_feature_vector(self, facility_type_index: int) -> List[float]:
        """18-dim feature vector — does NOT include heat source or occlusion."""
        return [
            self.length,
            self.width,
            self.height,
            float(self.door_count),
            float(self.window_count),
            float(self.stories),
            self.boundary[0],
            self.boundary[2],
            self.opening_ratio,
            float(facility_type_index),
            *self.combustible_vector(),
        ]

    @classmethod
    def parse_from_json(cls, data: Dict[str, Any]) -> "Building":
        length = _midpoint(data.get("length") or data.get("length_range"), 30.0)
        width = _midpoint(data.get("width") or data.get("width_range"), 20.0)
        height = _midpoint(data.get("height") or data.get("height_range"), 10.0)

        stories_template = data.get("stories_template") or []
        stories_section = stories_template[0] if stories_template else {}

        doors = stories_section.get("doors", {})
        windows = stories_section.get("windows", {})

        door_count = int(_extract_opening(doors, "count", 0))
        door_width = _extract_opening(doors, "width", 1.0)
        door_height = _extract_opening(doors, "height", 2.1)

        window_count = int(_extract_opening(windows, "count", 0))
        window_width = _extract_opening(windows, "width", 1.0)
        window_height = _extract_opening(windows, "height", 1.2)

        stories = int(_midpoint(data.get("stories_range"), 1))

        combustibles_raw: Dict[str, int] = {}
        for fc in stories_section.get("fire_compartment_ratios", []) or []:
            for c in fc.get("combustibles", []) or []:
                key = c.get("key")
                count = int(c.get("count", 0) or 0)
                if not key or count <= 0:
                    continue
                combustibles_raw[key] = combustibles_raw.get(key, 0) + count

        boundary = data.get("boundary")
        if not boundary or not isinstance(boundary, list) or len(boundary) < 4:
            boundary = [0.0, length, 0.0, width]
        boundary = [float(boundary[0]), float(boundary[1]), float(boundary[2]), float(boundary[3])]

        return cls(
            name=data.get("name", "Building"),
            cn_name=data.get("cn_name", "建筑"),
            length=length,
            width=width,
            height=height,
            door_count=door_count,
            door_width=door_width,
            door_height=door_height,
            window_count=window_count,
            window_width=window_width,
            window_height=window_height,
            stories=stories,
            boundary=boundary,
            combustibles_raw=combustibles_raw,
        )
