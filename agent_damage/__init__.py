"""Agent damage prediction module (rebuilt)."""

from .src import (
    Building,
    BuildingDamageResult,
    DamageLevel,
    EnsemblePredictor,
    Facility,
    FacilityDamageResult,
    FacilityType,
    HeatSourceParams,
    load_core_facilities,
)

__all__ = [
    "Building",
    "BuildingDamageResult",
    "DamageLevel",
    "EnsemblePredictor",
    "Facility",
    "FacilityDamageResult",
    "FacilityType",
    "HeatSourceParams",
    "load_core_facilities",
]
