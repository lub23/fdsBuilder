from pathlib import Path

import pytest

from agent_damage.src.processing.enums import FacilityType
from agent_damage.src.processing.facility import Facility


@pytest.mark.parametrize(
    "filename,expected_type",
    [
        ("aerospace.json", FacilityType.AEROSPACE),
        ("airport_hangar.json", FacilityType.AIRPORT_HANGAR),
        ("machinery_manufacturing.json", FacilityType.MACHINERY_MANUFACTURING),
        ("metallurgical_facilities.json", FacilityType.METALLURGICAL),
    ],
)
def test_load_core_facility(facilities_dir: Path, filename: str, expected_type):
    facility = Facility.load_from_json(facilities_dir / filename)
    assert facility.facility_type is expected_type
    assert facility.num_buildings > 0


def test_facility_bbox_and_nearest_boundary_distance(aerospace_json: Path):
    facility = Facility.load_from_json(aerospace_json)
    xmin, xmax, ymin, ymax = facility.bbox
    assert xmax > xmin
    assert ymax > ymin
    for b in facility.buildings:
        assert xmin <= b.boundary[0]
        assert xmax >= b.boundary[0] + b.length
        assert ymin <= b.boundary[2]
        assert ymax >= b.boundary[2] + b.width


def test_facility_center(aerospace_json: Path):
    facility = Facility.load_from_json(aerospace_json)
    cx, cy = facility.center
    xmin, xmax, ymin, ymax = facility.bbox
    assert cx == (xmin + xmax) / 2
    assert cy == (ymin + ymax) / 2


def test_facility_all_sub_building_types_populated(aerospace_json: Path):
    facility = Facility.load_from_json(aerospace_json)
    names = {b.name.lower() for b in facility.buildings}
    expected_substrings = [
        "launch control",
        "assembly",
        "processing",
        "launch site",
    ]
    for sub in expected_substrings:
        assert any(sub in n for n in names), f"Missing '{sub}' in {names}"
