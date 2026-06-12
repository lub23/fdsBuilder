"""Damage-label generation from simplified thermal load model.

Formula (from outline.md):
    base = heat_flux * duration * max(azimuth_weighted_opening_ratio, 0.01)
    if occluding_higher_count > 0:
        base *= 0.3 ** occluding_higher_count
    comb = 1.2*wood + 1.0*text + 1.5*plast + 2.0*fuel +
           1.3*elec + 1.2*chem + 0.8*metal + 1.1*comp
    thermal_load = base * (1 + comb)
low : thermal_load < 25
med : 25 <= thermal_load < 70
high : thermal_load >= 70
"""

from __future__ import annotations

import math
from typing import Sequence

from ..processing.building import Building
from ..processing.enums import DamageLevel
from ..processing.heat_source import HeatSourceParams


LABEL_THRESHOLD_MEDIUM: float = 25.0
LABEL_THRESHOLD_HIGH: float = 70.0

_COMB_WEIGHTS: Sequence[float] = (1.2, 1.0, 1.5, 2.0, 1.3, 1.2, 0.8, 1.1)

# Wall angle convention matching heat_source.py:
# azimuth 0°  = YMAX (north),  90° = XMAX (east)
#         180° = YMIN (south), 270° = XMIN (west)
_WALL_ANGLES = {
    "y_max": 0,
    "x_max": 90,
    "y_min": 180,
    "x_min": 270,
}


def _azimuth_opening_weight(wall: str, azimuth: float) -> float:
    """Weight of a wall face based on its angle to the radiation source.

    Returns cos(angle_diff) where angle_diff is the smallest angular
    separation between the wall normal and the radiation azimuth.
    0° difference (wall facing source) → weight=1.0,
    90° → 0.0, >90° → 0 (back face).
    """
    diff = abs(_WALL_ANGLES[wall] - (azimuth % 360)) % 360
    if diff > 180:
        diff = 360 - diff
    return max(0.0, math.cos(math.radians(diff)))


def _weighted_opening_ratio(building: Building, azimuth: float) -> float:
    """Compute azimuth-weighted opening ratio.

    Doors are distributed evenly on y_min/y_max walls,
    windows on x_min/x_max walls.  Each wall's opening ratio
    is weighted by its cosine angle to the radiation source.
    """
    L, W, h = building.length, building.width, building.height
    door_area = building.door_width * building.door_height
    win_area = building.window_width * building.window_height

    wall_opening_ratios: dict[str, float] = {}
    for wall, wall_angle in _WALL_ANGLES.items():
        if wall in ("y_min", "y_max"):
            wall_area = L * h
            openings = (building.door_count / 2) * door_area
        else:
            wall_area = W * h
            openings = (building.window_count / 2) * win_area
        ratio = openings / max(wall_area, 0.01)
        weight = _azimuth_opening_weight(wall, azimuth)
        wall_opening_ratios[wall] = ratio * weight

    total = sum(wall_opening_ratios.values())
    return max(total, 0.01)


def _thermal_load(
    building: Building, heat_source: HeatSourceParams, occluding_higher_count: int
) -> float:
    weighted_or = _weighted_opening_ratio(building, heat_source.azimuth)
    base = (
        heat_source.heat_flux
        * heat_source.duration
        * weighted_or
    )
    if occluding_higher_count > 0:
        base *= 0.3 ** occluding_higher_count
    comb = sum(
        w * v for w, v in zip(_COMB_WEIGHTS, building.combustible_vector())
    )
    return base * (1.0 + comb)


def simulate_damage_label(
    building: Building,
    heat_source: HeatSourceParams,
    occluding_higher_count: int,
) -> DamageLevel:
    load = _thermal_load(building, heat_source, occluding_higher_count)
    if load < LABEL_THRESHOLD_MEDIUM:
        return DamageLevel.LOW
    if load < LABEL_THRESHOLD_HIGH:
        return DamageLevel.MEDIUM
    return DamageLevel.HIGH
