#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for models.building (new dataclass-based model classes)."""

import pytest
from models.building import (
    Opening,
    Roof,
    FireCompartment,
    Story,
    Building,
    BuildingGroup,
)


# ============================================================
# Opening
# ============================================================
class TestOpening:
    def test_basic_creation(self):
        o = Opening(wall="x_max", type="door", boundary=[10.0, 5.0, 0.0, 4.0])
        assert o.wall == "x_max"
        assert o.type == "door"
        assert o.boundary == [10.0, 5.0, 0.0, 4.0]

    def test_to_dict(self):
        o = Opening(wall="y_min", type="window", boundary=[3.0, 2.0, 1.0, 1.5])
        d = o.to_dict()
        assert d == {
            "wall": "y_min",
            "type": "window",
            "boundary": [3.0, 2.0, 1.0, 1.5],
        }

    def test_from_dict(self):
        d = {"wall": "x_min", "type": "loading_dock", "boundary": [0.0, 6.0, 0.0, 5.0]}
        o = Opening.from_dict(d)
        assert o.wall == "x_min"
        assert o.type == "loading_dock"
        assert o.boundary == [0.0, 6.0, 0.0, 5.0]

    def test_roundtrip(self):
        o = Opening(wall="y_max", type="ribbon_window", boundary=[0.0, 20.0, 2.5, 0.5])
        assert Opening.from_dict(o.to_dict()) == o

    def test_all_wall_values(self):
        for wall in ("x_min", "x_max", "y_min", "y_max"):
            o = Opening(wall=wall, type="opening", boundary=[0, 1, 0, 1])
            assert o.wall == wall

    def test_all_type_values(self):
        for t in ("door", "window", "opening", "loading_dock", "ribbon_window"):
            o = Opening(wall="x_min", type=t, boundary=[0, 1, 0, 1])
            assert o.type == t


# ============================================================
# Roof
# ============================================================
class TestRoof:
    def test_defaults(self):
        r = Roof()
        assert r.thickness == 0.2
        assert r.material == "CONCRETE"
        assert r.openings == []

    def test_custom(self):
        r = Roof(thickness=0.3, material="STEEL", openings=[{"boundary": [1, 2, 3, 4]}])
        assert r.thickness == 0.3
        assert r.material == "STEEL"
        assert len(r.openings) == 1

    def test_to_dict(self):
        r = Roof(
            thickness=0.15, material="METAL", openings=[{"boundary": [0, 5, 0, 5]}]
        )
        d = r.to_dict()
        assert d["thickness"] == 0.15
        assert d["material"] == "METAL"
        assert d["openings"] == [{"boundary": [0, 5, 0, 5]}]

    def test_from_dict(self):
        d = {"thickness": 0.25, "material": "WOOD", "openings": []}
        r = Roof.from_dict(d)
        assert r.thickness == 0.25
        assert r.material == "WOOD"

    def test_from_dict_defaults(self):
        r = Roof.from_dict({})
        assert r.thickness == 0.2
        assert r.material == "CONCRETE"
        assert r.openings == []

    def test_roundtrip(self):
        r = Roof(
            thickness=0.5, material="CONCRETE", openings=[{"boundary": [2, 3, 4, 5]}]
        )
        assert Roof.from_dict(r.to_dict()) == r

    def test_openings_isolation(self):
        """Each Roof instance should have its own openings list."""
        r1 = Roof()
        r2 = Roof()
        r1.openings.append({"boundary": [0, 1, 0, 1]})
        assert r2.openings == []


# ============================================================
# FireCompartment
# ============================================================
class TestFireCompartment:
    def test_defaults(self):
        fc = FireCompartment()
        assert fc.name == ""
        assert fc.boundary == [0, 0, 0, 0]
        assert fc.firewall_thickness == 0.3
        assert fc.firewall_material == "CONCRETE"
        assert fc.openings == []
        assert fc.combustibles == []
        assert fc.specialized_components == []

    def test_custom(self):
        openings = [Opening(wall="x_min", type="door", boundary=[0, 3, 0, 3])]
        fc = FireCompartment(
            name="Zone A",
            boundary=[0, 10, 0, 5],
            firewall_thickness=0.5,
            firewall_material="STEEL",
            openings=openings,
            combustibles=[{"key": "OIL", "count": 2}],
            specialized_components=[{"key": "CRANE", "count": 1}],
        )
        assert fc.name == "Zone A"
        assert fc.boundary == [0, 10, 0, 5]
        assert len(fc.openings) == 1
        assert fc.openings[0].wall == "x_min"

    def test_to_dict(self):
        fc = FireCompartment(
            name="FC1",
            boundary=[0, 20, 0, 10],
            openings=[Opening(wall="y_max", type="window", boundary=[5, 2, 1, 1.5])],
            combustibles=[{"key": "WOOD", "count": 5}],
        )
        d = fc.to_dict()
        assert d["name"] == "FC1"
        assert d["boundary"] == [0, 20, 0, 10]
        assert d["openings"] == [
            {"wall": "y_max", "type": "window", "boundary": [5, 2, 1, 1.5]}
        ]
        assert d["combustibles"] == [{"key": "WOOD", "count": 5}]

    def test_from_dict_with_openings(self):
        d = {
            "name": "FC2",
            "boundary": [10, 20, 0, 10],
            "openings": [
                {"wall": "x_max", "type": "door", "boundary": [2, 3, 0, 4]},
                {"wall": "y_min", "type": "window", "boundary": [1, 2, 1, 1.5]},
            ],
        }
        fc = FireCompartment.from_dict(d)
        assert fc.name == "FC2"
        assert len(fc.openings) == 2
        assert isinstance(fc.openings[0], Opening)
        assert fc.openings[0].wall == "x_max"
        assert fc.openings[1].type == "window"

    def test_from_dict_defaults(self):
        fc = FireCompartment.from_dict({})
        assert fc.name == ""
        assert fc.boundary == [0, 0, 0, 0]
        assert fc.openings == []

    def test_roundtrip(self):
        fc = FireCompartment(
            name="Test",
            boundary=[5, 15, 2, 8],
            firewall_thickness=0.4,
            firewall_material="BRICK",
            openings=[Opening(wall="x_min", type="door", boundary=[0, 2, 0, 3])],
            combustibles=[{"key": "CABLE", "count": 10}],
            specialized_components=[{"key": "PTM", "count": 1}],
        )
        fc2 = FireCompartment.from_dict(fc.to_dict())
        assert fc2.name == fc.name
        assert fc2.boundary == fc.boundary
        assert fc2.firewall_thickness == fc.firewall_thickness
        assert fc2.firewall_material == fc.firewall_material
        assert len(fc2.openings) == len(fc.openings)
        assert fc2.openings[0] == fc.openings[0]
        assert len(fc2.combustibles) == len(fc.combustibles)
        assert fc2.combustibles[0].get("key") == "CABLE"
        assert fc2.specialized_components == fc.specialized_components

    def test_boundary_isolation(self):
        """Each FireCompartment should have its own boundary list."""
        fc1 = FireCompartment()
        fc2 = FireCompartment()
        fc1.boundary[0] = 99
        assert fc2.boundary[0] == 0


# ============================================================
# Story
# ============================================================
class TestStory:
    def test_defaults(self):
        s = Story()
        assert s.name == "1F"
        assert s.height == 3.0
        assert s.openings == []
        assert s.fire_compartments == []
        assert isinstance(s.roof, Roof)
        assert s.z_bottom == 0.0

    def test_z_top(self):
        s = Story(height=5.0)
        s.z_bottom = 10.0
        assert s.z_top == 15.0

    def test_z_bottom_writable(self):
        s = Story()
        s.z_bottom = 3.0
        assert s.z_bottom == 3.0
        assert s.z_top == 6.0

    def test_to_dict(self):
        s = Story(
            name="2F",
            height=4.0,
            openings=[Opening(wall="x_max", type="door", boundary=[1, 2, 0, 3])],
            fire_compartments=[FireCompartment(name="FC1", boundary=[0, 10, 0, 5])],
            roof=Roof(thickness=0.3),
        )
        d = s.to_dict()
        assert d["name"] == "2F"
        assert d["height"] == 4.0
        assert len(d["openings"]) == 1
        assert d["openings"][0]["wall"] == "x_max"
        assert len(d["fire_compartments"]) == 1
        assert d["fire_compartments"][0]["name"] == "FC1"
        assert d["roof"]["thickness"] == 0.3

    def test_from_dict(self):
        d = {
            "name": "3F",
            "height": 5.0,
            "openings": [
                {"wall": "y_min", "type": "window", "boundary": [2, 1.5, 1, 1]}
            ],
            "fire_compartments": [{"name": "FC-A", "boundary": [0, 10, 0, 10]}],
            "roof": {"thickness": 0.25, "material": "STEEL"},
        }
        s = Story.from_dict(d)
        assert s.name == "3F"
        assert s.height == 5.0
        assert len(s.openings) == 1
        assert isinstance(s.openings[0], Opening)
        assert len(s.fire_compartments) == 1
        assert isinstance(s.fire_compartments[0], FireCompartment)
        assert s.roof.thickness == 0.25

    def test_from_dict_defaults(self):
        s = Story.from_dict({})
        assert s.name == "1F"
        assert s.height == 3.0
        assert s.openings == []

    def test_roundtrip(self):
        s = Story(
            name="GF",
            height=6.0,
            openings=[
                Opening(wall="x_min", type="loading_dock", boundary=[0, 8, 0, 5])
            ],
            fire_compartments=[
                FireCompartment(
                    name="Main",
                    boundary=[0, 20, 0, 10],
                    openings=[
                        Opening(wall="y_max", type="window", boundary=[5, 2, 2, 1])
                    ],
                )
            ],
            roof=Roof(thickness=0.2, material="CONCRETE"),
        )
        s2 = Story.from_dict(s.to_dict())
        assert s2.name == s.name
        assert s2.height == s.height
        assert len(s2.openings) == 1
        assert s2.openings[0] == s.openings[0]
        assert len(s2.fire_compartments) == 1
        assert s2.fire_compartments[0].name == s.fire_compartments[0].name
        assert s2.roof.thickness == s.roof.thickness


# ============================================================
# Building
# ============================================================
class TestBuilding:
    def test_defaults(self):
        b = Building()
        assert b.name == ""
        assert b.cn_name == ""
        assert b.boundary == [0, 20, 0, 10]
        assert b.wall_thickness == 0.24
        assert b.height == 3.0
        assert b.stories == []

    def test_properties(self):
        b = Building(boundary=[5, 30, 10, 15])
        assert b.length == 30
        assert b.width == 15
        assert b.offset_x == 5
        assert b.offset_y == 10

    def test_update_z_offsets(self):
        b = Building(
            stories=[
                Story(name="1F", height=3.0),
                Story(name="2F", height=4.0),
                Story(name="3F", height=3.5),
            ]
        )
        b.update_z_offsets()
        assert b.stories[0].z_bottom == 0.0
        assert b.stories[0].z_top == 3.0
        assert b.stories[1].z_bottom == 3.0
        assert b.stories[1].z_top == 7.0
        assert b.stories[2].z_bottom == 7.0
        assert b.stories[2].z_top == 10.5

    def test_update_z_offsets_empty(self):
        b = Building()
        b.update_z_offsets()  # should not raise

    def test_get_exterior_walls(self):
        b = Building(
            boundary=[0, 20, 0, 10],
            wall_thickness=0.24,
            stories=[Story(name="1F", height=3.0)],
        )
        b.update_z_offsets()
        walls = b.get_exterior_walls(0)
        assert set(walls.keys()) == {"x_min", "x_max", "y_min", "y_max"}

        # Check y_min wall (south)
        ym = walls["y_min"]
        assert len(ym) == 6
        assert ym[0] == pytest.approx(-0.12)  # ox - t/2
        assert ym[1] == pytest.approx(20.12)  # ox + L + t/2
        assert ym[2] == pytest.approx(-0.24)  # oy - t
        assert ym[3] == pytest.approx(0.0)  # oy
        assert ym[4] == 0.0  # z0
        assert ym[5] == 3.0  # z1

        # Check x_max wall (east)
        xm = walls["x_max"]
        assert xm[0] == pytest.approx(20.0)  # ox + L
        assert xm[1] == pytest.approx(20.24)  # ox + L + t
        assert xm[2] == pytest.approx(-0.12)  # oy - t/2
        assert xm[3] == pytest.approx(10.12)  # oy + W + t/2

    def test_get_exterior_walls_with_offset(self):
        b = Building(
            boundary=[5, 20, 3, 10],
            wall_thickness=0.5,
            stories=[Story(name="1F", height=4.0)],
        )
        b.update_z_offsets()
        walls = b.get_exterior_walls(0)

        # x_min (west wall)
        xmin = walls["x_min"]
        assert xmin[0] == pytest.approx(5.0 - 0.5)  # ox - t
        assert xmin[1] == pytest.approx(5.0)  # ox
        assert xmin[2] == pytest.approx(3.0 - 0.25)  # oy - t/2
        assert xmin[3] == pytest.approx(13.25)  # oy + W + t/2
        assert xmin[4] == 0.0
        assert xmin[5] == 4.0

    def test_get_exterior_walls_second_story(self):
        b = Building(
            boundary=[0, 10, 0, 10],
            wall_thickness=0.2,
            stories=[Story(name="1F", height=3.0), Story(name="2F", height=4.0)],
        )
        b.update_z_offsets()
        walls = b.get_exterior_walls(1)
        # second story z: 3.0 to 7.0
        assert walls["y_min"][4] == 3.0
        assert walls["y_min"][5] == 7.0

    def test_to_dict(self):
        b = Building(
            name="warehouse",
            cn_name="仓库",
            boundary=[0, 30, 0, 20],
            wall_thickness=0.3,
            height=6.0,
            stories=[Story(name="1F", height=6.0)],
        )
        d = b.to_dict()
        assert d["name"] == "warehouse"
        assert d["cn_name"] == "仓库"
        assert d["boundary"] == [0, 30, 0, 20]
        assert d["wall_thickness"] == 0.3
        assert d["height"] == 6.0
        assert len(d["stories"]) == 1

    def test_from_dict(self):
        d = {
            "name": "factory",
            "cn_name": "工厂",
            "boundary": [10, 40, 5, 25],
            "wall_thickness": 0.25,
            "height": 8.0,
            "stories": [
                {"name": "1F", "height": 4.0},
                {"name": "2F", "height": 4.0},
            ],
        }
        b = Building.from_dict(d)
        assert b.name == "factory"
        assert b.cn_name == "工厂"
        assert b.boundary == [10, 40, 5, 25]
        assert b.length == 40
        assert b.width == 25
        assert len(b.stories) == 2
        assert b.stories[0].name == "1F"

    def test_from_dict_defaults(self):
        b = Building.from_dict({})
        assert b.name == ""
        assert b.boundary == [0, 20, 0, 10]
        assert b.stories == []

    def test_roundtrip(self):
        b = Building(
            name="test",
            cn_name="测试",
            boundary=[2, 25, 3, 12],
            wall_thickness=0.24,
            height=9.0,
            stories=[
                Story(
                    name="1F",
                    height=3.0,
                    openings=[
                        Opening(wall="x_max", type="door", boundary=[5, 3, 0, 3])
                    ],
                ),
                Story(name="2F", height=3.0),
                Story(name="3F", height=3.0),
            ],
        )
        b2 = Building.from_dict(b.to_dict())
        assert b2.name == b.name
        assert b2.cn_name == b.cn_name
        assert b2.boundary == b.boundary
        assert b2.wall_thickness == b.wall_thickness
        assert b2.height == b.height
        assert len(b2.stories) == len(b.stories)
        assert b2.stories[0].openings[0] == b.stories[0].openings[0]


# ============================================================
# BuildingGroup
# ============================================================
class TestBuildingGroup:
    def test_defaults(self):
        bg = BuildingGroup()
        assert bg.buildings == []
        assert bg.heat_source == {
            "azimuth": 0,
            "elevation": 0,
            "net_heat_flux": 1000,
            "duration": 1.36,
        }
        assert bg.simulation_time == 1800
        assert bg.domain == {"padding": 5.0, "grid_size": 1.0}
        assert bg.output == {"slices": True, "devices": True}

    def test_custom(self):
        bg = BuildingGroup(
            buildings=[Building(name="A"), Building(name="B")],
            heat_source={"enabled": True},
            simulation_time=600,
        )
        assert len(bg.buildings) == 2
        assert bg.simulation_time == 600

    def test_to_dict(self):
        bg = BuildingGroup(
            buildings=[Building(name="W1", boundary=[0, 20, 0, 10])],
            simulation_time=120,
        )
        d = bg.to_dict()
        assert "buildings" in d
        assert len(d["buildings"]) == 1
        assert d["buildings"][0]["name"] == "W1"
        assert d["simulation_time"] == 120
        assert d["heat_source"] == {
            "azimuth": 0,
            "elevation": 0,
            "net_heat_flux": 1000,
            "duration": 1.36,
        }
        assert d["domain"] == {"padding": 5.0, "grid_size": 1.0}
        assert d["output"] == {"slices": True, "devices": True}

    def test_from_dict_project_format(self):
        """Test loading from project save/load format: {building_group: {buildings: [...]}}"""
        d = {
            "building_group": {
                "buildings": [
                    {"name": "B1", "boundary": [0, 20, 0, 10], "stories": []},
                    {"name": "B2", "boundary": [30, 20, 0, 10], "stories": []},
                ],
                "simulation_time": 500,
                "heat_source": {"enabled": True},
            }
        }
        bg = BuildingGroup.from_dict(d)
        assert len(bg.buildings) == 2
        assert bg.buildings[0].name == "B1"
        assert bg.buildings[1].name == "B2"
        assert bg.simulation_time == 500

    def test_from_dict_facility_format(self):
        """Test loading from facility JSON format: {type: specialized, buildings: [...]}"""
        d = {
            "type": "specialized",
            "buildings": [
                {"name": "Factory", "boundary": [0, 40, 0, 20], "stories": []},
            ],
            "simulation_time": 300,
        }
        bg = BuildingGroup.from_dict(d)
        assert len(bg.buildings) == 1
        assert bg.buildings[0].name == "Factory"
        assert bg.simulation_time == 300

    def test_from_dict_direct_format(self):
        """Test loading from direct dict format: {buildings: [...]}"""
        d = {
            "buildings": [
                {"name": "X", "boundary": [0, 10, 0, 10], "stories": []},
            ],
            "simulation_time": 200,
        }
        bg = BuildingGroup.from_dict(d)
        assert len(bg.buildings) == 1
        assert bg.buildings[0].name == "X"
        assert bg.simulation_time == 200

    def test_from_dict_defaults(self):
        bg = BuildingGroup.from_dict({})
        assert bg.buildings == []
        assert bg.simulation_time == 1800

    def test_roundtrip(self):
        bg = BuildingGroup(
            buildings=[
                Building(
                    name="HQ",
                    cn_name="总部",
                    boundary=[0, 50, 0, 30],
                    wall_thickness=0.3,
                    height=12.0,
                    stories=[
                        Story(name="1F", height=4.0),
                        Story(name="2F", height=4.0),
                        Story(name="3F", height=4.0),
                    ],
                )
            ],
            heat_source={
                "azimuth": 45,
                "elevation": 30,
                "net_heat_flux": 15.0,
                "duration": 2.5,
            },
            simulation_time=600,
            domain={"padding": 10.0, "grid_size": 0.5},
            output={"slices": True, "devices": False},
        )
        d = bg.to_dict()
        bg2 = BuildingGroup.from_dict(d)
        assert len(bg2.buildings) == len(bg.buildings)
        assert bg2.buildings[0].name == "HQ"
        assert bg2.buildings[0].cn_name == "总部"
        assert len(bg2.buildings[0].stories) == 3
        assert bg2.simulation_time == 600
        assert bg2.heat_source == {
            "azimuth": 45,
            "elevation": 30,
            "net_heat_flux": 15.0,
            "duration": 2.5,
        }
        assert bg2.domain == {"padding": 10.0, "grid_size": 0.5}
        assert bg2.output == {"slices": True, "devices": False}


# ============================================================
# Integration / Edge Cases
# ============================================================
class TestIntegration:
    def test_deeply_nested_roundtrip(self):
        """Full round-trip with buildings, stories, fire compartments, openings."""
        bg = BuildingGroup(
            buildings=[
                Building(
                    name="plant",
                    cn_name="电解车间",
                    boundary=[0, 100, 0, 50],
                    wall_thickness=0.3,
                    height=15.0,
                    stories=[
                        Story(
                            name="1F",
                            height=15.0,
                            openings=[
                                Opening(
                                    wall="x_min", type="door", boundary=[10, 5, 0, 4]
                                ),
                                Opening(
                                    wall="x_max",
                                    type="window",
                                    boundary=[20, 3, 2, 1.5],
                                ),
                            ],
                            fire_compartments=[
                                FireCompartment(
                                    name="Zone-A",
                                    boundary=[0, 50, 0, 50],
                                    openings=[
                                        Opening(
                                            wall="x_max",
                                            type="door",
                                            boundary=[5, 3, 0, 4],
                                        ),
                                    ],
                                    combustibles=[
                                        {"key": "PREBAKED_ANODE_BLOCK", "count": 320},
                                    ],
                                    specialized_components=[
                                        {"key": "POT_TENDING_MACHINE", "count": 2},
                                    ],
                                ),
                                FireCompartment(
                                    name="Zone-B",
                                    boundary=[50, 100, 0, 50],
                                ),
                            ],
                            roof=Roof(
                                thickness=0.3,
                                material="STEEL",
                                openings=[{"boundary": [10, 5, 10, 5]}],
                            ),
                        ),
                    ],
                ),
            ],
            heat_source={"enabled": True, "radiation_flux": 50.0},
            simulation_time=600,
        )
        d = bg.to_dict()
        bg2 = BuildingGroup.from_dict(d)

        assert len(bg2.buildings) == 1
        b = bg2.buildings[0]
        assert b.name == "plant"
        assert b.cn_name == "电解车间"
        assert len(b.stories) == 1
        s = b.stories[0]
        assert len(s.openings) == 2
        assert isinstance(s.openings[0], Opening)
        assert len(s.fire_compartments) == 2
        fc = s.fire_compartments[0]
        assert fc.name == "Zone-A"
        assert len(fc.openings) == 1
        assert isinstance(fc.openings[0], Opening)
        assert fc.combustibles[0].get("key") == "PREBAKED_ANODE_BLOCK"
        assert fc.specialized_components == [{"key": "POT_TENDING_MACHINE", "count": 2}]
        assert s.roof.thickness == 0.3
        assert s.roof.material == "STEEL"

    def test_multi_building_group(self):
        bg = BuildingGroup(
            buildings=[
                Building(name="A", boundary=[0, 20, 0, 10]),
                Building(name="B", boundary=[30, 25, 0, 15]),
                Building(name="C", boundary=[0, 20, 20, 10]),
            ]
        )
        d = bg.to_dict()
        bg2 = BuildingGroup.from_dict(d)
        assert len(bg2.buildings) == 3
        assert [b.name for b in bg2.buildings] == ["A", "B", "C"]

    def test_empty_building_group_roundtrip(self):
        bg = BuildingGroup()
        d = bg.to_dict()
        bg2 = BuildingGroup.from_dict(d)
        assert bg2.buildings == []
        assert bg2.simulation_time == 1800

    def test_project_format_wrapper_roundtrip(self):
        """Simulate project save: wrap in building_group key, then load."""
        bg = BuildingGroup(
            buildings=[Building(name="proj_b1")],
            simulation_time=100,
        )
        project_data = {"building_group": bg.to_dict()}
        bg2 = BuildingGroup.from_dict(project_data)
        assert len(bg2.buildings) == 1
        assert bg2.buildings[0].name == "proj_b1"
        assert bg2.simulation_time == 100

    def test_old_classes_removed(self):
        """Verify that old classes are no longer importable."""
        import models.building as mb

        assert not hasattr(mb, "BuildingModel")
        assert not hasattr(mb, "WallData")
        assert not hasattr(mb, "OpeningData")
        assert not hasattr(mb, "FloorSlab")
        assert not hasattr(mb, "LayoutMode")
        assert not hasattr(mb, "compute_layout")


# ============================================================
# Combustible Rotation
# ============================================================
class TestCombustibleRotation:
    def test_rotation_field_default(self):
        from models.combustibles import Combustible

        cb = Combustible(preset_key="CONVEYOR_BELT", length=2.0, width=0.5)
        assert cb.rotation == 0

    def test_rotation_field_set(self):
        from models.combustibles import Combustible

        cb = Combustible(preset_key="CONVEYOR_BELT", length=2.0, width=0.5, rotation=90)
        assert cb.rotation == 90

    def test_from_dict_with_rotation(self):
        from models.combustibles import Combustible

        d = {"preset_key": "CONVEYOR_BELT", "length": 2.0, "width": 0.5, "rotation": 90}
        cb = Combustible.from_dict(d)
        assert cb.rotation == 90
        assert cb.length == 0.5  # swapped
        assert cb.width == 2.0  # swapped

    def test_from_dict_without_rotation(self):
        from models.combustibles import Combustible

        d = {"preset_key": "CONVEYOR_BELT", "length": 2.0, "width": 0.5}
        cb = Combustible.from_dict(d)
        assert cb.rotation == 0
        assert cb.length == 2.0
        assert cb.width == 0.5

    def test_to_dict_includes_rotation(self):
        from models.combustibles import Combustible

        cb = Combustible(preset_key="CONVEYOR_BELT", length=2.0, width=0.5, rotation=90)
        d = cb.to_dict()
        assert d["rotation"] == 90


# ============================================================
# Combustible Bounds Check
# ============================================================
class TestCombustibleBoundsCheck:
    def test_exceeds_bounds_warns(self, capsys):
        from models.building import FireCompartment

        fc = FireCompartment.from_dict(
            {
                "name": "TestRoom",
                "boundary": [0, 5, 0, 3],  # 5m x 3m room
                "combustibles": [
                    {
                        "preset_key": "CONVEYOR_BELT",
                        "length": 6.0,
                        "width": 0.5,
                    }  # exceeds X
                ],
            }
        )
        captured = capsys.readouterr()
        assert "exceeds bounds" in captured.out.lower() or "WARNING" in captured.out

    def test_within_bounds_no_warn(self, capsys):
        from models.building import FireCompartment

        fc = FireCompartment.from_dict(
            {
                "name": "TestRoom",
                "boundary": [0, 5, 0, 3],  # 5m x 3m room
                "combustibles": [
                    {"preset_key": "CONVEYOR_BELT", "length": 2.0, "width": 0.5}  # OK
                ],
            }
        )
        captured = capsys.readouterr()
        assert (
            "exceeds bounds" not in captured.out.lower()
            and "WARNING" not in captured.out
        )


class TestBuildingGroupHeatSourceMigration:
    def test_default_heat_source_structure(self):
        bg = BuildingGroup()
        assert bg.heat_source == {
            "azimuth": 0,
            "elevation": 0,
            "net_heat_flux": 1000,
            "duration": 1.36,
        }

    def test_default_simulation_time_1800(self):
        bg = BuildingGroup()
        assert bg.simulation_time == 1800

    def test_default_domain_grid_size_1(self):
        bg = BuildingGroup()
        assert bg.domain == {"padding": 5.0, "grid_size": 1.0}

    def test_from_dict_drops_legacy_fields_and_keeps_flux(self):
        # Legacy keys (enabled/distance/width_ratio/...) are silently dropped.
        # net_heat_flux is stored as-is in MW/m² (model→FDS: multiply by 1000).
        data = {
            "buildings": [],
            "heat_source": {
                "enabled": True,
                "distance": 5.0,
                "azimuth": 90,
                "elevation": 30,
                "net_heat_flux": 3.0,
                "duration": 2.0,
                "width_ratio": 1.5,
                "height_ratio": 1.0,
            },
        }
        bg = BuildingGroup.from_dict(data)
        assert bg.heat_source["net_heat_flux"] == 3.0
        assert bg.heat_source["azimuth"] == 90
        assert bg.heat_source["elevation"] == 30
        assert bg.heat_source["duration"] == 2.0
        assert "enabled" not in bg.heat_source
        assert "distance" not in bg.heat_source
        assert "width_ratio" not in bg.heat_source
        assert "height_ratio" not in bg.heat_source

    def test_from_dict_keeps_small_mw_value(self):
        data = {
            "buildings": [],
            "heat_source": {
                "net_heat_flux": 0.05,
                "azimuth": 0,
                "elevation": 0,
                "duration": 1.36,
            },
        }
        bg = BuildingGroup.from_dict(data)
        assert bg.heat_source["net_heat_flux"] == 0.05

    def test_from_dict_fills_missing_heat_source_fields(self):
        data = {"buildings": []}
        bg = BuildingGroup.from_dict(data)
        assert bg.heat_source == {
            "azimuth": 0,
            "elevation": 0,
            "net_heat_flux": 1000,
            "duration": 1.36,
        }
