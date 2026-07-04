import math

import pytest

from agent_damage.src.processing.heat_source import (
    AZIMUTH_OPTIONS,
    DURATION_OPTIONS,
    ELEVATION_OPTIONS,
    HEAT_FLUX_OPTIONS,
    HeatSourceParams,
    iter_heat_source_combinations,
)


def test_options_match_outline():
    assert ELEVATION_OPTIONS == (0, 30, 45, 60)
    assert DURATION_OPTIONS == (1.36, 2.1, 7.5)
    assert HEAT_FLUX_OPTIONS == (
        50, 100, 500, 1000, 2000, 3000,
        5000, 7000, 10000, 12000, 15000, 20000,
    )
    assert AZIMUTH_OPTIONS == tuple(range(0, 360, 5))
    assert len(AZIMUTH_OPTIONS) == 72


def test_combination_count():
    combos = list(iter_heat_source_combinations())
    assert len(combos) == 4 * 3 * 12 * 72  # 10368


def test_heat_source_to_feature_vector():
    hs = HeatSourceParams(elevation=30, azimuth=90, duration=2.1, heat_flux=10000)
    vec = hs.to_feature_vector()
    assert vec == [30.0, 90.0, 2.1, 10000.0]


@pytest.mark.parametrize("elevation", [0, 30, 45, 60])
def test_valid_elevations(elevation: int):
    hs = HeatSourceParams(elevation=elevation, azimuth=0, duration=2.1, heat_flux=5000)
    assert hs.elevation == elevation


def test_invalid_elevation_raises():
    with pytest.raises(ValueError):
        HeatSourceParams(elevation=15, azimuth=0, duration=2.1, heat_flux=5000)


def test_invalid_duration_raises():
    with pytest.raises(ValueError):
        HeatSourceParams(elevation=0, azimuth=0, duration=0.0, heat_flux=5000)


def test_heat_flux_bounds():
    with pytest.raises(ValueError):
        HeatSourceParams(elevation=0, azimuth=0, duration=2.1, heat_flux=25000)


def test_azimuth_must_be_multiple_of_5():
    with pytest.raises(ValueError):
        HeatSourceParams(elevation=0, azimuth=7, duration=2.1, heat_flux=5000)
