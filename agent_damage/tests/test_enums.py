from agent_damage.src.processing.enums import DamageLevel, FacilityType


def test_damage_level_numeric_roundtrip():
    for level in DamageLevel:
        assert DamageLevel.from_numeric(level.numeric) is level


def test_damage_level_values():
    assert DamageLevel.LOW.numeric == 0
    assert DamageLevel.MEDIUM.numeric == 1
    assert DamageLevel.HIGH.numeric == 2


def test_facility_type_known_values():
    assert FacilityType.AEROSPACE.value == "aerospace"
    assert FacilityType.AIRPORT_HANGAR.value == "airport_hangar"
    assert FacilityType.MACHINERY_MANUFACTURING.value == "machinery_manufacturing"
    assert FacilityType.METALLURGICAL.value == "metallurgical"


def test_facility_type_from_filename():
    assert FacilityType.from_filename("aerospace.json") is FacilityType.AEROSPACE
    assert (
        FacilityType.from_filename("metallurgical_facilities.json")
        is FacilityType.METALLURGICAL
    )
    assert (
        FacilityType.from_filename("machinery_manufacturing.json")
        is FacilityType.MACHINERY_MANUFACTURING
    )
    assert FacilityType.from_filename("airport_hangar.json") is FacilityType.AIRPORT_HANGAR


def test_facility_type_index_is_stable():
    assert FacilityType.AEROSPACE.index == 0
    assert FacilityType.AIRPORT_HANGAR.index == 1
    assert FacilityType.MACHINERY_MANUFACTURING.index == 2
    assert FacilityType.METALLURGICAL.index == 3
