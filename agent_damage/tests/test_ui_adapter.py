import pytest

from agent_damage.src.inference.ui_adapter import (
    convert_building,
    detect_facility_type,
    group_to_facility,
    nearest_enum,
)
from agent_damage.src.processing.enums import FacilityType
from agent_damage.src.processing.heat_source import (
    AZIMUTH_OPTIONS,
    DURATION_OPTIONS,
    HEAT_FLUX_OPTIONS,
)


class _FakeOpening:
    def __init__(self, type_, boundary):
        self.type = type_
        self.boundary = boundary


class _FakeStory:
    def __init__(self, height, openings=None, fire_compartments=None):
        self.height = height
        self.openings = openings or []
        self.fire_compartments = fire_compartments or []


class _FakeFC:
    def __init__(self, combustibles):
        self.combustibles = combustibles


class _FakeBuilding:
    def __init__(self, name="B", cn_name="建筑", boundary=(0, 20, 0, 15), stories=()):
        self.name = name
        self.cn_name = cn_name
        self.boundary = list(boundary)
        self.stories = list(stories)


class _FakeGroup:
    def __init__(self, buildings, chid="test"):
        self.buildings = buildings
        self.chid = chid


def test_nearest_enum_heat_flux():
    # UI value treated as kW/m² after divided by 1000 elsewhere
    assert nearest_enum(2.9, HEAT_FLUX_OPTIONS) == 3
    assert nearest_enum(0.0, HEAT_FLUX_OPTIONS) == 0.05
    assert nearest_enum(1000.0, HEAT_FLUX_OPTIONS) == 20


def test_nearest_enum_azimuth():
    assert nearest_enum(7, AZIMUTH_OPTIONS) == 5
    assert nearest_enum(92, AZIMUTH_OPTIONS) == 90


def test_nearest_enum_duration():
    assert nearest_enum(1.5, DURATION_OPTIONS) == 1.36
    assert nearest_enum(2.0, DURATION_OPTIONS) == 2.1
    assert nearest_enum(100, DURATION_OPTIONS) == 7.5


def test_convert_building_aggregates_openings():
    stories = [
        _FakeStory(
            height=4.0,
            openings=[
                _FakeOpening("door", [1, 2.0, 0, 2.1]),
                _FakeOpening("window", [0, 1.5, 1, 1.2]),
                _FakeOpening("window", [0, 1.5, 1, 1.2]),
            ],
        ),
        _FakeStory(height=3.5, openings=[_FakeOpening("door", [0, 2.0, 0, 2.1])]),
    ]
    main = _FakeBuilding(stories=stories, boundary=(10, 30, 5, 20))
    ad = convert_building(main)
    assert ad.door_count == 2
    assert ad.window_count == 2
    assert ad.stories == 2
    assert ad.length == 30
    assert ad.width == 20
    assert ad.height == pytest.approx(7.5)
    assert ad.boundary == [10.0, 30.0, 5.0, 20.0]


def test_convert_building_aggregates_combustibles():
    stories = [
        _FakeStory(
            height=3.0,
            fire_compartments=[
                _FakeFC([
                    {"key": "WOOD_TABLE", "count": 4},
                    {"key": "CABLE_BUNDLE", "count": 2},
                ]),
                _FakeFC([{"key": "WOOD_TABLE", "count": 3}]),
            ],
        )
    ]
    main = _FakeBuilding(stories=stories)
    ad = convert_building(main)
    assert ad.combustibles_raw == {"WOOD_TABLE": 7, "CABLE_BUNDLE": 2}


def test_convert_building_defaults_when_empty():
    main = _FakeBuilding(stories=[])
    ad = convert_building(main)
    assert ad.door_count == 0
    assert ad.window_count == 0
    assert ad.stories == 1  # minimum 1
    assert ad.combustibles_raw == {}


def test_detect_facility_type_aerospace():
    group = _FakeGroup(
        [_FakeBuilding(name="Launch control center", cn_name="发射控制中心")]
    )
    assert detect_facility_type(group) is FacilityType.AEROSPACE


def test_detect_facility_type_hangar():
    group = _FakeGroup([_FakeBuilding(name="Large Hangar", cn_name="大型机库")])
    assert detect_facility_type(group) is FacilityType.AIRPORT_HANGAR


def test_detect_facility_type_metallurgical():
    group = _FakeGroup(
        [_FakeBuilding(name="Electrolysis Workshop", cn_name="电解车间")]
    )
    assert detect_facility_type(group) is FacilityType.METALLURGICAL


def test_detect_facility_type_default_is_machinery():
    group = _FakeGroup([_FakeBuilding(name="Unknown", cn_name="未知建筑")])
    assert detect_facility_type(group) is FacilityType.MACHINERY_MANUFACTURING


def test_group_to_facility_end_to_end():
    stories = [_FakeStory(height=5.0, fire_compartments=[_FakeFC([{"key": "JET_FUEL", "count": 1}])])]
    buildings = [
        _FakeBuilding(name="Large Hangar", cn_name="大型机库", stories=stories),
        _FakeBuilding(name="Medium Hangar", cn_name="中型机库", stories=stories),
    ]
    group = _FakeGroup(buildings, chid="airport_hangar")
    fac = group_to_facility(group)
    assert fac.name == "airport_hangar"
    assert fac.facility_type is FacilityType.AIRPORT_HANGAR
    assert len(fac.buildings) == 2
