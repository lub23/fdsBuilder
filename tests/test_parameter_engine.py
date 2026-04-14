#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for models.parameter_engine (equivalent model template expansion)."""

import pytest
from models.building import Opening, Roof, FireCompartment, Story, Building
from models.parameter_engine import ParameterEngine


# ============================================================
# resolve_range
# ============================================================
class TestResolveRange:
    def test_two_element_midpoint(self):
        """[min, max] -> (min+max)/2"""
        assert ParameterEngine.resolve_range([10, 20]) == 15.0

    def test_three_element_default(self):
        """[min, max, default] -> default"""
        assert ParameterEngine.resolve_range([2, 4, 3]) == 3.0

    def test_two_element_same(self):
        assert ParameterEngine.resolve_range([5, 5]) == 5.0

    def test_two_element_floats(self):
        assert ParameterEngine.resolve_range([1.5, 2.5]) == pytest.approx(2.0)

    def test_three_element_default_is_min(self):
        assert ParameterEngine.resolve_range([1, 10, 1]) == 1.0

    def test_three_element_default_is_max(self):
        assert ParameterEngine.resolve_range([1, 10, 10]) == 10.0


# ============================================================
# _wall_length
# ============================================================
class TestWallLength:
    """fc_boundary = [x_min, x_max, y_min, y_max].
    x_min/x_max walls: y_max - y_min.
    y_min/y_max walls: x_max - x_min.
    """

    def test_x_min(self):
        assert ParameterEngine._wall_length([0, 40, 0, 20], "x_min") == 20.0

    def test_x_max(self):
        assert ParameterEngine._wall_length([0, 40, 0, 20], "x_max") == 20.0

    def test_y_min(self):
        assert ParameterEngine._wall_length([0, 40, 0, 20], "y_min") == 40.0

    def test_y_max(self):
        assert ParameterEngine._wall_length([0, 40, 0, 20], "y_max") == 40.0

    def test_offset_boundary(self):
        assert ParameterEngine._wall_length([10, 50, 5, 25], "x_min") == 20.0
        assert ParameterEngine._wall_length([10, 50, 5, 25], "y_min") == 40.0


# ============================================================
# _distribute_exterior_openings
# ============================================================
class TestDistributeExteriorOpenings:
    """Doors on y_min/y_max, windows on x_min/x_max.
    Spacing = wall_len / (count + 1), center at spacing*(i+1).
    w_offset = center - w/2.
    h_offset: 0 for doors, story_height * 0.4 for windows.
    """

    def _make_template(self, doors=None, windows=None):
        tmpl = {}
        if doors:
            tmpl["doors"] = doors
        if windows:
            tmpl["windows"] = windows
        return tmpl

    def test_doors_on_y_walls(self):
        tmpl = self._make_template(
            doors={"width": [4, 4], "height": [4, 4], "count": [2, 2]},
        )
        openings = ParameterEngine._distribute_exterior_openings(
            tmpl, length=100.0, width=50.0, story_height=10.0
        )
        door_openings = [o for o in openings if o["type"] == "door"]
        # 2 doors on y_min + 2 doors on y_max = 4 doors
        assert len(door_openings) == 4
        y_min_doors = [o for o in door_openings if o["wall"] == "y_min"]
        y_max_doors = [o for o in door_openings if o["wall"] == "y_max"]
        assert len(y_min_doors) == 2
        assert len(y_max_doors) == 2

    def test_doors_spacing(self):
        """With 1 door on a wall of length 100: spacing = 100/2 = 50, center = 50, w_offset = 50 - 2 = 48."""
        tmpl = self._make_template(
            doors={"width": [4, 4], "height": [4, 4], "count": [1, 1]},
        )
        openings = ParameterEngine._distribute_exterior_openings(
            tmpl, length=100.0, width=50.0, story_height=10.0
        )
        # doors go on y_min/y_max walls, wall_len = length = 100
        y_min_doors = [o for o in openings if o["type"] == "door" and o["wall"] == "y_min"]
        assert len(y_min_doors) == 1
        d = y_min_doors[0]
        # spacing = 100 / (1+1) = 50, center = 50, w_offset = 50 - 4/2 = 48
        assert d["boundary"][0] == pytest.approx(48.0)
        assert d["boundary"][1] == pytest.approx(4.0)
        assert d["boundary"][2] == pytest.approx(0.0)  # h_offset=0 for doors
        assert d["boundary"][3] == pytest.approx(4.0)

    def test_windows_on_x_walls(self):
        tmpl = self._make_template(
            windows={"width": [2, 2], "height": [1.5, 1.5], "count": [3, 3]},
        )
        openings = ParameterEngine._distribute_exterior_openings(
            tmpl, length=100.0, width=50.0, story_height=10.0
        )
        win_openings = [o for o in openings if o["type"] == "window"]
        # 3 windows on x_min + 3 on x_max = 6
        assert len(win_openings) == 6
        x_min_wins = [o for o in win_openings if o["wall"] == "x_min"]
        x_max_wins = [o for o in win_openings if o["wall"] == "x_max"]
        assert len(x_min_wins) == 3
        assert len(x_max_wins) == 3

    def test_window_h_offset(self):
        """h_offset for windows = story_height * 0.4."""
        tmpl = self._make_template(
            windows={"width": [2, 2], "height": [1.5, 1.5], "count": [1, 1]},
        )
        openings = ParameterEngine._distribute_exterior_openings(
            tmpl, length=80.0, width=40.0, story_height=10.0
        )
        wins = [o for o in openings if o["type"] == "window"]
        for w in wins:
            assert w["boundary"][2] == pytest.approx(4.0)  # 10 * 0.4

    def test_no_doors_no_windows(self):
        tmpl = {}
        openings = ParameterEngine._distribute_exterior_openings(
            tmpl, length=100.0, width=50.0, story_height=10.0
        )
        assert openings == []

    def test_window_spacing(self):
        """2 windows on x_min wall of width 50: spacing = 50/3, centers at 50/3 and 100/3."""
        tmpl = self._make_template(
            windows={"width": [2, 2], "height": [1.5, 1.5], "count": [2, 2]},
        )
        openings = ParameterEngine._distribute_exterior_openings(
            tmpl, length=80.0, width=50.0, story_height=10.0
        )
        # x_min windows, wall_len = width = 50
        x_min_wins = [o for o in openings if o["wall"] == "x_min" and o["type"] == "window"]
        assert len(x_min_wins) == 2
        spacing = 50.0 / 3  # ~16.667
        # First window center at spacing*1, w_offset = center - w/2
        assert x_min_wins[0]["boundary"][0] == pytest.approx(spacing - 1.0)
        # Second window center at spacing*2
        assert x_min_wins[1]["boundary"][0] == pytest.approx(spacing * 2 - 1.0)


# ============================================================
# _expand_story_template
# ============================================================
class TestExpandStoryTemplate:
    def _make_template(self):
        return {
            "name": "1F",
            "height": 10.0,
            "doors": {
                "width": [4, 4],
                "height": [4, 4],
                "count": [1, 3],
            },
            "windows": {
                "width": [2, 3],
                "height": [1.5, 2],
                "count": [2, 6],
            },
            "fire_compartment_ratios": [
                {
                    "name": "Zone A",
                    "boundary_ratio": [0.0, 0.5, 0.0, 1.0],
                    "firewall_thickness": 0.3,
                    "firewall_material": "CONCRETE",
                    "opening_templates": [
                        {
                            "wall": "x_max",
                            "type": "door",
                            "w_offset_ratio": 0.2,
                            "width_ratio": 0.1,
                            "h_offset": 0,
                            "height": 4.0,
                        }
                    ],
                    "combustibles": [{"key": "WOOD_DESK", "count": 3}],
                    "specialized_components": [],
                },
                {
                    "name": "Zone B",
                    "boundary_ratio": [0.5, 1.0, 0.0, 1.0],
                    "firewall_thickness": 0.3,
                    "firewall_material": "CONCRETE",
                    "opening_templates": [],
                    "combustibles": [],
                    "specialized_components": [],
                },
            ],
            "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
        }

    def test_returns_dict(self):
        tmpl = self._make_template()
        result = ParameterEngine._expand_story_template(tmpl, 100.0, 50.0, 10.0)
        assert isinstance(result, dict)

    def test_has_name(self):
        tmpl = self._make_template()
        result = ParameterEngine._expand_story_template(tmpl, 100.0, 50.0, 10.0)
        assert result["name"] == "1F"

    def test_has_height(self):
        tmpl = self._make_template()
        result = ParameterEngine._expand_story_template(tmpl, 100.0, 50.0, 10.0)
        assert result["height"] == 10.0

    def test_fire_compartments_boundary(self):
        """FC boundary = [ratio[0]*length, ratio[1]*length, ratio[2]*width, ratio[3]*width]"""
        tmpl = self._make_template()
        result = ParameterEngine._expand_story_template(tmpl, 100.0, 50.0, 10.0)
        fcs = result["fire_compartments"]
        assert len(fcs) == 2
        # Zone A: [0.0*100, 0.5*100, 0.0*50, 1.0*50] = [0, 50, 0, 50]
        assert fcs[0]["boundary"] == [0.0, 50.0, 0.0, 50.0]
        # Zone B: [0.5*100, 1.0*100, 0.0*50, 1.0*50] = [50, 100, 0, 50]
        assert fcs[1]["boundary"] == [50.0, 100.0, 0.0, 50.0]

    def test_fire_compartment_openings(self):
        """Opening w_offset = w_offset_ratio * wall_length, width = width_ratio * wall_length."""
        tmpl = self._make_template()
        result = ParameterEngine._expand_story_template(tmpl, 100.0, 50.0, 10.0)
        fcs = result["fire_compartments"]
        # Zone A boundary = [0, 50, 0, 50], x_max wall -> wall_len = y_max - y_min = 50
        fc_a_openings = fcs[0]["openings"]
        assert len(fc_a_openings) == 1
        o = fc_a_openings[0]
        assert o["wall"] == "x_max"
        assert o["type"] == "door"
        # w_offset = 0.2 * 50 = 10.0, width = 0.1 * 50 = 5.0
        assert o["boundary"][0] == pytest.approx(10.0)
        assert o["boundary"][1] == pytest.approx(5.0)
        assert o["boundary"][2] == pytest.approx(0.0)
        assert o["boundary"][3] == pytest.approx(4.0)

    def test_fire_compartment_metadata(self):
        tmpl = self._make_template()
        result = ParameterEngine._expand_story_template(tmpl, 100.0, 50.0, 10.0)
        fcs = result["fire_compartments"]
        assert fcs[0]["name"] == "Zone A"
        assert fcs[0]["firewall_thickness"] == 0.3
        assert fcs[0]["firewall_material"] == "CONCRETE"
        assert fcs[0]["combustibles"] == [{"key": "WOOD_DESK", "count": 3}]
        assert fcs[0]["specialized_components"] == []

    def test_has_exterior_openings(self):
        tmpl = self._make_template()
        result = ParameterEngine._expand_story_template(tmpl, 100.0, 50.0, 10.0)
        assert "openings" in result
        assert len(result["openings"]) > 0

    def test_has_roof(self):
        tmpl = self._make_template()
        result = ParameterEngine._expand_story_template(tmpl, 100.0, 50.0, 10.0)
        assert "roof" in result
        assert result["roof"]["thickness"] == 0.2
        assert result["roof"]["material"] == "CONCRETE"

    def test_no_fire_compartment_ratios(self):
        """Template without fire_compartment_ratios should produce empty list."""
        tmpl = {"name": "1F", "height": 5.0, "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []}}
        result = ParameterEngine._expand_story_template(tmpl, 80.0, 30.0, 5.0)
        assert result["fire_compartments"] == []


# ============================================================
# generate
# ============================================================
class TestGenerate:
    def _make_template_building(self):
        return {
            "name": "Plant",
            "cn_name": "工厂",
            "length_range": [50, 120],
            "width_range": [15, 50],
            "height_range": [8, 12],
            "stories_range": [2, 4, 3],
            "stories_template": [
                {
                    "name": "1F",
                    "height": 10.0,
                    "doors": {
                        "width": [4, 4],
                        "height": [4, 4],
                        "count": [1, 3],
                    },
                    "windows": {
                        "width": [2, 3],
                        "height": [1.5, 2],
                        "count": [2, 6],
                    },
                    "fire_compartment_ratios": [
                        {
                            "name": "Zone A",
                            "boundary_ratio": [0.0, 0.5, 0.0, 1.0],
                            "firewall_thickness": 0.3,
                            "firewall_material": "CONCRETE",
                            "opening_templates": [
                                {
                                    "wall": "x_max",
                                    "type": "door",
                                    "w_offset_ratio": 0.2,
                                    "width_ratio": 0.1,
                                    "h_offset": 0,
                                    "height": 4.0,
                                }
                            ],
                            "combustibles": [{"key": "WOOD_DESK", "count": 3}],
                            "specialized_components": [],
                        }
                    ],
                    "roof": {
                        "thickness": 0.2,
                        "material": "CONCRETE",
                        "openings": [],
                    },
                }
            ],
            "stories": [],
        }

    def test_returns_building(self):
        tmpl = self._make_template_building()
        params = {"length": 85.0, "width": 32.5, "height": 10.0, "stories": 3}
        b = ParameterEngine.generate(tmpl, params)
        assert isinstance(b, Building)

    def test_building_name(self):
        tmpl = self._make_template_building()
        params = {"length": 85.0, "width": 32.5, "height": 10.0, "stories": 3}
        b = ParameterEngine.generate(tmpl, params)
        assert b.name == "Plant"
        assert b.cn_name == "工厂"

    def test_building_boundary(self):
        tmpl = self._make_template_building()
        params = {"length": 85.0, "width": 32.5, "height": 10.0, "stories": 3}
        b = ParameterEngine.generate(tmpl, params)
        assert b.boundary == [0, 85.0, 0, 32.5]

    def test_building_height(self):
        tmpl = self._make_template_building()
        params = {"length": 85.0, "width": 32.5, "height": 10.0, "stories": 3}
        b = ParameterEngine.generate(tmpl, params)
        assert b.height == pytest.approx(10.0)

    def test_stories_count(self):
        tmpl = self._make_template_building()
        params = {"length": 85.0, "width": 32.5, "height": 9.0, "stories": 3}
        b = ParameterEngine.generate(tmpl, params)
        assert len(b.stories) == 3

    def test_story_height(self):
        """Each story height = total_height / num_stories."""
        tmpl = self._make_template_building()
        params = {"length": 85.0, "width": 32.5, "height": 9.0, "stories": 3}
        b = ParameterEngine.generate(tmpl, params)
        for s in b.stories:
            assert s.height == pytest.approx(3.0)

    def test_story_names(self):
        """Stories should be named from template, cycling the last entry."""
        tmpl = self._make_template_building()
        params = {"length": 85.0, "width": 32.5, "height": 9.0, "stories": 3}
        b = ParameterEngine.generate(tmpl, params)
        # Template only has one entry ("1F"), so stories 2 and 3 also use that template
        # but story names should be "1F", "2F", "3F"
        assert b.stories[0].name == "1F"
        assert b.stories[1].name == "2F"
        assert b.stories[2].name == "3F"

    def test_fire_compartments_present(self):
        tmpl = self._make_template_building()
        params = {"length": 85.0, "width": 32.5, "height": 10.0, "stories": 3}
        b = ParameterEngine.generate(tmpl, params)
        # Each story should have fire compartments from the template
        for s in b.stories:
            assert len(s.fire_compartments) >= 1

    def test_fire_compartment_boundary_scales(self):
        """FC boundary should scale with the provided length/width."""
        tmpl = self._make_template_building()
        params = {"length": 100.0, "width": 50.0, "height": 10.0, "stories": 1}
        b = ParameterEngine.generate(tmpl, params)
        fc = b.stories[0].fire_compartments[0]
        # Zone A: boundary_ratio=[0.0, 0.5, 0.0, 1.0] -> [0, 50, 0, 50]
        assert fc.boundary == [0.0, 50.0, 0.0, 50.0]

    def test_exterior_openings_present(self):
        tmpl = self._make_template_building()
        params = {"length": 100.0, "width": 50.0, "height": 10.0, "stories": 1}
        b = ParameterEngine.generate(tmpl, params)
        assert len(b.stories[0].openings) > 0

    def test_opening_types(self):
        """Story-level exterior openings should be Opening instances."""
        tmpl = self._make_template_building()
        params = {"length": 100.0, "width": 50.0, "height": 10.0, "stories": 1}
        b = ParameterEngine.generate(tmpl, params)
        for o in b.stories[0].openings:
            assert isinstance(o, Opening)

    def test_fc_openings_are_opening_instances(self):
        tmpl = self._make_template_building()
        params = {"length": 100.0, "width": 50.0, "height": 10.0, "stories": 1}
        b = ParameterEngine.generate(tmpl, params)
        for fc in b.stories[0].fire_compartments:
            for o in fc.openings:
                assert isinstance(o, Opening)

    def test_roof_present(self):
        tmpl = self._make_template_building()
        params = {"length": 100.0, "width": 50.0, "height": 10.0, "stories": 1}
        b = ParameterEngine.generate(tmpl, params)
        assert isinstance(b.stories[0].roof, Roof)

    def test_multiple_stories_template_cycling(self):
        """When stories > len(stories_template), later stories reuse the last template."""
        tmpl = self._make_template_building()
        params = {"length": 80.0, "width": 30.0, "height": 12.0, "stories": 4}
        b = ParameterEngine.generate(tmpl, params)
        assert len(b.stories) == 4
        # All stories should have fire compartments (from the single template)
        for s in b.stories:
            assert len(s.fire_compartments) >= 1

    def test_z_offsets_updated(self):
        """Building should have z_offsets updated."""
        tmpl = self._make_template_building()
        params = {"length": 85.0, "width": 32.5, "height": 9.0, "stories": 3}
        b = ParameterEngine.generate(tmpl, params)
        assert b.stories[0].z_bottom == pytest.approx(0.0)
        assert b.stories[1].z_bottom == pytest.approx(3.0)
        assert b.stories[2].z_bottom == pytest.approx(6.0)

    def test_single_story(self):
        tmpl = self._make_template_building()
        params = {"length": 60.0, "width": 20.0, "height": 5.0, "stories": 1}
        b = ParameterEngine.generate(tmpl, params)
        assert len(b.stories) == 1
        assert b.stories[0].height == pytest.approx(5.0)
        assert b.stories[0].name == "1F"


# ============================================================
# Integration
# ============================================================
class TestParameterEngineIntegration:
    def test_generate_to_dict_roundtrip(self):
        """Generated building should serialize and deserialize cleanly."""
        tmpl = {
            "name": "Warehouse",
            "cn_name": "仓库",
            "length_range": [30, 60],
            "width_range": [10, 30],
            "height_range": [6, 10],
            "stories_range": [1, 2, 1],
            "stories_template": [
                {
                    "name": "1F",
                    "height": 8.0,
                    "doors": {
                        "width": [3, 3],
                        "height": [3, 3],
                        "count": [1, 1],
                    },
                    "windows": {
                        "width": [1.5, 1.5],
                        "height": [1.0, 1.0],
                        "count": [2, 2],
                    },
                    "fire_compartment_ratios": [
                        {
                            "name": "Main",
                            "boundary_ratio": [0.0, 1.0, 0.0, 1.0],
                            "firewall_thickness": 0.3,
                            "firewall_material": "CONCRETE",
                            "opening_templates": [],
                            "combustibles": [],
                            "specialized_components": [],
                        }
                    ],
                    "roof": {
                        "thickness": 0.2,
                        "material": "CONCRETE",
                        "openings": [],
                    },
                }
            ],
            "stories": [],
        }
        params = {"length": 45.0, "width": 20.0, "height": 8.0, "stories": 1}
        b = ParameterEngine.generate(tmpl, params)
        d = b.to_dict()
        b2 = Building.from_dict(d)
        assert b2.name == "Warehouse"
        assert b2.cn_name == "仓库"
        assert b2.boundary == [0, 45.0, 0, 20.0]
        assert len(b2.stories) == 1
        assert b2.stories[0].name == "1F"
        assert len(b2.stories[0].fire_compartments) == 1
        assert b2.stories[0].fire_compartments[0].name == "Main"

    def test_full_expansion_from_1_json_template(self):
        """Reproduce the template from 1.json equivalent model section."""
        tmpl = {
            "name": "Large Rocket Manufacturing Plant",
            "cn_name": "大型火箭制造厂",
            "length_range": [50, 120],
            "width_range": [15, 50],
            "height_range": [8, 12],
            "stories_range": [2, 4, 3],
            "stories_template": [
                {
                    "name": "1F",
                    "height": 10.0,
                    "doors": {
                        "width": [4, 4],
                        "height": [4, 4],
                        "count": [1, 3],
                    },
                    "windows": {
                        "width": [2, 3],
                        "height": [1.5, 2],
                        "count": [2, 6],
                    },
                    "fire_compartment_ratios": [
                        {
                            "name": "Zone A",
                            "boundary_ratio": [0.0, 0.5, 0.0, 1.0],
                            "firewall_thickness": 0.3,
                            "firewall_material": "CONCRETE",
                            "opening_templates": [
                                {
                                    "wall": "x_max",
                                    "type": "door",
                                    "w_offset_ratio": 0.2,
                                    "width_ratio": 0.1,
                                    "h_offset": 0,
                                    "height": 4.0,
                                }
                            ],
                            "combustibles": [{"key": "WOOD_DESK", "count": 3}],
                            "specialized_components": [
                                {"key": "BOILER_IGNITION_SYSTEM", "count": 1}
                            ],
                        }
                    ],
                    "roof": {
                        "thickness": 0.2,
                        "material": "CONCRETE",
                        "openings": [{"boundary": [1, 2, 2, 2]}],
                    },
                }
            ],
            "stories": [],
        }
        # Use default params from ranges
        length = ParameterEngine.resolve_range(tmpl["length_range"])  # 85.0
        width = ParameterEngine.resolve_range(tmpl["width_range"])  # 32.5
        height = ParameterEngine.resolve_range(tmpl["height_range"])  # 10.0
        stories = int(ParameterEngine.resolve_range(tmpl["stories_range"]))  # 3

        assert length == pytest.approx(85.0)
        assert width == pytest.approx(32.5)
        assert height == pytest.approx(10.0)
        assert stories == 3

        params = {
            "length": length,
            "width": width,
            "height": height,
            "stories": stories,
        }
        b = ParameterEngine.generate(tmpl, params)

        assert isinstance(b, Building)
        assert b.name == "Large Rocket Manufacturing Plant"
        assert b.boundary == [0, 85.0, 0, 32.5]
        assert len(b.stories) == 3

        story_height = 10.0 / 3
        for s in b.stories:
            assert s.height == pytest.approx(story_height)

        # Check FC in first story
        fc = b.stories[0].fire_compartments[0]
        assert fc.name == "Zone A"
        assert fc.boundary == [0.0, 42.5, 0.0, 32.5]
        assert fc.combustibles == [{"key": "WOOD_DESK", "count": 3}]

    def test_boundary_offset_from_template(self):
        """When template has a boundary field, its offset_x/offset_y should be used."""
        tmpl = {
            "name": "Offset Plant",
            "cn_name": "偏移工厂",
            "boundary": [100, 60, 200, 30],
            "length_range": [50, 80],
            "width_range": [20, 40],
            "height_range": [6, 10],
            "stories_range": [1, 1],
            "stories_template": [
                {
                    "name": "1F",
                    "height": 8.0,
                    "doors": {
                        "width": [3, 3],
                        "height": [3, 3],
                        "count": [1, 1],
                    },
                    "windows": {
                        "width": [0, 0],
                        "height": [0, 0],
                        "count": [0, 0],
                    },
                    "fire_compartment_ratios": [],
                    "roof": {
                        "thickness": 0.2,
                        "material": "CONCRETE",
                        "openings": [],
                    },
                }
            ],
            "stories": [],
        }
        params = {"length": 60.0, "width": 30.0, "height": 8.0, "stories": 1}
        b = ParameterEngine.generate(tmpl, params)
        # boundary should use offset from template boundary [100, _, 200, _]
        assert b.boundary[0] == 100  # offset_x
        assert b.boundary[1] == 60.0  # length from params
        assert b.boundary[2] == 200  # offset_y
        assert b.boundary[3] == 30.0  # width from params

    def test_no_boundary_defaults_to_origin(self):
        """Without template boundary, building should be at origin."""
        tmpl = {
            "name": "Origin Plant",
            "cn_name": "原点工厂",
            "length_range": [50, 80],
            "width_range": [20, 40],
            "height_range": [6, 10],
            "stories_range": [1, 1],
            "stories_template": [
                {
                    "name": "1F",
                    "height": 8.0,
                    "fire_compartment_ratios": [],
                    "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
                }
            ],
            "stories": [],
        }
        params = {"length": 60.0, "width": 30.0, "height": 8.0, "stories": 1}
        b = ParameterEngine.generate(tmpl, params)
        assert b.boundary == [0, 60.0, 0, 30.0]

    def test_equivalent_json_fire_compartments_load(self):
        """Verify that loading an equivalent JSON and generating produces fire compartments."""
        import json
        import os
        aerospace_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "facilities", "aerospace.json"
        )
        if not os.path.exists(aerospace_path):
            pytest.skip("aerospace.json not found")

        with open(aerospace_path, "r", encoding="utf-8") as f:
            facility = json.load(f)

        tmpl_building = facility["buildings"][0]
        lr = tmpl_building["length_range"]
        wr = tmpl_building["width_range"]
        hr = tmpl_building["height_range"]
        sr = tmpl_building["stories_range"]
        params = {
            "length": ParameterEngine.resolve_range(lr),
            "width": ParameterEngine.resolve_range(wr),
            "height": ParameterEngine.resolve_range(hr),
            "stories": int(ParameterEngine.resolve_range(sr)),
        }
        b = ParameterEngine.generate(tmpl_building, params)

        assert isinstance(b, Building)
        # Must have fire compartments (the key rename bug would cause 0)
        assert len(b.stories) > 0
        assert len(b.stories[0].fire_compartments) > 0
        # Verify boundary offset is applied
        assert b.boundary[0] == tmpl_building["boundary"][0]
        assert b.boundary[2] == tmpl_building["boundary"][2]
