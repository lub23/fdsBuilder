"""Result dataclasses for two-stage inference."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..processing.building import Building
from ..processing.enums import DamageLevel
from ..processing.facility import Facility
from ..processing.heat_source import HeatSourceParams


@dataclass
class BuildingDamageResult:
    building: Building
    damage_level: DamageLevel
    probability: float
    uncertainty: float


@dataclass
class FacilityDamageResult:
    facility: Facility
    heat_source: HeatSourceParams
    building_results: List[BuildingDamageResult] = field(default_factory=list)

    def get_overall_level(self, algorithm: str = "max") -> DamageLevel:
        if not self.building_results:
            return DamageLevel.LOW
        if algorithm == "max":
            return max(
                self.building_results, key=lambda r: r.damage_level.numeric
            ).damage_level
        if algorithm == "weighted":
            weights = [r.building.floor_area for r in self.building_results]
            total = sum(weights) or 1.0
            score = (
                sum(r.damage_level.numeric * w for r, w in zip(self.building_results, weights))
                / total
            )
            return DamageLevel.from_numeric(int(round(score)))
        if algorithm == "threshold":
            high = sum(1 for r in self.building_results if r.damage_level is DamageLevel.HIGH)
            medium = sum(
                1 for r in self.building_results if r.damage_level is DamageLevel.MEDIUM
            )
            if high >= 1:
                return DamageLevel.HIGH
            if medium >= 2:
                return DamageLevel.MEDIUM
            return DamageLevel.LOW
        raise ValueError(f"Unknown aggregation algorithm: {algorithm}")

    @property
    def overall_uncertainty(self) -> float:
        if not self.building_results:
            return 0.0
        return float(
            sum(r.uncertainty for r in self.building_results) / len(self.building_results)
        )
