"""agent_damage source package."""

__version__ = "0.2.0"

from .data.generator import FEATURE_COLUMNS, generate_balanced_dataset, generate_splits
from .inference.predictor import EnsemblePredictor
from .inference.results import BuildingDamageResult, FacilityDamageResult
from .processing.building import Building
from .processing.enums import DamageLevel, FacilityType
from .processing.facility import Facility
from .processing.facility_loader import load_core_facilities
from .processing.heat_source import HeatSourceParams

__all__ = [
    "Building",
    "BuildingDamageResult",
    "DamageLevel",
    "EnsemblePredictor",
    "FEATURE_COLUMNS",
    "Facility",
    "FacilityDamageResult",
    "FacilityType",
    "HeatSourceParams",
    "generate_balanced_dataset",
    "generate_splits",
    "load_core_facilities",
]
