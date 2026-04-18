import math

import pytest

from agent_damage.src.processing.building import Building


SAMPLE_BUILDING_JSON = {
    "name": "Test Building",
    "cn_name": "测试建筑",
    "boundary": [10.0, 30.0, 5.0, 20.0],
    "length_range": [20, 40],
    "width_range": [15, 25],
    "height_range": [8, 12],
    "stories_range": [1, 3, 2],
    "stories_template": [
        {
            "name": "1F",
            "doors": {"width": [2, 2], "height": [3, 3], "count": [2, 4]},
            "windows": {"width": [1, 1], "height": [1.5, 1.5], "count": [4, 8]},
            "fire_compartment_ratios": [
                {"combustibles": [
                    {"key": "WOOD_TABLE", "count": 6},
                    {"key": "CABLE_BUNDLE", "count": 2},
                ]},
            ],
        }
    ],
}


def test_parse_from_json_computes_midpoints():
    b = Building.parse_from_json(SAMPLE_BUILDING_JSON)
    assert b.name == "Test Building"
    assert b.cn_name == "测试建筑"
    assert b.length == 30.0  # (20+40)/2
    assert b.width == 20.0   # (15+25)/2
    assert b.height == 10.0  # (8+12)/2
    assert b.door_count == 3
    assert b.window_count == 6
    assert b.stories == 2
    assert b.boundary == [10.0, 30.0, 5.0, 20.0]


def test_parse_from_json_aggregates_combustibles():
    b = Building.parse_from_json(SAMPLE_BUILDING_JSON)
    assert b.combustibles_raw == {"WOOD_TABLE": 6, "CABLE_BUNDLE": 2}


def test_opening_ratio():
    b = Building.parse_from_json(SAMPLE_BUILDING_JSON)
    expected = (3 * 2 * 3 + 6 * 1 * 1.5) / (2 * (30 * 10 + 20 * 10))
    assert math.isclose(b.opening_ratio, expected, abs_tol=1e-6)


def test_to_feature_vector_has_18_dims():
    b = Building.parse_from_json(SAMPLE_BUILDING_JSON)
    vec = b.to_feature_vector(facility_type_index=0)
    assert len(vec) == 18
    assert vec[0] == b.length
    assert vec[1] == b.width
    assert vec[2] == b.height
    assert vec[3] == b.door_count
    assert vec[4] == b.window_count
    assert vec[5] == b.stories
    assert vec[6] == b.boundary[0]
    assert vec[7] == b.boundary[2]
    assert math.isclose(vec[8], b.opening_ratio)
    assert vec[9] == 0  # facility_type_index
    assert math.isclose(sum(vec[10:18]), 1.0, abs_tol=1e-6)


def test_center_xy():
    b = Building.parse_from_json(SAMPLE_BUILDING_JSON)
    assert b.center_x == 10.0 + 30.0 / 2
    assert b.center_y == 5.0 + 20.0 / 2


def test_parse_json_missing_boundary_defaults_to_origin():
    data = dict(SAMPLE_BUILDING_JSON)
    data["boundary"] = None
    b = Building.parse_from_json(data)
    assert b.boundary == [0.0, b.length, 0.0, b.width]
