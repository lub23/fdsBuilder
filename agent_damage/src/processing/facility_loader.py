"""Load the four canonical facility JSONs used for damage modeling."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

from .facility import Facility


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FACILITIES_DIR = PROJECT_ROOT / "facilities"

CORE_FACILITY_FILES: Tuple[str, ...] = (
    "aerospace.json",
    "airport_hangar.json",
    "machinery_manufacturing.json",
    "metallurgical_facilities.json",
)


@lru_cache(maxsize=1)
def load_core_facilities() -> Tuple[Facility, ...]:
    """Load and cache the 4 canonical facilities (aerospace / airport_hangar /
    machinery_manufacturing / metallurgical_facilities)."""
    facilities: List[Facility] = []
    for name in CORE_FACILITY_FILES:
        path = FACILITIES_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"Missing facility JSON: {path}")
        facilities.append(Facility.load_from_json(path))
    return tuple(facilities)
