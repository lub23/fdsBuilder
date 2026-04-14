#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for tools.migrate_schema -- schema migration functions."""

import copy
import json
import pytest

from tools.migrate_schema import (
    resolve_value,
    resolve_range_array,
    position_to_w_offset,
    wall_index_to_wall_str,
    migrate_specialized,
    migrate_equivalent,
    migrate_building_config,
)


# ============================================================
# resolve_value
# ============================================================
class TestResolveValue:
    def test_plain_int(self):
        assert resolve_value(42) == 42

    def test_plain_float(self):
        assert resolve_value(3.14) == 3.14

    def test_value_unit_dict(self):
        assert resolve_value({"value": 176, "unit": "m"}) == 176

    def test_min_eq_max(self):
        assert resolve_value({"min": 19, "max": 19, "median": 19, "mean": 19, "unit": "m"}) == 19

    def test_min_ne_max_returns_min(self):
        assert resolve_value({"min": 50, "max": 120, "median": -1, "mean": -1, "unit": "m"}) == 50

    def test_empty_dict(self):
        assert resolve_value({}) == 0

    def test_zero(self):
        assert resolve_value(0) == 0


# ============================================================
# resolve_range_array
# ============================================================
class TestResolveRangeArray:
    def test_range_without_median(self):
        r = resolve_range_array({"min": 50, "max": 120, "median": -1, "mean": -1, "unit": "m"})
        assert r == [50, 120]

    def test_range_with_median(self):
        r = resolve_range_array({"min": 8, "max": 12, "median": 10, "mean": 10, "unit": "m"})
        assert r == [8, 12, 10]

    def test_equal_range(self):
        r = resolve_range_array({"min": 19, "max": 19, "median": 19, "mean": 19, "unit": "m"})
        assert r == [19, 19, 19]

    def test_plain_number(self):
        r = resolve_range_array(5)
        assert r == [5, 5]

    def test_median_zero_excluded(self):
        r = resolve_range_array({"min": 0, "max": 0, "median": 0, "mean": 0, "unit": ""})
        assert r == [0, 0]

    def test_median_negative_excluded(self):
        r = resolve_range_array({"min": 10, "max": 20, "median": -1, "mean": -1, "unit": "m"})
        assert r == [10, 20]


# ============================================================
# position_to_w_offset
# ============================================================
class TestPositionToWOffset:
    def test_center(self):
        # position=0.5 on wall_length=100, width=10 -> 0.5*100 - 10/2 = 45
        assert position_to_w_offset(0.5, 10, 100) == 45.0

    def test_left_edge(self):
        # position=0.05 on wall_length=100, width=10 -> 0.05*100 - 5 = 0
        assert position_to_w_offset(0.05, 10, 100) == 0.0

    def test_alcoa_example(self):
        # From alcoa.json: position=0.85, width=30, wall_length=334 (x_max wall, FC covers full y)
        # w_offset = 0.85 * 334 - 30 / 2 = 283.9 - 15 = 268.9
        w_off = position_to_w_offset(0.85, 30, 334)
        assert pytest.approx(w_off, abs=0.1) == 268.9

    def test_zero_position(self):
        # position=0, width=2, wall_length=10 -> -1
        assert position_to_w_offset(0, 2, 10) == -1.0


# ============================================================
# wall_index_to_wall_str
# ============================================================
class TestWallIndexToWallStr:
    def test_all_indices(self):
        assert wall_index_to_wall_str(0) == "y_min"
        assert wall_index_to_wall_str(1) == "y_max"
        assert wall_index_to_wall_str(2) == "x_min"
        assert wall_index_to_wall_str(3) == "x_max"

    def test_unknown_index(self):
        result = wall_index_to_wall_str(5)
        assert "5" in result  # should return some fallback with the index


# ============================================================
# migrate_specialized
# ============================================================
class TestMigrateSpecialized:
    """Tests for specialized facility migration using a minimal fixture."""

    @pytest.fixture
    def minimal_old(self):
        """Minimal old-format specialized facility."""
        return {
            "cn_name": "Test Facility",
            "fire_separation": 15.0,
            "sub_types": {
                "Bay_A1": {
                    "cn_name": "A1 Bay",
                    "description": "test bay",
                    "offset": {"x": 10, "y": 200},
                    "rotation": 0,
                    "building": {
                        "length": {"min": 20, "max": 20, "median": 20, "mean": 20, "unit": "m"},
                        "width": {"min": 100, "max": 100, "median": 100, "mean": 100, "unit": "m"},
                        "height": {"min": 15, "max": 15, "median": 15, "mean": 15, "unit": "m"},
                        "stories": {"min": 1, "max": 1, "median": 1, "mean": 1, "unit": ""},
                    },
                    "doors": {},
                    "windows": {},
                    "wall_thickness": 0.3,
                    "fire_compartments": [
                        {
                            "name": "FC1",
                            "x_ratio": [0, 0.5],
                            "y_ratio": [0, 1.0],
                            "wall_thickness": 0.3,
                            "wall_material": "CONCRETE",
                            "openings": [
                                {"wall": "x_max", "type": "door", "position": 0.5, "width": 4.0, "height": 5.0, "z_bottom": 0},
                            ],
                            "combustibles": [{"key": "CABLE_BUNDLE", "count": 3}],
                            "specialized_components": [],
                        },
                        {
                            "name": "FC2",
                            "x_ratio": [0.5, 1.0],
                            "y_ratio": [0, 1.0],
                            "wall_thickness": 0.3,
                            "wall_material": "CONCRETE",
                            "openings": [],
                            "combustibles": [],
                            "specialized_components": [],
                        },
                    ],
                    "specialized_components": [],
                },
            },
        }

    def test_type_is_specialized(self, minimal_old):
        result = migrate_specialized(minimal_old)
        assert result["type"] == "specialized"

    def test_cn_name_preserved(self, minimal_old):
        result = migrate_specialized(minimal_old)
        assert result["cn_name"] == "Test Facility"

    def test_fire_separation_removed(self, minimal_old):
        result = migrate_specialized(minimal_old)
        assert "fire_separation" not in result

    def test_buildings_is_list(self, minimal_old):
        result = migrate_specialized(minimal_old)
        assert isinstance(result["buildings"], list)
        assert len(result["buildings"]) == 1

    def test_building_name(self, minimal_old):
        result = migrate_specialized(minimal_old)
        b = result["buildings"][0]
        assert b["name"] == "Bay_A1"
        assert b["cn_name"] == "A1 Bay"

    def test_building_boundary(self, minimal_old):
        result = migrate_specialized(minimal_old)
        b = result["buildings"][0]
        # boundary = [offset_x, length, offset_y, width]
        assert b["boundary"] == [10, 20, 200, 100]

    def test_building_height(self, minimal_old):
        result = migrate_specialized(minimal_old)
        b = result["buildings"][0]
        assert b["height"] == 15

    def test_wall_thickness(self, minimal_old):
        result = migrate_specialized(minimal_old)
        b = result["buildings"][0]
        assert b["wall_thickness"] == 0.3

    def test_rotation_removed(self, minimal_old):
        result = migrate_specialized(minimal_old)
        b = result["buildings"][0]
        assert "rotation" not in b

    def test_stories_structure(self, minimal_old):
        result = migrate_specialized(minimal_old)
        b = result["buildings"][0]
        assert len(b["stories"]) == 1
        s = b["stories"][0]
        assert s["name"] == "1F"
        assert s["height"] == 15

    def test_fc_boundary_absolute(self, minimal_old):
        result = migrate_specialized(minimal_old)
        fcs = result["buildings"][0]["stories"][0]["fire_compartments"]
        # FC1: x_ratio=[0,0.5], length=20 -> x=[0,10]
        # y_ratio=[0,1.0], width=100 -> y=[0,100]
        assert fcs[0]["boundary"] == [0, 10, 0, 100]
        # FC2: x_ratio=[0.5,1.0] -> x=[10,20]
        assert fcs[1]["boundary"] == [10, 20, 0, 100]

    def test_fc_opening_converted(self, minimal_old):
        result = migrate_specialized(minimal_old)
        fcs = result["buildings"][0]["stories"][0]["fire_compartments"]
        opening = fcs[0]["openings"][0]
        assert opening["wall"] == "x_max"
        assert opening["type"] == "door"
        # FC1 boundary=[0,10,0,100], x_max wall -> wall_length = 100-0 = 100
        # w_offset = 0.5 * 100 - 4/2 = 48
        assert opening["boundary"] == [48.0, 4.0, 0, 5.0]

    def test_fc_fields_renamed(self, minimal_old):
        result = migrate_specialized(minimal_old)
        fc = result["buildings"][0]["stories"][0]["fire_compartments"][0]
        assert "firewall_thickness" in fc
        assert "firewall_material" in fc
        assert "wall_thickness" not in fc or fc.get("firewall_thickness") == 0.3

    def test_combustibles_preserved(self, minimal_old):
        result = migrate_specialized(minimal_old)
        fc = result["buildings"][0]["stories"][0]["fire_compartments"][0]
        assert fc["combustibles"] == [{"key": "CABLE_BUNDLE", "count": 3}]

    def test_roof_present(self, minimal_old):
        result = migrate_specialized(minimal_old)
        s = result["buildings"][0]["stories"][0]
        assert "roof" in s
        assert s["roof"]["material"] == "CONCRETE"

    def test_multi_story(self):
        """Building with 2 stories should produce 2 story entries."""
        old = {
            "cn_name": "Multi",
            "fire_separation": 0,
            "sub_types": {
                "B1": {
                    "cn_name": "B1",
                    "offset": {"x": 0, "y": 0},
                    "building": {
                        "length": {"min": 40, "max": 40, "median": 40, "mean": 40, "unit": "m"},
                        "width": {"min": 20, "max": 20, "median": 20, "mean": 20, "unit": "m"},
                        "height": {"min": 10, "max": 10, "median": 10, "mean": 10, "unit": "m"},
                        "stories": {"min": 2, "max": 2, "median": 2, "mean": 2, "unit": ""},
                    },
                    "doors": {},
                    "windows": {},
                    "wall_thickness": 0.3,
                    "fire_compartments": [
                        {
                            "name": "FC",
                            "x_ratio": [0, 1.0],
                            "y_ratio": [0, 1.0],
                            "wall_thickness": 0.3,
                            "wall_material": "CONCRETE",
                            "openings": [],
                            "combustibles": [],
                            "specialized_components": [],
                        }
                    ],
                    "specialized_components": [],
                },
            },
        }
        result = migrate_specialized(old)
        b = result["buildings"][0]
        assert len(b["stories"]) == 2
        assert b["stories"][0]["name"] == "1F"
        assert b["stories"][1]["name"] == "2F"
        assert b["stories"][0]["height"] == 5.0
        assert b["stories"][1]["height"] == 5.0

    def test_no_fcs_creates_default(self):
        """Building with no fire_compartments should get a default FC."""
        old = {
            "cn_name": "No FC",
            "sub_types": {
                "B1": {
                    "cn_name": "B1",
                    "offset": {"x": 0, "y": 0},
                    "building": {
                        "length": {"min": 10, "max": 10, "median": 10, "mean": 10, "unit": "m"},
                        "width": {"min": 5, "max": 5, "median": 5, "mean": 5, "unit": "m"},
                        "height": {"min": 3, "max": 3, "median": 3, "mean": 3, "unit": "m"},
                        "stories": {"min": 1, "max": 1, "median": 1, "mean": 1, "unit": ""},
                    },
                    "wall_thickness": 0.3,
                    "fire_compartments": [],
                },
            },
        }
        result = migrate_specialized(old)
        fcs = result["buildings"][0]["stories"][0]["fire_compartments"]
        assert len(fcs) == 1
        assert fcs[0]["name"] == "default"
        assert fcs[0]["boundary"] == [0, 10, 0, 5]

    def test_y_wall_opening(self):
        """Opening on y_min wall should use x span as wall_length."""
        old = {
            "cn_name": "Y",
            "sub_types": {
                "B1": {
                    "cn_name": "B1",
                    "offset": {"x": 0, "y": 0},
                    "building": {
                        "length": {"min": 60, "max": 60, "median": 60, "mean": 60, "unit": "m"},
                        "width": {"min": 40, "max": 40, "median": 40, "mean": 40, "unit": "m"},
                        "height": {"min": 5, "max": 5, "median": 5, "mean": 5, "unit": "m"},
                        "stories": {"min": 1, "max": 1, "median": 1, "mean": 1, "unit": ""},
                    },
                    "wall_thickness": 0.3,
                    "fire_compartments": [
                        {
                            "name": "FC",
                            "x_ratio": [0, 1.0],
                            "y_ratio": [0, 1.0],
                            "wall_thickness": 0.3,
                            "wall_material": "CONCRETE",
                            "openings": [
                                {"wall": "y_min", "type": "door", "position": 0.5, "width": 6.0, "height": 4.0, "z_bottom": 0},
                            ],
                            "combustibles": [],
                            "specialized_components": [],
                        }
                    ],
                },
            },
        }
        result = migrate_specialized(old)
        fc = result["buildings"][0]["stories"][0]["fire_compartments"][0]
        opening = fc["openings"][0]
        # y_min wall -> wall_length = x_max - x_min = 60
        # w_offset = 0.5 * 60 - 6/2 = 27
        assert opening["boundary"][0] == 27.0


# ============================================================
# migrate_equivalent
# ============================================================
class TestMigrateEquivalent:
    @pytest.fixture
    def minimal_equiv_old(self):
        return {
            "cn_name": "Test Equiv",
            "fire_separation": 20.0,
            "sub_types": {
                "TypeA": {
                    "cn_name": "Type A",
                    "description": "test type",
                    "offset": {"x": 0, "y": 80},
                    "building": {
                        "length": {"min": 50, "max": 120, "median": -1, "mean": -1, "unit": "m"},
                        "width": {"min": 15, "max": 50, "median": -1, "mean": -1, "unit": "m"},
                        "height": {"min": 8, "max": 12, "median": -1, "mean": -1, "unit": "m"},
                        "stories": {"min": 1, "max": 2, "median": -1, "mean": -1, "unit": ""},
                    },
                    "doors": {
                        "width": {"min": 4, "max": 4, "median": -1, "mean": -1, "unit": "m"},
                        "height": {"min": 4, "max": 4, "median": -1, "mean": -1, "unit": "m"},
                        "count": {"min": 1, "max": 3, "median": -1, "mean": -1, "unit": ""},
                    },
                    "windows": {
                        "width": {"min": 0, "max": 0, "median": -1, "mean": -1, "unit": "m"},
                        "height": {"min": 0, "max": 0, "median": -1, "mean": -1, "unit": "m"},
                        "count": {"min": 0, "max": 0, "median": -1, "mean": -1, "unit": ""},
                    },
                    "wall_thickness": 0.3,
                    "fire_compartments": [
                        {
                            "name": "Zone1",
                            "x_ratio": [0, 0.6],
                            "y_ratio": [0, 1],
                            "wall_thickness": 0.3,
                            "wall_material": "CONCRETE",
                            "openings": [
                                {"wall": "x_max", "type": "door", "position": 0.5, "width": 2.0, "height": 2.5, "z_bottom": 0},
                            ],
                            "combustibles": [{"key": "CABLE_BUNDLE", "count": 4}],
                            "specialized_components": [],
                        }
                    ],
                    "specialized_components": [{"key": "ROCKET", "count": 1, "size_class": "small"}],
                },
            },
        }

    def test_type_is_equivalent(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        assert result["type"] == "equivalent"

    def test_cn_name_preserved(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        assert result["cn_name"] == "Test Equiv"

    def test_fire_separation_removed(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        assert "fire_separation" not in result

    def test_buildings_array(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        assert len(result["buildings"]) == 1

    def test_length_range(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        assert b["length_range"] == [50, 120]

    def test_width_range(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        assert b["width_range"] == [15, 50]

    def test_height_range(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        assert b["height_range"] == [8, 12]

    def test_stories_range(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        assert b["stories_range"] == [1, 2]

    def test_empty_stories(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        assert b["stories"] == []

    def test_stories_template_has_doors(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        tmpl = b["stories_template"][0]
        assert "doors" in tmpl
        assert tmpl["doors"]["width"] == [4, 4]

    def test_stories_template_has_windows(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        tmpl = b["stories_template"][0]
        assert "windows" in tmpl

    def test_fc_boundary_ratio(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        fc = b["stories_template"][0]["fire_compartments"][0]
        assert fc["boundary_ratio"] == [0, 0.6, 0, 1]

    def test_fc_opening_ratios(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        fc = b["stories_template"][0]["fire_compartments"][0]
        opening = fc["openings"][0]
        assert "w_offset_ratio" in opening
        assert "width_ratio" in opening
        # x_max wall -> wall_length = width_max = 50
        # w_offset = 0.5*50 - 2/2 = 24
        # w_offset_ratio = 24 / 50 = 0.48
        assert pytest.approx(opening["w_offset_ratio"], abs=0.001) == 0.48
        assert pytest.approx(opening["width_ratio"], abs=0.001) == 0.04

    def test_specialized_components_preserved(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        assert len(b["specialized_components"]) == 1
        assert b["specialized_components"][0]["key"] == "ROCKET"

    def test_combustibles_in_fc(self, minimal_equiv_old):
        result = migrate_equivalent(minimal_equiv_old)
        b = result["buildings"][0]
        fc = b["stories_template"][0]["fire_compartments"][0]
        assert fc["combustibles"] == [{"key": "CABLE_BUNDLE", "count": 4}]


# ============================================================
# migrate_building_config
# ============================================================
class TestMigrateBuildingConfig:
    @pytest.fixture
    def minimal_config(self):
        return {
            "chid": "test_plant",
            "building_group": {
                "buildings": [
                    {
                        "name": "Main Hall",
                        "length": 100.0,
                        "width": 20.0,
                        "wall_thickness": 0.3,
                        "x_offset": 0,
                        "y_offset": 0,
                        "stories": [
                            {
                                "name": "1F",
                                "height": 10.0,
                                "walls": [
                                    {"name": "S", "x1": 0, "y1": 0, "x2": 100, "y2": 0, "thickness": 0.3, "is_external": True, "height": 10},
                                    {"name": "N", "x1": 0, "y1": 20, "x2": 100, "y2": 20, "thickness": 0.3, "is_external": True, "height": 10},
                                    {"name": "W", "x1": 0, "y1": 0, "x2": 0, "y2": 20, "thickness": 0.3, "is_external": True, "height": 10},
                                    {"name": "E", "x1": 100, "y1": 0, "x2": 100, "y2": 20, "thickness": 0.3, "is_external": True, "height": 10},
                                ],
                                "openings": [
                                    {"wall_index": 0, "type": "door", "position": 0.5, "width": 6.0, "height": 4.5, "z_bottom": 0},
                                    {"wall_index": 2, "type": "window", "position": 0.5, "width": 1.0, "height": 1.0, "z_bottom": 6.0},
                                ],
                                "combustibles": [
                                    {"id": "CB_001", "preset_key": "RUBBER", "name": "Belt", "x": 5, "y": 5, "z": 0,
                                     "length": 1, "width": 1, "height": 1, "hrrpua": 700, "ignition_temp": 370,
                                     "color": "BLACK", "matl": {}, "compartment_id": "FC_0",
                                     "component_key": "", "material_key": ""},
                                ],
                            },
                        ],
                        "roof": {"thickness": 0.2, "material": "CONCRETE"},
                        "materials": {"floor": "CONCRETE", "roof": "CONCRETE", "walls": "CONCRETE"},
                        "specialized_components": [],
                    },
                ],
            },
            "heat_source": {},
            "domain": {},
            "simulation_time": 300,
            "output": {},
        }

    def test_building_group_wrapper(self, minimal_config):
        result = migrate_building_config(minimal_config)
        assert "building_group" in result

    def test_chid_preserved(self, minimal_config):
        result = migrate_building_config(minimal_config)
        assert result["chid"] == "test_plant"

    def test_simulation_fields_preserved(self, minimal_config):
        result = migrate_building_config(minimal_config)
        assert "heat_source" in result
        assert "domain" in result
        assert "simulation_time" in result

    def test_building_boundary(self, minimal_config):
        result = migrate_building_config(minimal_config)
        b = result["building_group"]["buildings"][0]
        # boundary = [x_offset, length, y_offset, width]
        assert b["boundary"] == [0, 100.0, 0, 20.0]

    def test_walls_removed(self, minimal_config):
        result = migrate_building_config(minimal_config)
        s = result["building_group"]["buildings"][0]["stories"][0]
        assert "walls" not in s

    def test_wall_index_converted(self, minimal_config):
        result = migrate_building_config(minimal_config)
        s = result["building_group"]["buildings"][0]["stories"][0]
        openings = s["openings"]
        # wall_index=0 -> y_min
        assert openings[0]["wall"] == "y_min"
        # wall_index=2 -> x_min
        assert openings[1]["wall"] == "x_min"

    def test_opening_boundary_format(self, minimal_config):
        result = migrate_building_config(minimal_config)
        s = result["building_group"]["buildings"][0]["stories"][0]
        opening = s["openings"][0]
        # wall_index=0 (y_min), wall_length=100
        # w_offset = 0.5*100 - 6/2 = 47
        assert opening["boundary"] == [47.0, 6.0, 0, 4.5]

    def test_x_wall_opening(self, minimal_config):
        result = migrate_building_config(minimal_config)
        s = result["building_group"]["buildings"][0]["stories"][0]
        opening = s["openings"][1]
        # wall_index=2 (x_min), wall_length=20
        # w_offset = 0.5*20 - 1/2 = 9.5
        assert opening["boundary"] == [9.5, 1.0, 6.0, 1.0]

    def test_combustibles_in_default_fc(self, minimal_config):
        result = migrate_building_config(minimal_config)
        s = result["building_group"]["buildings"][0]["stories"][0]
        fc = s["fire_compartments"][0]
        assert fc["name"] == "default"
        assert len(fc["combustibles"]) == 1
        assert fc["combustibles"][0]["preset_key"] == "RUBBER"

    def test_default_fc_boundary(self, minimal_config):
        result = migrate_building_config(minimal_config)
        fc = result["building_group"]["buildings"][0]["stories"][0]["fire_compartments"][0]
        assert fc["boundary"] == [0, 100.0, 0, 20.0]

    def test_roof_on_last_story(self, minimal_config):
        result = migrate_building_config(minimal_config)
        s = result["building_group"]["buildings"][0]["stories"][0]
        assert s["roof"]["thickness"] == 0.2
        assert s["roof"]["material"] == "CONCRETE"

    def test_total_height(self, minimal_config):
        result = migrate_building_config(minimal_config)
        b = result["building_group"]["buildings"][0]
        assert b["height"] == 10.0

    def test_cn_name_set(self, minimal_config):
        result = migrate_building_config(minimal_config)
        b = result["building_group"]["buildings"][0]
        assert b["cn_name"] == "Main Hall"

    def test_multi_story_floor_slab_becomes_roof(self):
        """Story N's floor_slab should become story N-1's roof."""
        config = {
            "building_group": {
                "buildings": [{
                    "name": "B1",
                    "length": 50.0,
                    "width": 10.0,
                    "wall_thickness": 0.3,
                    "x_offset": 0,
                    "y_offset": 0,
                    "stories": [
                        {
                            "name": "1F",
                            "height": 5.0,
                            "walls": [],
                            "openings": [],
                            "combustibles": [],
                            "floor_slab": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
                        },
                        {
                            "name": "2F",
                            "height": 4.0,
                            "walls": [],
                            "openings": [],
                            "combustibles": [],
                            "floor_slab": {"thickness": 0.15, "material": "STEEL", "openings": [{"name": "hole", "x": 10, "y": 5, "length": 3, "width": 2}]},
                        },
                    ],
                    "roof": {"thickness": 0.2, "material": "CONCRETE"},
                }],
            },
        }
        result = migrate_building_config(config)
        stories = result["building_group"]["buildings"][0]["stories"]
        assert len(stories) == 2
        # 2F's floor_slab (STEEL) -> 1F's roof
        assert stories[0]["roof"]["material"] == "STEEL"
        assert stories[0]["roof"]["thickness"] == 0.15
        assert len(stories[0]["roof"]["openings"]) == 1
        # Building-level roof -> 2F's roof
        assert stories[1]["roof"]["material"] == "CONCRETE"

    def test_internal_wall_opening(self):
        """Opening on wall_index >= 4 should map to internal_ wall string."""
        config = {
            "building_group": {
                "buildings": [{
                    "name": "B1",
                    "length": 100.0,
                    "width": 20.0,
                    "wall_thickness": 0.3,
                    "x_offset": 0,
                    "y_offset": 0,
                    "stories": [{
                        "name": "1F",
                        "height": 10.0,
                        "walls": [
                            {"name": "S", "x1": 0, "y1": 0, "x2": 100, "y2": 0, "thickness": 0.3, "is_external": True, "height": 10},
                            {"name": "N", "x1": 0, "y1": 20, "x2": 100, "y2": 20, "thickness": 0.3, "is_external": True, "height": 10},
                            {"name": "W", "x1": 0, "y1": 0, "x2": 0, "y2": 20, "thickness": 0.3, "is_external": True, "height": 10},
                            {"name": "E", "x1": 100, "y1": 0, "x2": 100, "y2": 20, "thickness": 0.3, "is_external": True, "height": 10},
                            {"name": "Div", "x1": 50, "y1": 0, "x2": 50, "y2": 20, "thickness": 0.3, "is_external": False, "is_fire_partition": True, "material": "CONCRETE", "height": 10},
                        ],
                        "openings": [
                            {"wall_index": 4, "type": "door", "position": 0.5, "width": 3.0, "height": 4.0, "z_bottom": 0},
                        ],
                        "combustibles": [],
                    }],
                    "roof": {"thickness": 0.2, "material": "CONCRETE"},
                }],
            },
        }
        result = migrate_building_config(config)
        opening = result["building_group"]["buildings"][0]["stories"][0]["openings"][0]
        assert opening["wall"] == "internal_4"
        # Wall 4 runs from (50,0) to (50,20), so wall_length=20
        # w_offset = 0.5*20 - 3/2 = 8.5
        assert opening["boundary"][0] == 8.5


# ============================================================
# Integration: real data structure from alcoa
# ============================================================
class TestAlcoaLikeData:
    """Test migration with data closely matching real alcoa.json structure."""

    @pytest.fixture
    def alcoa_bay_a1(self):
        return {
            "cn_name": "Alcoa Warrick Operations",
            "fire_separation": 15.0,
            "sub_types": {
                "Bay_A1": {
                    "cn_name": "A1 Bay",
                    "description": "Standard narrow bay",
                    "offset": {"x": 9.5, "y": 183},
                    "rotation": 0,
                    "building": {
                        "length": {"min": 19, "max": 19, "median": 19, "mean": 19, "unit": "m"},
                        "width": {"min": 334, "max": 334, "median": 334, "mean": 334, "unit": "m"},
                        "height": {"min": 15, "max": 15, "median": 15, "mean": 15, "unit": "m"},
                        "stories": {"min": 1, "max": 1, "median": 1, "mean": 1, "unit": ""},
                    },
                    "doors": {},
                    "windows": {},
                    "wall_thickness": 0.3,
                    "fire_compartments": [{
                        "name": "A1",
                        "x_ratio": [0, 1.0],
                        "y_ratio": [0, 1.0],
                        "wall_thickness": 0.3,
                        "wall_material": "CONCRETE",
                        "openings": [
                            {"wall": "x_max", "type": "window", "position": 0.85, "width": 30, "height": 5, "z_bottom": 1},
                            {"wall": "x_min", "type": "door", "position": 0.443, "width": 8, "height": 15, "z_bottom": 0},
                        ],
                        "combustibles": [{"key": "PREBAKED_ANODE_BLOCK", "count": 320}],
                        "specialized_components": [{"key": "POT_TENDING_MACHINE", "count": 2}],
                    }],
                    "specialized_components": [],
                },
            },
        }

    def test_boundary(self, alcoa_bay_a1):
        result = migrate_specialized(alcoa_bay_a1)
        b = result["buildings"][0]
        assert b["boundary"] == [9.5, 19, 183, 334]

    def test_fc_covers_entire_building(self, alcoa_bay_a1):
        result = migrate_specialized(alcoa_bay_a1)
        fc = result["buildings"][0]["stories"][0]["fire_compartments"][0]
        assert fc["boundary"] == [0, 19, 0, 334]

    def test_x_max_window_offset(self, alcoa_bay_a1):
        """x_max wall -> wall_length = y span = 334. w_offset = 0.85*334 - 30/2 = 268.9"""
        result = migrate_specialized(alcoa_bay_a1)
        fc = result["buildings"][0]["stories"][0]["fire_compartments"][0]
        window = fc["openings"][0]
        assert window["wall"] == "x_max"
        assert window["boundary"][0] == pytest.approx(268.9, abs=0.1)
        assert window["boundary"][1] == 30
        assert window["boundary"][2] == 1  # z_bottom
        assert window["boundary"][3] == 5  # height

    def test_x_min_door_offset(self, alcoa_bay_a1):
        """x_min wall -> wall_length = 334. w_offset = 0.443*334 - 8/2 = 143.962"""
        result = migrate_specialized(alcoa_bay_a1)
        fc = result["buildings"][0]["stories"][0]["fire_compartments"][0]
        door = fc["openings"][1]
        assert door["wall"] == "x_min"
        assert door["boundary"][0] == pytest.approx(143.962, abs=0.1)
        assert door["boundary"][1] == 8
        assert door["boundary"][2] == 0
        assert door["boundary"][3] == 15
