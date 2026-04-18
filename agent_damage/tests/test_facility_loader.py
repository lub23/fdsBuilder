from pathlib import Path

from agent_damage.src.processing.enums import FacilityType
from agent_damage.src.processing.facility_loader import (
    CORE_FACILITY_FILES,
    load_core_facilities,
)


def test_core_facility_files_set():
    assert set(CORE_FACILITY_FILES) == {
        "aerospace.json",
        "airport_hangar.json",
        "machinery_manufacturing.json",
        "metallurgical_facilities.json",
    }


def test_load_core_facilities_returns_4():
    facilities = load_core_facilities()
    assert len(facilities) == 4
    types = {f.facility_type for f in facilities}
    assert types == set(FacilityType)
