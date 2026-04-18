"""Adapters between the main app (models.building.Building / BuildingGroup) and
the agent_damage inference types (Facility / Building).

The main app stores buildings with stories and fire compartments; this module
aggregates the relevant fields into the flat schema expected by agent_damage.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence, Tuple

from ..processing.building import Building as AdBuilding
from ..processing.enums import FacilityType
from ..processing.facility import Facility as AdFacility


def nearest_enum(value: float, options: Sequence[float]) -> float:
    """Return the option closest to `value` (Euclidean in 1D)."""
    return min(options, key=lambda x: abs(x - value))


def _aggregate_openings(stories: Iterable[Any]) -> Tuple[int, float, float, int, float, float]:
    """Aggregate door and window counts/sizes across all stories.

    Main app exposes openings at two levels: Story.openings (exterior) and each
    FireCompartment.openings (interior). For damage prediction we care about the
    exterior envelope, so only Story.openings contribute to the facade opening
    ratio.

    Returns:
        (door_count, door_width, door_height, window_count, window_width, window_height)
    """
    door_widths: list[float] = []
    door_heights: list[float] = []
    window_widths: list[float] = []
    window_heights: list[float] = []

    for story in stories:
        for op in getattr(story, "openings", []) or []:
            # Opening.boundary = [w_offset, width, h_offset, height]
            boundary = getattr(op, "boundary", None) or []
            if len(boundary) < 4:
                continue
            w = float(boundary[1])
            h = float(boundary[3])
            otype = getattr(op, "type", "") or ""
            if otype in ("door", "loading_dock"):
                door_widths.append(w)
                door_heights.append(h)
            elif otype in ("window", "ribbon_window"):
                window_widths.append(w)
                window_heights.append(h)

    def _avg(xs: list[float], default: float) -> float:
        return sum(xs) / len(xs) if xs else default

    return (
        len(door_widths),
        _avg(door_widths, 1.0),
        _avg(door_heights, 2.1),
        len(window_widths),
        _avg(window_widths, 1.0),
        _avg(window_heights, 1.2),
    )


def _aggregate_combustibles(stories: Iterable[Any]) -> dict[str, int]:
    """Sum combustible counts across all stories' fire compartments."""
    totals: dict[str, int] = {}
    for story in stories:
        for fc in getattr(story, "fire_compartments", []) or []:
            for c in getattr(fc, "combustibles", []) or []:
                if isinstance(c, dict):
                    key = c.get("key") or c.get("preset_key")
                    count = int(c.get("count", 1) or 1)
                else:
                    key = getattr(c, "key", None) or getattr(c, "preset_key", None)
                    count = int(getattr(c, "count", 1) or 1)
                if not key or count <= 0:
                    continue
                totals[key] = totals.get(key, 0) + count
    return totals


def convert_building(main_building: Any) -> AdBuilding:
    """Convert a main-app `Building` to the agent_damage `Building`."""
    stories = list(getattr(main_building, "stories", []) or [])
    (
        door_count,
        door_width,
        door_height,
        window_count,
        window_width,
        window_height,
    ) = _aggregate_openings(stories)

    combustibles_raw = _aggregate_combustibles(stories)

    boundary = list(getattr(main_building, "boundary", [0, 20, 0, 10]))
    if len(boundary) < 4:
        boundary = boundary + [0] * (4 - len(boundary))
    boundary = [float(boundary[0]), float(boundary[1]), float(boundary[2]), float(boundary[3])]

    # Height: prefer sum of story heights (authoritative per building.py:212)
    height = sum(float(getattr(s, "height", 0.0)) for s in stories) or float(
        getattr(main_building, "height", 3.0)
    )

    return AdBuilding(
        name=getattr(main_building, "name", "Building") or "Building",
        cn_name=getattr(main_building, "cn_name", "") or getattr(main_building, "name", "建筑"),
        length=float(boundary[1]),
        width=float(boundary[3]),
        height=height,
        door_count=door_count,
        door_width=door_width,
        door_height=door_height,
        window_count=window_count,
        window_width=window_width,
        window_height=window_height,
        stories=max(len(stories), 1),
        boundary=boundary,
        combustibles_raw=combustibles_raw,
    )


_FACILITY_KEYWORDS: tuple[tuple[FacilityType, tuple[str, ...]], ...] = (
    (FacilityType.AIRPORT_HANGAR, ("hangar", "机库", "机场")),
    (
        FacilityType.AEROSPACE,
        (
            "aerospace",
            "launch",
            "发射",
            "航天",
            "总装",
            "assembly_building",
            "sub_assembly_building",
        ),
    ),
    (
        FacilityType.METALLURGICAL,
        (
            "metallurg",
            "电解",
            "electrolysis",
            "steel",
            "钢铁",
            "refinery",
            "精炼",
            "冶金",
            "power_plant",
            "专用电厂",
            "smelt",
        ),
    ),
    (
        FacilityType.MACHINERY_MANUFACTURING,
        ("machining", "机械加工", "manufacturing", "机加"),
    ),
)


def detect_facility_type(building_group: Any) -> FacilityType:
    """Heuristic: infer facility type from building names (en + zh)."""
    buildings = getattr(building_group, "buildings", []) or []
    if not buildings:
        return FacilityType.MACHINERY_MANUFACTURING
    names_blob = " ".join(
        (getattr(b, "name", "") + " " + getattr(b, "cn_name", "")).lower()
        for b in buildings
    )
    for ftype, keywords in _FACILITY_KEYWORDS:
        for kw in keywords:
            if kw.lower() in names_blob:
                return ftype
    return FacilityType.MACHINERY_MANUFACTURING


def group_to_facility(building_group: Any, facility_type: FacilityType | None = None) -> AdFacility:
    """Convert a main-app `BuildingGroup` to an agent_damage `Facility`."""
    if facility_type is None:
        facility_type = detect_facility_type(building_group)
    ad_buildings = [
        convert_building(b) for b in (getattr(building_group, "buildings", []) or [])
    ]
    name = (
        getattr(building_group, "chid", None)
        or (ad_buildings[0].name if ad_buildings else "facility")
    )
    return AdFacility(
        name=name,
        cn_name=name,
        facility_type=facility_type,
        buildings=ad_buildings,
    )
