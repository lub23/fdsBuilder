#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the small/medium/large scale support added in 2026-06-17."""
import pytest

from models.building import Building, BuildingGroup, Story
from models.parameter_engine import ParameterEngine
from models.build_arranger import has_overlap, arrange_buildings
from models.facility import FacilityManager


class TestScaleIdxNormalisation:
    def test_explicit_zero(self):
        assert ParameterEngine.normalise_scale_idx(0) == 0

    def test_explicit_medium(self):
        assert ParameterEngine.normalise_scale_idx(1) == 1

    def test_explicit_large(self):
        assert ParameterEngine.normalise_scale_idx(2) == 2

    def test_legacy_negative_one_is_large(self):
        assert ParameterEngine.normalise_scale_idx(-1) == 2

    def test_none_defaults_to_medium(self):
        assert ParameterEngine.normalise_scale_idx(None) == 1


class TestResolveFuelCount:
    def test_count_scaled_takes_priority(self):
        entry = {"key": "X", "count": 10, "count_scaled": [4, 10, 20]}
        assert ParameterEngine.resolve_fuel_count(entry, 0) == 4
        assert ParameterEngine.resolve_fuel_count(entry, 1) == 10
        assert ParameterEngine.resolve_fuel_count(entry, 2) == 20

    def test_density_multiplier_legacy_path(self):
        entry = {"key": "X", "count": 10}
        assert ParameterEngine.resolve_fuel_count(entry, 0, density_multiplier=0.5) == 5
        assert ParameterEngine.resolve_fuel_count(entry, 1, density_multiplier=0.5) == 5
        assert ParameterEngine.resolve_fuel_count(entry, 2, density_multiplier=1.5) == 15

    def test_density_multiplier_min_one(self):
        entry = {"key": "X", "count": 1}
        # Even with heavy scaling, do not produce zero when source was >0
        assert ParameterEngine.resolve_fuel_count(entry, 0, density_multiplier=0.5) >= 1

    def test_zero_count_stays_zero(self):
        entry = {"key": "X", "count": 0}
        assert ParameterEngine.resolve_fuel_count(entry, 1, density_multiplier=2.0) == 0

    def test_legacy_negative_index(self):
        entry = {"key": "X", "count": 5, "count_scaled": [2, 5, 10]}
        assert ParameterEngine.resolve_fuel_count(entry, -1) == 10


class TestParameterEngineScaleIntegration:
    def _make_template(self):
        return {
            "name": "ScalePlant",
            "cn_name": "规模工厂",
            "length_range": [50, 100, 75],
            "width_range": [20, 40, 30],
            "height_range": [8, 12, 10],
            "stories_range": [1, 2, 1],
            "stories_template": [
                {
                    "name": "1F",
                    "height": 10.0,
                    "doors": {
                        "width": [4, 4], "height": [4, 4], "count": [1, 1]
                    },
                    "windows": {"width": [0, 0], "height": [0, 0], "count": [0, 0]},
                    "fire_compartment_ratios": [
                        {
                            "name": "Zone A",
                            "boundary_ratio": [0.0, 1.0, 0.0, 1.0],
                            "firewall_thickness": 0.5,
                            "firewall_material": "CONCRETE",
                            "opening_templates": [],
                            "combustibles": [
                                {"key": "WOODEN_PALLET", "count": 10,
                                 "count_scaled": [6, 10, 15]}
                            ],
                            "specialized_components": [],
                        }
                    ],
                    "roof": {"thickness": 0.5, "material": "CONCRETE", "openings": []},
                }
            ],
            "stories": [],
        }

    def test_small_uses_count_scaled_zero(self):
        tmpl = self._make_template()
        params = {
            "length": 75.0, "width": 30.0, "height": 10.0, "stories": 1,
            "scale_idx": 0,
        }
        b = ParameterEngine.generate(tmpl, params)
        cb_count = b.stories[0].fire_compartments[0].combustibles[0]["count"]
        assert cb_count == 6

    def test_medium_uses_count_scaled_one(self):
        tmpl = self._make_template()
        params = {
            "length": 75.0, "width": 30.0, "height": 10.0, "stories": 1,
            "scale_idx": 1,
        }
        b = ParameterEngine.generate(tmpl, params)
        cb_count = b.stories[0].fire_compartments[0].combustibles[0]["count"]
        assert cb_count == 10

    def test_large_uses_count_scaled_two(self):
        tmpl = self._make_template()
        params = {
            "length": 75.0, "width": 30.0, "height": 10.0, "stories": 1,
            "scale_idx": 2,
        }
        b = ParameterEngine.generate(tmpl, params)
        cb_count = b.stories[0].fire_compartments[0].combustibles[0]["count"]
        assert cb_count == 15

    def test_legacy_negative_scale_idx_works(self):
        tmpl = self._make_template()
        params = {
            "length": 75.0, "width": 30.0, "height": 10.0, "stories": 1,
            "scale_idx": -1,
        }
        b = ParameterEngine.generate(tmpl, params)
        cb_count = b.stories[0].fire_compartments[0].combustibles[0]["count"]
        assert cb_count == 15

    def test_default_scale_idx_is_medium(self):
        tmpl = self._make_template()
        params = {
            "length": 75.0, "width": 30.0, "height": 10.0, "stories": 1,
        }
        b = ParameterEngine.generate(tmpl, params)
        cb_count = b.stories[0].fire_compartments[0].combustibles[0]["count"]
        assert cb_count == 10


class TestBuildArranger:
    def test_disjoint_buildings_no_overlap(self):
        b1 = Building(name="A", boundary=[0, 10, 0, 10])
        b2 = Building(name="B", boundary=[20, 10, 0, 10])
        assert has_overlap([b1, b2]) is False

    def test_overlapping_buildings_detected(self):
        b1 = Building(name="A", boundary=[0, 10, 0, 10])
        b2 = Building(name="B", boundary=[5, 10, 0, 10])
        assert has_overlap([b1, b2]) is True

    def test_arrange_packs_overlapping(self):
        b1 = Building(name="A", boundary=[0, 10, 0, 10])
        b2 = Building(name="B", boundary=[5, 10, 0, 10])
        arrange_buildings([b1, b2], gap=20.0)
        assert has_overlap([b1, b2]) is False
        # b2 must be at offset_x >= 10 (b1's right edge) + 20 (gap)
        assert b2.offset_x >= 30.0

    def test_arrange_negative_y_lifted(self):
        b1 = Building(name="A", boundary=[0, 10, -5, 10])
        arrange_buildings([b1])
        assert b1.offset_y == 0

    def test_arrange_does_not_disturb_already_separated(self):
        b1 = Building(name="A", boundary=[0, 10, 0, 10])
        b2 = Building(name="B", boundary=[40, 10, 0, 10])
        original_a = b1.offset_x
        original_b = b2.offset_x
        arrange_buildings([b1, b2], gap=20.0)
        assert b1.offset_x == original_a
        assert b2.offset_x == original_b

    def test_arrange_preserves_flag(self):
        b1 = Building(name="A", boundary=[0, 10, 0, 10])
        b2 = Building(name="B", boundary=[5, 10, 0, 10])
        arrange_buildings([b1, b2], gap=20.0, preserve_offsets=True)
        assert b1.offset_x == 0
        assert b2.offset_x == 5
        assert has_overlap([b1, b2]) is True


class TestFacilityManagerReload:
    def test_load_equivalent_supports_scale_idx(self):
        mgr = FacilityManager()
        for bname in mgr.list_buildings("aerospace"):
            lower = mgr.load_equivalent(
                "aerospace",
                bname,
                {
                    "length": 60, "width": 25, "height": 10, "stories": 2,
                    "scale_idx": 0,
                },
            )
            assert isinstance(lower, Building)
            med = mgr.load_equivalent(
                "aerospace",
                bname,
                {
                    "length": 85, "width": 32, "height": 12, "stories": 2,
                    "scale_idx": 1,
                },
            )
            assert isinstance(med, Building)
            break

    def test_facility_meta_block_present(self):
        mgr = FacilityManager()
        for fname in [
            "aerospace",
            "airport_hangar",
            "machinery_manufacturing",
            "metallurgical_facilities",
        ]:
            assert "meta" in mgr.facilities[fname], \
                f"facility {fname} is missing meta block"
            assert "default_scale" in mgr.facilities[fname]["meta"]

    def test_all_combustibles_have_count_scaled(self):
        mgr = FacilityManager()
        for fname in (
            "aerospace",
            "airport_hangar",
            "machinery_manufacturing",
            "metallurgical_facilities",
        ):
            for b in mgr.facilities[fname]["buildings"]:
                for tmpl in b.get("stories_template", []):
                    for fc in tmpl.get("fire_compartment_ratios", []):
                        for entry in fc.get("combustibles", []):
                            if entry.get("count", 0) > 0:
                                assert "count_scaled" in entry, (
                                    f"{fname}: {entry} missing count_scaled"
                                )
                                cs = entry["count_scaled"]
                                assert len(cs) == 3

    def test_scale_dimensions_drive_params(self):
        mgr = FacilityManager()
        for fname in ("aerospace", "machinery_manufacturing", "metallurgical_facilities"):
            for bname in mgr.list_buildings(fname):
                small = mgr.params_for_scale(fname, bname, scale_idx=0)
                medium = mgr.params_for_scale(fname, bname, scale_idx=1)
                large = mgr.params_for_scale(fname, bname, scale_idx=2)
                assert small["length"] < medium["length"] < large["length"]
                assert small["width"] < medium["width"] < large["width"]
                assert small["height"] <= medium["height"] <= large["height"]

    def test_facility_layout_keeps_declared_gap_at_every_scale(self):
        mgr = FacilityManager()
        for fname in ("aerospace", "machinery_manufacturing", "metallurgical_facilities"):
            layout = mgr.facilities[fname]["layout"]
            gap_x = layout["gap_x"]
            gap_y = layout["gap_y"]
            for scale_idx in (0, 1, 2):
                buildings = []
                for bname in mgr.list_buildings(fname):
                    params = mgr.params_for_scale(fname, bname, scale_idx=scale_idx)
                    buildings.append(mgr.load_equivalent(fname, bname, params))
                assert mgr.arrange_buildings_by_layout(fname, buildings) is True
                assert has_overlap(buildings) is False

                by_name = {b.name: b for b in buildings}
                normalized_rows = [
                    [name for name in row if name in by_name]
                    for row in layout["rows"]
                ]
                normalized_rows = [row for row in normalized_rows if row]
                layout_names = {name for row in normalized_rows for name in row}
                remaining = [
                    name for name in by_name
                    if name not in layout_names
                ]
                if remaining:
                    normalized_rows.append(remaining)

                previous_row_bottom = None
                for row in normalized_rows:
                    row_buildings = [by_name[name] for name in row]
                    for left, right in zip(row_buildings, row_buildings[1:]):
                        actual_gap = right.offset_x - (left.offset_x + left.length)
                        assert actual_gap == pytest.approx(gap_x)
                    row_top = row_buildings[0].offset_y
                    if previous_row_bottom is not None:
                        assert row_top - previous_row_bottom == pytest.approx(gap_y)
                    previous_row_bottom = max(b.offset_y + b.width for b in row_buildings)

    def test_airport_hangar_is_one_facility_with_three_scale_types(self):
        mgr = FacilityManager()
        assert "airport_uav_hangar" not in mgr.facilities
        assert len(mgr.list_buildings("airport_hangar")) == 1
        bname = mgr.list_buildings("airport_hangar")[0]
        small = mgr.params_for_scale("airport_hangar", bname, scale_idx=0)
        medium = mgr.params_for_scale("airport_hangar", bname, scale_idx=1)
        large = mgr.params_for_scale("airport_hangar", bname, scale_idx=2)
        assert small["scale_idx"] == 0
        assert medium["scale_idx"] == 1
        assert large["scale_idx"] == 2
        assert (small["length"], small["width"], small["height"]) != (
            medium["length"], medium["width"], medium["height"]
        )
        assert (medium["length"], medium["width"], medium["height"]) != (
            large["length"], large["width"], large["height"]
        )
        assert mgr.load_equivalent("airport_hangar", bname, small).cn_name == "小型机库"
        assert mgr.load_equivalent("airport_hangar", bname, medium).cn_name == "中型机库"
        assert mgr.load_equivalent("airport_hangar", bname, large).cn_name == "大型机库"


class TestFDSGeneratorMeshConfig:
    def test_default_grid_is_one_metre(self):
        b = Building(name="Test", boundary=[0, 40, 0, 20], wall_thickness=0.3,
                     stories=[Story(name="S1", height=8.0)])
        b.update_z_offsets()
        bg = BuildingGroup(buildings=[b])
        from generators.fds_generator import FDSGenerator
        gen = FDSGenerator(bg)
        _domain, grid_size, num_meshes, _ref = gen._compute_mesh()
        assert grid_size == 1.0

    def test_refinement_overrides_user_num_meshes(self):
        b = Building(name="Test", boundary=[0, 40, 0, 20], wall_thickness=0.3,
                     stories=[Story(name="S1", height=8.0)])
        b.update_z_offsets()
        bg = BuildingGroup(buildings=[b], domain={"grid_size": 1.0, "num_meshes": 4})
        from generators.fds_generator import FDSGenerator
        gen = FDSGenerator(bg)
        _domain, _grid_size, num_meshes, _ref = gen._compute_mesh()
        assert num_meshes == 5

    def test_user_grid_size_used(self):
        b = Building(name="Test", boundary=[0, 40, 0, 20], wall_thickness=0.3,
                     stories=[Story(name="S1", height=8.0)])
        b.update_z_offsets()
        bg = BuildingGroup(buildings=[b], domain={"grid_size": 2.0, "num_meshes": 1})
        from generators.fds_generator import FDSGenerator
        gen = FDSGenerator(bg)
        _domain, grid_size, _num, _ref = gen._compute_mesh()
        assert grid_size == 2.0
