"""Damage-label generation from simplified thermal load model.

Formula (from outline.md):
    base = heat_flux * duration * max(opening_ratio, 0.01)
    if occluding_higher_count > 0:
        base *= 0.3 ** occluding_higher_count
    comb = 1.2*wood + 1.0*text + 1.5*plast + 2.0*fuel +
           1.3*elec + 1.2*chem + 0.8*metal + 1.1*comp
    thermal_load = base * (1 + comb)
    low  : thermal_load < 30
    med  : 30 <= thermal_load < 80
    high : thermal_load >= 80
"""

from __future__ import annotations

from typing import Sequence

from ..processing.building import Building
from ..processing.enums import DamageLevel
from ..processing.heat_source import HeatSourceParams


LABEL_THRESHOLD_MEDIUM: float = 15.0
LABEL_THRESHOLD_HIGH: float = 40.0

_COMB_WEIGHTS: Sequence[float] = (1.2, 1.0, 1.5, 2.0, 1.3, 1.2, 0.8, 1.1)


def _thermal_load(
    building: Building, heat_source: HeatSourceParams, occluding_higher_count: int
) -> float:
    base = (
        heat_source.heat_flux
        * heat_source.duration
        * max(building.opening_ratio, 0.01)
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
