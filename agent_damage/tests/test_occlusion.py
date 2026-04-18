import math

import pytest

from agent_damage.src.processing.building import Building
from agent_damage.src.processing.facility import Facility
from agent_damage.src.processing.enums import FacilityType
from agent_damage.src.processing.occlusion import (
    FIXED_SOURCE_OFFSET,
    heat_source_position,
    occluding_higher_count,
)


def _make_building(
    name: str, x: float, y: float, length: float, width: float, height: float
) -> Building:
    return Building(
        name=name,
        cn_name=name,
        length=length,
        width=width,
        height=height,
        door_count=1,
        door_width=1.0,
        door_height=2.0,
        window_count=2,
        window_width=1.0,
        window_height=1.5,
        stories=1,
        boundary=[x, length, y, width],
        combustibles_raw={"WOOD_TABLE": 1},
    )


def test_fixed_offset_matches_fds_generator():
    assert FIXED_SOURCE_OFFSET == pytest.approx(18.0)


def test_heat_source_position_east():
    facility = Facility(
        name="f", cn_name="f", facility_type=FacilityType.AEROSPACE,
        buildings=[_make_building("b", 0, 0, 10, 10, 5)],
    )
    # azimuth=90 = east (+x)
    pos = heat_source_position(facility, azimuth=90)
    cx, cy = facility.center
    assert pos[0] == pytest.approx(cx + 5.0 + FIXED_SOURCE_OFFSET, abs=1e-6)
    assert pos[1] == pytest.approx(cy, abs=1e-6)


def test_heat_source_position_north():
    facility = Facility(
        name="f", cn_name="f", facility_type=FacilityType.AEROSPACE,
        buildings=[_make_building("b", 0, 0, 10, 20, 5)],
    )
    # azimuth=0 = north (+y)
    pos = heat_source_position(facility, azimuth=0)
    cx, cy = facility.center
    assert pos[0] == pytest.approx(cx, abs=1e-6)
    assert pos[1] == pytest.approx(cy + 10.0 + FIXED_SOURCE_OFFSET, abs=1e-6)


def test_occluding_count_zero_when_only_target():
    target = _make_building("t", 0, 0, 10, 10, 5)
    facility = Facility(
        name="f", cn_name="f", facility_type=FacilityType.AEROSPACE,
        buildings=[target],
    )
    assert occluding_higher_count(facility, target, azimuth=90) == 0


def test_occluding_count_taller_on_line():
    target = _make_building("target", 0, 0, 10, 10, 5)
    blocker = _make_building("blocker", 20, 0, 10, 10, 10)  # taller
    facility = Facility(
        name="f", cn_name="f", facility_type=FacilityType.AEROSPACE,
        buildings=[target, blocker],
    )
    assert occluding_higher_count(facility, target, azimuth=90) == 1


def test_occluding_count_shorter_not_counted():
    target = _make_building("target", 0, 0, 10, 10, 10)
    shorter = _make_building("shorter", 20, 0, 10, 10, 5)
    facility = Facility(
        name="f", cn_name="f", facility_type=FacilityType.AEROSPACE,
        buildings=[target, shorter],
    )
    assert occluding_higher_count(facility, target, azimuth=90) == 0


def test_occluding_count_off_line_not_counted():
    target = _make_building("target", 0, 0, 10, 10, 5)
    offline = _make_building("offline", 20, 40, 10, 10, 10)
    facility = Facility(
        name="f", cn_name="f", facility_type=FacilityType.AEROSPACE,
        buildings=[target, offline],
    )
    assert occluding_higher_count(facility, target, azimuth=90) == 0
