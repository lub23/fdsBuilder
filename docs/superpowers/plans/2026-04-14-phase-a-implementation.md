# Phase A: Data Model Refactoring - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the fdsBuilder data model from legacy wall-based structures to a unified boundary-driven schema with string wall IDs, absolute opening coordinates, fire compartment encapsulation, and a parameter engine for equivalent models.

**Architecture:** Schema-First approach. Define target JSON schema, write migration scripts to convert all 11 facility JSON files + building_config.json, then rewrite Python model classes to directly mirror JSON, followed by FDS generator and UI adaptation. Shared geometry logic extracted to `models/geometry.py`.

**Tech Stack:** Python 3.13, PySide6, PyVista, dataclasses, json

**Design Spec:** `docs/superpowers/specs/2026-04-14-phase-a-data-model-refactoring-design.md`

---

## File Structure

### New files
- `models/geometry.py` - Shared geometry utilities (coplanar detection, wall length, coordinate transforms)
- `models/parameter_engine.py` - ParameterEngine for equivalent model template expansion
- `tools/migrate_schema.py` - One-time migration script for all JSON files
- `tests/test_models.py` - Tests for new model classes
- `tests/test_geometry.py` - Tests for geometry utilities
- `tests/test_parameter_engine.py` - Tests for ParameterEngine
- `tests/test_migration.py` - Tests for migration correctness

### Modified files
- `models/building.py` - Complete rewrite: Opening, Roof, FireCompartment, Story, Building, BuildingGroup
- `models/facility.py` - Rewrite FacilityManager to use new schema
- `models/combustibles.py` - Adapt CombustibleManager to work with FireCompartment.boundary
- `models/__init__.py` - Update exports
- `generators/fds_generator.py` - Adapt to new model structure
- `ui/facility_panel.py` - Equivalent/specialized visual distinction, read-only mode
- `ui/param_panel.py` - Remove walls table, adapt openings, add fire compartment editor
- `ui/viewer_3d.py` - Render from boundary-based model
- `ui/dialogs.py` - Adapt OpeningDialog, remove WallDialog/BatchWallDialog, rename FloorSlabHoleDialog
- `ui/mainwindow.py` - Wire new model types
- `main.py` - Update imports
- `data/facilities/*.json` - All 11 files migrated to new schema
- `building_config.json` - Migrated to new schema

### Deleted classes/code
- `BuildingModel` class (replaced by `BuildingGroup`)
- `WallData` dataclass
- `OpeningData` dataclass
- `FloorSlab` dataclass (replaced by `Roof`)
- `LayoutMode` enum and `compute_layout` function
- `WallDialog`, `BatchWallDialog` in dialogs.py

---

## Task 1: New Model Classes (`models/building.py`)

**Files:**
- Rewrite: `models/building.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write tests for Opening, Roof, FireCompartment**

```python
# tests/test_models.py
import pytest
from models.building import Opening, Roof, FireCompartment, Story, Building, BuildingGroup


class TestOpening:
    def test_from_dict(self):
        d = {"wall": "x_max", "type": "door", "boundary": [10.0, 5.0, 0, 4.0]}
        o = Opening.from_dict(d)
        assert o.wall == "x_max"
        assert o.type == "door"
        assert o.boundary == [10.0, 5.0, 0, 4.0]

    def test_to_dict(self):
        o = Opening(wall="y_min", type="window", boundary=[2.0, 1.5, 1.0, 1.2])
        d = o.to_dict()
        assert d == {"wall": "y_min", "type": "window", "boundary": [2.0, 1.5, 1.0, 1.2]}


class TestRoof:
    def test_defaults(self):
        r = Roof()
        assert r.thickness == 0.2
        assert r.material == "CONCRETE"
        assert r.openings == []

    def test_from_dict_with_openings(self):
        d = {"thickness": 0.3, "material": "STEEL", "openings": [{"boundary": [1, 2, 3, 4]}]}
        r = Roof.from_dict(d)
        assert r.thickness == 0.3
        assert len(r.openings) == 1
        assert r.openings[0]["boundary"] == [1, 2, 3, 4]


class TestFireCompartment:
    def test_from_dict_full(self):
        d = {
            "name": "Zone A",
            "boundary": [0, 88, 0, 75],
            "firewall_thickness": 0.3,
            "firewall_material": "CONCRETE",
            "openings": [{"wall": "x_max", "type": "door", "boundary": [10.0, 5.0, 0, 4.0]}],
            "combustibles": [{"key": "WOOD_DESK", "count": 3}],
            "specialized_components": [{"key": "BOILER", "count": 1}],
        }
        fc = FireCompartment.from_dict(d)
        assert fc.name == "Zone A"
        assert fc.boundary == [0, 88, 0, 75]
        assert len(fc.openings) == 1
        assert isinstance(fc.openings[0], Opening)
        assert fc.combustibles == [{"key": "WOOD_DESK", "count": 3}]

    def test_to_dict_roundtrip(self):
        fc = FireCompartment(
            name="Zone B", boundary=[88, 176, 0, 75],
            firewall_thickness=0.3, firewall_material="CONCRETE",
            openings=[Opening(wall="y_min", type="door", boundary=[5, 3, 0, 2.5])],
            combustibles=[], specialized_components=[],
        )
        d = fc.to_dict()
        fc2 = FireCompartment.from_dict(d)
        assert fc2.boundary == fc.boundary
        assert len(fc2.openings) == 1


class TestStory:
    def test_z_top(self):
        s = Story(name="1F", height=4.0)
        s.z_bottom = 0.0
        assert s.z_top == 4.0

    def test_from_dict_with_compartments(self):
        d = {
            "name": "1F",
            "height": 10.0,
            "openings": [],
            "fire_compartments": [
                {"name": "Z1", "boundary": [0, 100, 0, 50], "firewall_thickness": 0.3,
                 "firewall_material": "CONCRETE", "openings": [], "combustibles": [],
                 "specialized_components": []}
            ],
            "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
        }
        s = Story.from_dict(d)
        assert len(s.fire_compartments) == 1
        assert isinstance(s.fire_compartments[0], FireCompartment)
        assert isinstance(s.roof, Roof)


class TestBuilding:
    def test_properties(self):
        b = Building(boundary=[10, 176, 20, 150])
        assert b.length == 176
        assert b.width == 150
        assert b.offset_x == 10
        assert b.offset_y == 20

    def test_update_z_offsets(self):
        b = Building(boundary=[0, 100, 0, 50], height=20)
        b.stories = [
            Story(name="1F", height=10.0),
            Story(name="2F", height=10.0),
        ]
        b.update_z_offsets()
        assert b.stories[0].z_bottom == 0.0
        assert b.stories[1].z_bottom == 10.0
        assert b.stories[1].z_top == 20.0

    def test_from_dict_roundtrip(self):
        d = {
            "name": "Test",
            "cn_name": "测试",
            "boundary": [0, 100, 0, 50],
            "wall_thickness": 0.24,
            "height": 10,
            "boundary_polygons": None,
            "stories": [{
                "name": "1F", "height": 10.0, "openings": [],
                "fire_compartments": [{
                    "name": "Z1", "boundary": [0, 100, 0, 50],
                    "firewall_thickness": 0.0, "firewall_material": "CONCRETE",
                    "openings": [], "combustibles": [], "specialized_components": [],
                }],
                "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
            }],
        }
        b = Building.from_dict(d)
        assert b.length == 100
        assert b.stories[0].fire_compartments[0].boundary == [0, 100, 0, 50]
        d2 = b.to_dict()
        assert d2["boundary"] == [0, 100, 0, 50]


class TestBuildingGroup:
    def test_from_dict_building_group_format(self):
        d = {
            "building_group": {
                "buildings": [{
                    "name": "B1", "cn_name": "建筑1",
                    "boundary": [0, 100, 0, 50], "wall_thickness": 0.24, "height": 10,
                    "boundary_polygons": None,
                    "stories": [{
                        "name": "1F", "height": 10.0, "openings": [],
                        "fire_compartments": [{
                            "name": "Z1", "boundary": [0, 100, 0, 50],
                            "firewall_thickness": 0.0, "firewall_material": "CONCRETE",
                            "openings": [], "combustibles": [], "specialized_components": [],
                        }],
                        "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
                    }],
                }],
                "heat_source": {},
                "simulation_time": 300,
                "domain": {"padding": 5.0, "mesh_cells": [80, 60, 40]},
                "output": {"slices": True, "devices": True},
            }
        }
        bg = BuildingGroup.from_dict(d)
        assert len(bg.buildings) == 1
        assert bg.buildings[0].length == 100
        assert bg.simulation_time == 300

    def test_from_dict_facility_format(self):
        """Facility JSON (no building_group wrapper) should also load"""
        d = {
            "type": "specialized",
            "cn_name": "Test",
            "buildings": [{
                "name": "B1", "cn_name": "测试",
                "boundary": [0, 176, 0, 150], "wall_thickness": 0.24, "height": 10,
                "boundary_polygons": None,
                "stories": [{
                    "name": "1F", "height": 10.0, "openings": [],
                    "fire_compartments": [{
                        "name": "Z1", "boundary": [0, 176, 0, 150],
                        "firewall_thickness": 0.0, "firewall_material": "CONCRETE",
                        "openings": [], "combustibles": [], "specialized_components": [],
                    }],
                    "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
                }],
            }],
        }
        bg = BuildingGroup.from_dict(d)
        assert len(bg.buildings) == 1
        assert bg.buildings[0].name == "B1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/code/fdsBuilder && python -m pytest tests/test_models.py -v`
Expected: FAIL (new classes not yet defined)

- [ ] **Step 3: Implement new model classes**

Rewrite `models/building.py` with the new dataclasses: `Opening`, `Roof`, `FireCompartment`, `Story`, `Building`, `BuildingGroup`. Remove `BuildingModel`, `WallData`, `OpeningData`, `FloorSlab`, `LayoutMode`, `compute_layout`. Each class has `to_dict()` and `from_dict()` that directly mirror the JSON schema. `BuildingGroup.from_dict()` handles both `{"building_group": {...}}` format and facility `{"type": ..., "buildings": [...]}` format.

Key implementation details:
- `Building.boundary = [offset_x, length, offset_y, width]`
- `Building.length` / `width` / `offset_x` / `offset_y` are `@property` reading from `boundary`
- `FireCompartment.boundary = [x_min, x_max, y_min, y_max]`
- `Opening.boundary = [w_offset, width, h_offset, height]`
- `Roof.openings[].boundary = [x, length, y, width]`
- `Story.z_bottom` is a regular float field (not a property with hidden attr)
- `Building.get_exterior_walls(story_index)` generates 4 wall OBST boxes from boundary + wall_thickness

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:/code/fdsBuilder && python -m pytest tests/test_models.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add models/building.py tests/test_models.py
git commit -m "refactor: rewrite model classes with boundary-based schema"
```

---

## Task 2: Geometry Utilities (`models/geometry.py`)

**Files:**
- Create: `models/geometry.py`
- Test: `tests/test_geometry.py`

- [ ] **Step 1: Write tests for geometry utilities**

```python
# tests/test_geometry.py
import pytest
from models.building import Opening, FireCompartment, Story, Building
from models.geometry import (
    wall_length_for_fc,
    wall_length_for_building,
    detect_coplanar_openings,
    is_coplanar,
    fc_wall_start_offset,
    resolve_negative_offset,
    opening_to_world_coords,
)


class TestWallLength:
    def test_fc_x_wall(self):
        """x_min/x_max walls run along Y, length = y_max - y_min"""
        assert wall_length_for_fc([0, 88, 0, 75], "x_min") == 75
        assert wall_length_for_fc([0, 88, 0, 75], "x_max") == 75

    def test_fc_y_wall(self):
        """y_min/y_max walls run along X, length = x_max - x_min"""
        assert wall_length_for_fc([0, 88, 0, 75], "y_min") == 88
        assert wall_length_for_fc([0, 88, 0, 75], "y_max") == 88

    def test_building_wall(self):
        """Building walls: y walls along length, x walls along width"""
        assert wall_length_for_building([0, 176, 0, 150], "y_min") == 176
        assert wall_length_for_building([0, 176, 0, 150], "x_min") == 150


class TestCoplanarDetection:
    def test_fc_at_building_edge(self):
        building = Building(boundary=[0, 176, 0, 150], height=10)
        fc = FireCompartment(
            name="Z1", boundary=[0, 88, 0, 75],
            openings=[Opening(wall="x_min", type="door", boundary=[10, 5, 0, 4])],
        )
        story = Story(name="1F", height=10, fire_compartments=[fc])
        coplanar = detect_coplanar_openings(building, story)
        # x_min of FC (0) == 0 of building -> coplanar
        assert len(coplanar) == 1
        assert coplanar[0].wall == "x_min"

    def test_fc_not_at_edge(self):
        building = Building(boundary=[0, 176, 0, 150], height=10)
        fc = FireCompartment(
            name="Z1", boundary=[88, 176, 0, 75],
            openings=[Opening(wall="x_min", type="door", boundary=[10, 5, 0, 4])],
        )
        story = Story(name="1F", height=10, fire_compartments=[fc])
        coplanar = detect_coplanar_openings(building, story)
        # x_min of FC (88) != 0 of building -> not coplanar
        assert len(coplanar) == 0

    def test_coplanar_w_offset_shift(self):
        """FC not at origin: w_offset must be shifted by FC wall start"""
        building = Building(boundary=[0, 176, 0, 150], height=10)
        fc = FireCompartment(
            name="Z2", boundary=[88, 176, 0, 75],
            openings=[Opening(wall="y_min", type="door", boundary=[10, 5, 0, 4])],
        )
        story = Story(name="1F", height=10, fire_compartments=[fc])
        coplanar = detect_coplanar_openings(building, story)
        # y_min of FC (0) == 0 of building -> coplanar
        # FC y_min wall spans x=[88, 176], so w_offset shifts by 88
        assert len(coplanar) == 1
        assert coplanar[0].boundary[0] == 10 + 88  # shifted


class TestResolveNegativeOffset:
    def test_positive_unchanged(self):
        assert resolve_negative_offset(5.0, 3.0, 100.0) == 5.0

    def test_negative_from_end(self):
        # -2.0 means 2m from end: wall_len + (-2) - width = 100 - 2 - 3 = 95
        assert resolve_negative_offset(-2.0, 3.0, 100.0) == 95.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/code/fdsBuilder && python -m pytest tests/test_geometry.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement geometry utilities**

```python
# models/geometry.py
"""Shared geometry utilities for Viewer3D and FDSGenerator."""

from __future__ import annotations
from models.building import Opening, FireCompartment, Story, Building


def wall_length_for_fc(fc_boundary: list[float], wall_id: str) -> float:
    """Return the length of a fire compartment wall segment."""
    x_min, x_max, y_min, y_max = fc_boundary
    if wall_id in ("x_min", "x_max"):
        return y_max - y_min
    return x_max - x_min


def wall_length_for_building(building_boundary: list[float], wall_id: str) -> float:
    """Return the length of a building exterior wall."""
    _ox, length, _oy, width = building_boundary
    if wall_id in ("y_min", "y_max"):
        return length
    return width


def is_coplanar(fc_boundary: list[float], building_length: float,
                building_width: float, wall_id: str, tol: float = 1e-6) -> bool:
    """Check if a fire compartment wall coincides with the building exterior."""
    x_min, x_max, y_min, y_max = fc_boundary
    checks = {"x_min": (x_min, 0), "x_max": (x_max, building_length),
              "y_min": (y_min, 0), "y_max": (y_max, building_width)}
    fc_val, bld_val = checks[wall_id]
    return abs(fc_val - bld_val) < tol


def fc_wall_start_offset(fc_boundary: list[float], wall_id: str) -> float:
    """Return the offset of FC wall start relative to the building wall start."""
    x_min, _x_max, y_min, _y_max = fc_boundary
    if wall_id in ("y_min", "y_max"):
        return x_min  # y-direction walls span along X
    return y_min  # x-direction walls span along Y


def detect_coplanar_openings(building: Building, story: Story) -> list[Opening]:
    """Detect FC openings on walls coplanar with building exterior, with w_offset translation."""
    L, W = building.length, building.width
    coplanar = []
    for fc in story.fire_compartments:
        for wall_id in ("x_min", "x_max", "y_min", "y_max"):
            if not is_coplanar(fc.boundary, L, W, wall_id):
                continue
            shift = fc_wall_start_offset(fc.boundary, wall_id)
            for opening in fc.openings:
                if opening.wall == wall_id:
                    coplanar.append(Opening(
                        wall=opening.wall,
                        type=opening.type,
                        boundary=[
                            opening.boundary[0] + shift,
                            opening.boundary[1],
                            opening.boundary[2],
                            opening.boundary[3],
                        ],
                    ))
    return coplanar


def resolve_negative_offset(w_offset: float, width: float, wall_length: float) -> float:
    """Convert negative w_offset (from wall end) to positive (from wall start)."""
    if w_offset >= 0:
        return w_offset
    return wall_length + w_offset - width


def opening_to_world_coords(
    opening: Opening, building: Building, story: Story,
    is_exterior: bool = True
) -> tuple[float, float, float, float, float, float]:
    """Convert an opening to world-space 6-tuple [x1, x2, y1, y2, z1, z2].

    For exterior walls, the opening is on the building boundary.
    Returns the HOLE box coordinates in world space.
    """
    ox, L, oy, W = building.boundary
    w_off, w, h_off, h = opening.boundary
    z0 = story.z_bottom
    wall_id = opening.wall

    # Resolve negative offset
    if wall_id in ("y_min", "y_max"):
        wl = L
    else:
        wl = W
    w_off = resolve_negative_offset(w_off, w, wl)

    if wall_id == "y_min":
        return (ox + w_off, ox + w_off + w, oy, oy, z0 + h_off, z0 + h_off + h)
    elif wall_id == "y_max":
        return (ox + w_off, ox + w_off + w, oy + W, oy + W, z0 + h_off, z0 + h_off + h)
    elif wall_id == "x_min":
        return (ox, ox, oy + w_off, oy + w_off + w, z0 + h_off, z0 + h_off + h)
    else:  # x_max
        return (ox + L, ox + L, oy + w_off, oy + w_off + w, z0 + h_off, z0 + h_off + h)
```

- [ ] **Step 4: Run tests**

Run: `cd D:/code/fdsBuilder && python -m pytest tests/test_geometry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add models/geometry.py tests/test_geometry.py
git commit -m "feat: add shared geometry utilities for coplanar detection and coordinate transforms"
```

---

## Task 3: ParameterEngine (`models/parameter_engine.py`)

**Files:**
- Create: `models/parameter_engine.py`
- Test: `tests/test_parameter_engine.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_parameter_engine.py
import pytest
from models.parameter_engine import ParameterEngine
from models.building import Building


class TestResolveRange:
    def test_min_max(self):
        assert ParameterEngine.resolve_range([50, 120]) == 85.0

    def test_min_max_default(self):
        assert ParameterEngine.resolve_range([2, 4, 3]) == 3


class TestGenerate:
    def test_basic_generation(self):
        template = {
            "name": "Test Plant",
            "cn_name": "测试工厂",
            "length_range": [50, 120],
            "width_range": [15, 50],
            "height_range": [8, 12],
            "stories_range": [1, 3],
            "stories_template": [{
                "name": "1F",
                "height": 10.0,
                "doors": {"width": [4, 4], "height": [4, 4], "count": [2, 2]},
                "windows": {},
                "fire_compartment_ratios": [{
                    "name": "Zone A",
                    "boundary_ratio": [0.0, 0.5, 0.0, 1.0],
                    "firewall_thickness": 0.3,
                    "firewall_material": "CONCRETE",
                    "opening_templates": [{
                        "wall": "x_max",
                        "type": "door",
                        "w_offset_ratio": 0.3,
                        "width_ratio": 0.2,
                        "h_offset": 0,
                        "height": 4.0,
                    }],
                    "combustibles": [{"key": "WOOD_DESK", "count": 3}],
                    "specialized_components": [],
                }],
                "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
            }],
            "stories": [],
        }
        params = {"length": 100, "width": 40, "height": 10, "stories": 2}
        building = ParameterEngine.generate(template, params)

        assert isinstance(building, Building)
        assert building.length == 100
        assert building.width == 40
        assert len(building.stories) == 2

        # Check fire compartment was expanded from ratio
        fc = building.stories[0].fire_compartments[0]
        assert fc.boundary == [0.0, 50.0, 0.0, 40.0]  # 0.5 * 100, 1.0 * 40

        # Check opening was expanded from ratio
        assert len(fc.openings) == 1
        opening = fc.openings[0]
        assert opening.wall == "x_max"
        # FC x_max wall length = y_max - y_min = 40
        # w_offset = 0.3 * 40 = 12, width = 0.2 * 40 = 8
        assert abs(opening.boundary[0] - 12.0) < 0.01
        assert abs(opening.boundary[1] - 8.0) < 0.01

    def test_exterior_doors_distributed(self):
        template = {
            "name": "T", "cn_name": "T",
            "length_range": [100, 100], "width_range": [50, 50],
            "height_range": [10, 10], "stories_range": [1, 1],
            "stories_template": [{
                "name": "1F", "height": 10.0,
                "doors": {"width": [4, 4], "height": [4, 4], "count": [2, 2]},
                "windows": {},
                "fire_compartment_ratios": [],
                "roof": {"thickness": 0.2, "material": "CONCRETE", "openings": []},
            }],
            "stories": [],
        }
        params = {"length": 100, "width": 50, "height": 10, "stories": 1}
        building = ParameterEngine.generate(template, params)
        # Doors distributed on y_min and y_max walls
        ext_openings = building.stories[0].openings
        assert len(ext_openings) == 4  # 2 doors on y_min + 2 doors on y_max
        walls = {o.wall for o in ext_openings}
        assert "y_min" in walls
        assert "y_max" in walls
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/code/fdsBuilder && python -m pytest tests/test_parameter_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ParameterEngine**

Implement `models/parameter_engine.py` with `resolve_range()`, `generate()`, `_expand_story_template()`, `_wall_length()`, `_distribute_exterior_openings()` exactly as specified in design spec Section 5.2.

- [ ] **Step 4: Run tests**

Run: `cd D:/code/fdsBuilder && python -m pytest tests/test_parameter_engine.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add models/parameter_engine.py tests/test_parameter_engine.py
git commit -m "feat: add ParameterEngine for equivalent model template expansion"
```

---

## Task 4: Migration Script (`tools/migrate_schema.py`)

**Files:**
- Create: `tools/migrate_schema.py`
- Test: `tests/test_migration.py`

- [ ] **Step 1: Write migration tests**

```python
# tests/test_migration.py
import pytest
import json
import sys
sys.path.insert(0, ".")
from tools.migrate_schema import (
    migrate_specialized,
    migrate_equivalent,
    migrate_building_config,
    position_to_w_offset,
    wall_index_to_wall_str,
)


class TestPositionConversion:
    def test_center_position(self):
        # position=0.5 on wall_length=100, width=10 -> center=50, w_offset=45
        assert position_to_w_offset(0.5, 10, 100) == 45.0

    def test_start_position(self):
        # position=0.05 on wall_length=100, width=10 -> center=5, w_offset=0
        assert position_to_w_offset(0.05, 10, 100) == 0.0

    def test_wall_index_mapping(self):
        assert wall_index_to_wall_str(0) == "y_min"
        assert wall_index_to_wall_str(1) == "y_max"
        assert wall_index_to_wall_str(2) == "x_min"
        assert wall_index_to_wall_str(3) == "x_max"


class TestMigrateSpecialized:
    def test_basic_structure(self):
        old = {
            "cn_name": "Test",
            "fire_separation": 15.0,
            "sub_types": {
                "Plant_A": {
                    "cn_name": "工厂A",
                    "type": "specialized",
                    "rotation": 0,
                    "building": {
                        "length": {"value": 100, "unit": "m"},
                        "width": {"value": 50, "unit": "m"},
                        "height": {"value": 10, "unit": "m"},
                        "stories": {"value": 1, "unit": ""},
                    },
                    "doors": {},
                    "windows": {},
                    "wall_thickness": 0.24,
                    "fire_compartments": [{
                        "name": "Zone1",
                        "x_ratio": [0, 1],
                        "y_ratio": [0, 1],
                        "wall_thickness": 0.3,
                        "wall_material": "CONCRETE",
                        "openings": [
                            {"wall": "y_min", "type": "door", "position": 0.5,
                             "width": 5, "height": 4, "z_bottom": 0}
                        ],
                        "combustibles": [{"key": "WOOD_DESK", "count": 3}],
                        "specialized_components": [],
                    }],
                }
            }
        }
        new = migrate_specialized(old)
        assert new["type"] == "specialized"
        assert "fire_separation" not in new
        assert "sub_types" not in new
        assert len(new["buildings"]) == 1
        b = new["buildings"][0]
        assert b["name"] == "Plant_A"
        assert b["boundary"] == [0, 100, 0, 50]
        assert "rotation" not in b
        fc = b["stories"][0]["fire_compartments"][0]
        assert fc["boundary"] == [0, 100, 0, 50]
        opening = fc["openings"][0]
        assert opening["wall"] == "y_min"
        assert "boundary" in opening
        assert "position" not in opening
        # position=0.5 on wall_length=100 (y_min wall, x direction), width=5
        # w_offset = 0.5 * 100 - 5/2 = 47.5
        assert abs(opening["boundary"][0] - 47.5) < 0.01


class TestMigrateEquivalent:
    def test_basic_structure(self):
        old = {
            "cn_name": "航空航天",
            "fire_separation": 20.0,
            "sub_types": {
                "Plant_X": {
                    "cn_name": "工厂X",
                    "building": {
                        "length": {"min": 50, "max": 120, "median": -1, "mean": -1, "unit": "m"},
                        "width": {"min": 15, "max": 50, "median": -1, "mean": -1, "unit": "m"},
                        "height": {"min": 8, "max": 12, "median": -1, "mean": -1, "unit": "m"},
                        "stories": {"min": 2, "max": 4, "median": -1, "mean": -1, "unit": ""},
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
                    "fire_compartments": [],
                }
            }
        }
        new = migrate_equivalent(old)
        assert new["type"] == "equivalent"
        assert "fire_separation" not in new
        b = new["buildings"][0]
        assert b["length_range"] == [50, 120]
        assert b["width_range"] == [15, 50]
        assert b["stories_range"] == [2, 4]
        assert "stories_template" in b
        assert b["stories"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/code/fdsBuilder && python -m pytest tests/test_migration.py -v`
Expected: FAIL

- [ ] **Step 3: Implement migration script**

Implement `tools/migrate_schema.py` with:
- `resolve_value(p)`: Extract value from `{"value": X}` or `{"min": X, "max": Y}` dicts
- `resolve_range_array(p)`: Convert `{"min": X, "max": Y, "median": Z}` to `[X, Y]` or `[X, Y, Z]`
- `position_to_w_offset(position, width, wall_length)`: Convert 0-1 center ratio to absolute left-edge offset
- `wall_index_to_wall_str(idx)`: Map 0→y_min, 1→y_max, 2→x_min, 3→x_max
- `migrate_specialized(old_data)`: Full specialized JSON conversion
- `migrate_equivalent(old_data)`: Full equivalent JSON conversion (including ratio derivation)
- `migrate_building_config(old_data)`: BuildingGroup config conversion
- `main()`: CLI entry point that processes all files with backup

Key details for `migrate_specialized`:
1. For buildings with `{"value": V}` dimensions, use `V` directly
2. For buildings with `{"min": X, "max": Y}` where min==max, use the value directly
3. Fire compartment boundaries: convert from `x_ratio * building_length` to absolute `[x_min, x_max, y_min, y_max]`
4. Opening position conversion uses the FC's wall length (not building wall length)
5. Wrap everything in a story with a default roof
6. Move combustibles and specialized_components inside fire_compartments

Key details for `migrate_building_config`:
1. `floor_slab` of story N → `roof` of story N-1
2. Building-level `roof` → last story's `roof`
3. Generate a default fire_compartment covering the entire story
4. Move `combustibles` into the default fire_compartment

- [ ] **Step 4: Run tests**

Run: `cd D:/code/fdsBuilder && python -m pytest tests/test_migration.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tools/migrate_schema.py tests/test_migration.py
git commit -m "feat: add schema migration script for JSON data files"
```

---

## Task 5: Run Migration on All Data Files

**Files:**
- Modify: `data/facilities/*.json` (all 11 files)
- Modify: `building_config.json`

- [ ] **Step 1: Run migration script**

Run: `cd D:/code/fdsBuilder && python tools/migrate_schema.py`
Expected: Script backs up originals to `data/facilities/_backup/`, converts all 11 facility JSON files and `building_config.json`, prints diff report.

- [ ] **Step 2: Spot-check migrated files**

Manually verify `data/facilities/alcoa.json`:
- Root has `"type": "specialized"`, no `"fire_separation"`, no `"sub_types"`
- Has `"buildings": [...]` array
- Each building has `"boundary": [ox, L, oy, W]`
- All openings use `"boundary": [w_off, w, h_off, h]` format
- No `"position"`, `"wall_index"`, `"rotation"` fields remain

Verify `data/facilities/aerospace.json`:
- Root has `"type": "equivalent"`
- Buildings have `"length_range"`, `"width_range"`, etc.
- Has `"stories_template"` with ratio-based compartments
- `"stories": []`

- [ ] **Step 3: Run model load test**

```bash
cd D:/code/fdsBuilder && python -c "
from models.building import BuildingGroup, Building
import json

# Test specialized load
with open('data/facilities/alcoa.json') as f:
    data = json.load(f)
for b_data in data['buildings']:
    b = Building.from_dict(b_data)
    print(f'Loaded: {b.name}, boundary={b.boundary}, stories={len(b.stories)}')
    for s in b.stories:
        for fc in s.fire_compartments:
            print(f'  FC: {fc.name}, boundary={fc.boundary}, openings={len(fc.openings)}')

# Test building_config load
with open('building_config.json') as f:
    data = json.load(f)
bg = BuildingGroup.from_dict(data)
print(f'BuildingGroup: {len(bg.buildings)} buildings')
"
```

- [ ] **Step 4: Commit migrated data**

```bash
git add data/facilities/ building_config.json
git commit -m "data: migrate all JSON files to new boundary-based schema"
```

---

## Task 6: Rewrite FacilityManager (`models/facility.py`)

**Files:**
- Rewrite: `models/facility.py`

- [ ] **Step 1: Rewrite FacilityManager**

Replace the entire `FacilityManager` class with the simplified version from spec Section 5.1:
- `__init__`: load all JSON files from `data/facilities/`
- `get_type(facility_name)`: return `data["type"]`
- `list_buildings(facility_name)`: return building names
- `load_specialized(facility_name, building_name)`: `Building.from_dict()` directly
- `load_equivalent(facility_name, building_name, params)`: delegate to `ParameterEngine.generate()`
- `_find_building(facility_name, building_name)`: lookup helper
- `default_params(facility_name, building_name)`: return ranges for UI spinboxes (equivalent models only)

Delete all old methods: `_rv`, `_rng`, `default_params` (old version), `generate_model`, `generate_group`, `_place_openings`, `_add_to_wall`, `_resolve_overlaps`, `_apply_preset_compartments`, `_find_partition_wall`, etc.

- [ ] **Step 2: Verify import works**

Run: `cd D:/code/fdsBuilder && python -c "from models.facility import FacilityManager; fm = FacilityManager(); print(f'Loaded {len(fm.facilities)} facilities'); print([(k, fm.get_type(k)) for k in fm.facilities])"`

Expected: Lists all 11 facilities with correct types.

- [ ] **Step 3: Commit**

```bash
git add models/facility.py
git commit -m "refactor: rewrite FacilityManager for new schema"
```

---

## Task 7: FDS Generator Adaptation (`generators/fds_generator.py`)

**Files:**
- Rewrite: `generators/fds_generator.py`

- [ ] **Step 1: Read current FDS generator**

Read and understand the current `generators/fds_generator.py` structure before modifying.

- [ ] **Step 2: Rewrite generator**

Adapt `FDSGenerator` to work with `BuildingGroup` (not `BuildingModel`):
- `generate(building_group)` main entry
- `_generate_exterior_walls(building, story)`: auto-generate 4 walls from `building.boundary`, use `&OBST` + `&HOLE` pattern
- `_detect_coplanar_openings()`: call `geometry.detect_coplanar_openings()`
- `_generate_wall_with_holes(wall_id, obst_bounds, openings, wall_thick)`: emit OBST for full wall, then HOLE for each opening with ±5cm normal redundancy
- `_generate_firewalls(building, story)`: emit OBST for non-coplanar FC boundaries
- `_generate_roof(story, building)`: emit OBST + HOLE from `story.roof`
- Combustibles: iterate `fc.combustibles`, use `CombustibleManager` to generate positions within `fc.boundary`
- Coordinate system: world coords from `building.boundary = [ox, L, oy, W]`

Key changes from old generator:
- No more `story.walls` iteration — walls generated from boundary
- No more `wall_index` integer lookups — use string `wall` IDs
- No more `position * wall_length` center calculation — use `boundary[0]` directly as w_offset
- HOLE thickness redundancy: `REDUNDANCY = 0.05`, expand ±5cm in wall normal direction
- `resolve_negative_offset()` for negative `w_offset`

- [ ] **Step 3: Test FDS output**

Run: `cd D:/code/fdsBuilder && python -c "
from models.building import BuildingGroup
from generators.fds_generator import FDSGenerator
import json

with open('building_config.json') as f:
    data = json.load(f)
bg = BuildingGroup.from_dict(data)
gen = FDSGenerator()
fds_text = gen.generate(bg)
print(fds_text[:2000])
print('...')
print(f'Total lines: {len(fds_text.splitlines())}')
# Check no syntax errors in FDS output
assert '&HEAD' in fds_text
assert '&TAIL' in fds_text
assert '&OBST' in fds_text
print('FDS output OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add generators/fds_generator.py
git commit -m "refactor: adapt FDS generator for boundary-based model"
```

---

## Task 8: Update UI - FacilityPanel (`ui/facility_panel.py`)

**Files:**
- Rewrite: `ui/facility_panel.py`

- [ ] **Step 1: Rewrite FacilityPanel**

Key changes:
- Tree widget: iterate `fm.facilities` → `data["buildings"]` (not `sub_types`)
- Category labels show `[等效]` or `[特异]` with color-coded icons
- On selecting a building:
  - Equivalent: show editable spinboxes with min/max from `*_range` fields
  - Specialized: show read-only labels from `building.boundary` values
- "Generate" button:
  - Specialized: `fm.load_specialized()` → emit `building_added` signal
  - Equivalent: collect params from spinboxes → `fm.load_equivalent()` → emit `building_added`
- Scene table: show `building.name`, `boundary` values, allow editing `boundary[0]` and `boundary[2]` (offsets)
- Remove references to `BuildingModel`, use `BuildingGroup` and `Building` directly

- [ ] **Step 2: Smoke test UI launch**

Run: `cd D:/code/fdsBuilder && python main.py`
Expected: App launches, facility tree shows categories with [等效]/[特异] labels, clicking a specialized building shows read-only params.

- [ ] **Step 3: Commit**

```bash
git add ui/facility_panel.py
git commit -m "refactor: update FacilityPanel for new model types"
```

---

## Task 9: Update UI - ParameterPanel + Dialogs

**Files:**
- Modify: `ui/param_panel.py`
- Modify: `ui/dialogs.py`

- [ ] **Step 1: Update ParameterPanel**

Key changes:
- Remove walls table (`_walls_table` and related methods)
- Openings table: replace `位置(0-1)` column with `w_offset(m)`, replace `所属墙(index)` with `所属墙(str)` dropdown, replace `z_bottom` with `h_offset`
- Add fire compartment section: combo box to select current FC, display FC boundary, list FC openings
- Add read-only mode flag `self._readonly`: when True, disable all editing controls
- `sync_ui_from_model()`: read from `BuildingGroup` structure (not `BuildingModel`)
- `sync_model_from_ui()`: write back to `BuildingGroup`
- Remove `_current_story().walls` references
- Combustible management: scope to selected `FireCompartment`
- Replace floor_slab section with roof openings section

- [ ] **Step 2: Update Dialogs**

- `OpeningDialog`: change `position` SpinBox (0-1 range) to `w_offset` SpinBox (meters); change `wall_index` ComboBox (ints) to `wall` ComboBox (strings: x_min, x_max, y_min, y_max); change `z_bottom` label to `h_offset`
- Delete `WallDialog` class
- Delete `BatchWallDialog` class
- Rename `FloorSlabHoleDialog` → `RoofOpeningDialog`, change boundary format to `[x, length, y, width]`
- `BatchOpeningDialog`: adapt to new boundary format
- `CombustibleDialog`: add fire_compartment selector ComboBox, generate combustibles within selected FC boundary

- [ ] **Step 3: Smoke test**

Run app, open a building config, verify:
- No walls table visible
- Opening table shows w_offset and wall string columns
- Fire compartment selector appears
- Editing an opening produces correct boundary values

- [ ] **Step 4: Commit**

```bash
git add ui/param_panel.py ui/dialogs.py
git commit -m "refactor: update ParameterPanel and dialogs for new schema"
```

---

## Task 10: Update UI - Viewer3D (`ui/viewer_3d.py`)

**Files:**
- Modify: `ui/viewer_3d.py`

- [ ] **Step 1: Rewrite update_model**

Replace `update_model(model: BuildingModel)` with `update_model(model: BuildingGroup)`:

- Iterate `model.buildings` (not `model.building_group.buildings`)
- For each building/story:
  1. Auto-generate 4 exterior walls from `building.boundary` + `wall_thickness`
  2. Merge `story.openings` + `detect_coplanar_openings()` for exterior opening rendering
  3. Render openings as colored boxes (blue=window, green=door)
  4. Render fire compartment firewalls (red semi-transparent) for non-coplanar boundaries
  5. Render FC internal openings
  6. Render roof from `story.roof`
  7. Render combustibles from `fc.combustibles` (positioned within FC boundary)
- Use world coordinates: `ox + ...`, `oy + ...` from `building.boundary`
- Import and use `detect_coplanar_openings` from `models.geometry`

- [ ] **Step 2: Smoke test 3D view**

Run app, load a facility building, verify:
- Exterior walls render correctly
- Openings appear as colored cutouts
- Fire compartment walls visible in red
- No crashes on specialized model load (the main bug fix)

- [ ] **Step 3: Commit**

```bash
git add ui/viewer_3d.py
git commit -m "refactor: update Viewer3D for boundary-based rendering"
```

---

## Task 11: Update MainWindow + Main Entry

**Files:**
- Modify: `ui/mainwindow.py`
- Modify: `main.py`
- Modify: `models/__init__.py`

- [ ] **Step 1: Update MainWindow**

- Replace all `BuildingModel` references with `BuildingGroup`
- `update_preview()`: `viewer_3d.update_model(building_group)` and `FDSGenerator().generate(building_group)`
- `open_config()`: `BuildingGroup.from_dict(data)` (no more `BuildingModel().from_dict()`)
- `save_config()`: `building_group.to_dict()` wrapped in `{"building_group": ...}`
- Wire facility_panel signals: `building_added` → add `Building` to `BuildingGroup.buildings`
- Story checkboxes: rebuild from `building_group.buildings[current_building_index].stories`

- [ ] **Step 2: Update models/__init__.py**

Export new classes, remove old ones:
```python
from models.building import Opening, Roof, FireCompartment, Story, Building, BuildingGroup
from models.geometry import detect_coplanar_openings, wall_length_for_building, wall_length_for_fc
from models.parameter_engine import ParameterEngine
from models.facility import FacilityManager
```

- [ ] **Step 3: End-to-end smoke test**

Run: `cd D:/code/fdsBuilder && python main.py`

Test sequence:
1. App launches without errors
2. Open `building_config.json` → 3D preview renders
3. FDS preview shows valid output
4. Select a specialized facility → loads as read-only
5. Select an equivalent facility → editable params, generate building
6. Save config → re-open → same state

- [ ] **Step 4: Commit**

```bash
git add ui/mainwindow.py main.py models/__init__.py
git commit -m "refactor: wire MainWindow to new BuildingGroup model"
```

---

## Task 12: Cleanup and Final Validation

**Files:**
- Modify: `models/building.py` (remove any dead code)
- Delete: `tools/modify_specialized_facilities.py` (superseded by migrate_schema.py)

- [ ] **Step 1: Remove dead code**

- Delete `check_equivalent.py` and `check_types.py` (old validation scripts, superseded)
- Delete `tools/modify_specialized_facilities.py`
- Remove any remaining references to `BuildingModel`, `WallData`, `OpeningData`, `FloorSlab` across all files
- Run: `cd D:/code/fdsBuilder && grep -r "BuildingModel\|WallData\|OpeningData\|FloorSlab\|wall_index\|floor_slab" --include="*.py" models/ generators/ ui/`
- Expected: No matches (all references removed)

- [ ] **Step 2: Run all tests**

Run: `cd D:/code/fdsBuilder && python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 3: Full app smoke test**

Run app, exercise all major flows:
1. New project → add building → edit openings → save
2. Load specialized facility → verify read-only → 3D renders
3. Load equivalent facility → adjust params → generate → 3D renders
4. Export FDS → verify `&OBST`, `&HOLE` output has no overlapping coordinates
5. Multi-building group → verify offsets

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "refactor: cleanup dead code, complete Phase A data model refactoring"
```
