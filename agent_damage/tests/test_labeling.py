from agent_damage.src.data.labeling import (
    LABEL_THRESHOLD_HIGH,
    LABEL_THRESHOLD_MEDIUM,
    simulate_damage_label,
)
from agent_damage.src.processing.building import Building
from agent_damage.src.processing.enums import DamageLevel
from agent_damage.src.processing.heat_source import HeatSourceParams


def _building(height: float = 10.0, opening_ratio_override=None):
    length = 20.0
    width = 20.0
    wall_area = 2.0 * (length * height + width * height)
    if opening_ratio_override is not None:
        door_area = opening_ratio_override * wall_area
        door_count = 1
        door_width = door_area
        door_height = 1.0
    else:
        door_count = 2
        door_width = 2.0
        door_height = 3.0
    return Building(
        name="b",
        cn_name="b",
        length=length,
        width=width,
        height=height,
        door_count=door_count,
        door_width=door_width,
        door_height=door_height,
        window_count=0,
        window_width=0.0,
        window_height=0.0,
        stories=1,
        boundary=[0.0, length, 0.0, width],
        combustibles_raw={"WOOD_TABLE": 1},
    )


def test_low_label_for_low_flux():
    b = _building()
    hs = HeatSourceParams(elevation=0, azimuth=0, duration=1.36, heat_flux=0.05)
    label = simulate_damage_label(b, hs, occluding_higher_count=0)
    assert label is DamageLevel.LOW


def test_high_label_for_max_flux_fuel_heavy():
    # Small shed with lots of openings (opening_ratio=0.5) so the thermal
    # load reaches HIGH territory under max flux + fuel-heavy combustibles.
    b = Building(
        name="b", cn_name="b", length=10, width=10, height=3,
        door_count=4, door_width=2, door_height=2.5,
        window_count=10, window_width=2, window_height=2,
        stories=1, boundary=[0, 10, 0, 10],
        combustibles_raw={"JET_FUEL": 100, "DIESEL_TANK": 50, "GASOLINE": 20},
    )
    hs = HeatSourceParams(elevation=0, azimuth=0, duration=7.5, heat_flux=20.0)
    label = simulate_damage_label(b, hs, occluding_higher_count=0)
    assert label is DamageLevel.HIGH


def test_occlusion_reduces_damage():
    b = _building()
    hs = HeatSourceParams(elevation=0, azimuth=0, duration=7.5, heat_flux=20.0)
    no_block = simulate_damage_label(b, hs, occluding_higher_count=0)
    with_block = simulate_damage_label(b, hs, occluding_higher_count=3)
    assert with_block.numeric <= no_block.numeric


def test_thresholds_monotonic():
    assert LABEL_THRESHOLD_MEDIUM < LABEL_THRESHOLD_HIGH
