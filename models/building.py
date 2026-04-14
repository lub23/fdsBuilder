#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Building model dataclasses for FDS generation.

Classes: Opening, Roof, FireCompartment, Story, Building, BuildingGroup.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ============================================================
# Opening
# ============================================================
@dataclass
class Opening:
    """A door, window, or other opening in a wall.

    Attributes:
        wall:     Which wall the opening is on ("x_min", "x_max", "y_min", "y_max").
        type:     Opening type ("door", "window", "opening", "loading_dock", "ribbon_window").
        boundary: [w_offset, width, h_offset, height] -- offset + size along wall.
    """
    wall: str                    # "x_min", "x_max", "y_min", "y_max"
    type: str                    # "door", "window", "opening", "loading_dock", "ribbon_window"
    boundary: list[float]        # [w_offset, width, h_offset, height]

    def to_dict(self) -> dict:
        return {"wall": self.wall, "type": self.type, "boundary": list(self.boundary)}

    @classmethod
    def from_dict(cls, d: dict) -> Opening:
        return cls(
            wall=d["wall"],
            type=d["type"],
            boundary=list(d["boundary"]),
        )


# ============================================================
# Roof
# ============================================================
@dataclass
class Roof:
    """Roof slab for a story.

    Attributes:
        thickness: Slab thickness in metres.
        material:  FDS surface material name.
        openings:  List of dicts, each with a ``boundary`` key [x, length, y, width].
    """
    thickness: float = 0.2
    material: str = "CONCRETE"
    openings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "thickness": self.thickness,
            "material": self.material,
            "openings": [dict(o) for o in self.openings],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Roof:
        return cls(
            thickness=d.get("thickness", 0.2),
            material=d.get("material", "CONCRETE"),
            openings=d.get("openings", []),
        )


# ============================================================
# FireCompartment
# ============================================================
@dataclass
class FireCompartment:
    """A fire compartment within a story.

    Attributes:
        name:                  Human-readable compartment name.
        boundary:              [x_min, x_max, y_min, y_max] in building-local coords.
        firewall_thickness:    Thickness of partition firewalls in metres.
        firewall_material:     FDS surface material name.
        openings:              Openings in this compartment's firewalls.
        combustibles:          List of combustible item dicts.
        specialized_components: List of specialized component dicts.
    """
    name: str = ""
    boundary: list[float] = field(default_factory=lambda: [0, 0, 0, 0])
    firewall_thickness: float = 0.3
    firewall_material: str = "CONCRETE"
    openings: list[Opening] = field(default_factory=list)
    combustibles: list[dict] = field(default_factory=list)
    specialized_components: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "boundary": list(self.boundary),
            "firewall_thickness": self.firewall_thickness,
            "firewall_material": self.firewall_material,
            "openings": [o.to_dict() for o in self.openings],
            "combustibles": [dict(c) for c in self.combustibles],
            "specialized_components": [dict(sc) for sc in self.specialized_components],
        }

    @classmethod
    def from_dict(cls, d: dict) -> FireCompartment:
        return cls(
            name=d.get("name", ""),
            boundary=list(d.get("boundary", [0, 0, 0, 0])),
            firewall_thickness=d.get("firewall_thickness", 0.3),
            firewall_material=d.get("firewall_material", "CONCRETE"),
            openings=[Opening.from_dict(o) for o in d.get("openings", [])],
            combustibles=d.get("combustibles", []),
            specialized_components=d.get("specialized_components", []),
        )


# ============================================================
# Story
# ============================================================
@dataclass
class Story:
    """A single story (floor) in a building.

    Attributes:
        name:              Story label, e.g. "1F", "2F".
        height:            Floor-to-ceiling height in metres.
        openings:          Exterior openings on this story.
        fire_compartments: Fire compartments within this story.
        roof:              Roof/floor-slab above this story.
        z_bottom:          Runtime-computed bottom elevation (set by Building.update_z_offsets).
    """
    name: str = "1F"
    height: float = 3.0
    openings: list[Opening] = field(default_factory=list)
    fire_compartments: list[FireCompartment] = field(default_factory=list)
    roof: Roof = field(default_factory=Roof)
    z_bottom: float = 0.0

    @property
    def z_top(self) -> float:
        return self.z_bottom + self.height

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "height": self.height,
            "openings": [o.to_dict() for o in self.openings],
            "fire_compartments": [fc.to_dict() for fc in self.fire_compartments],
            "roof": self.roof.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Story:
        return cls(
            name=d.get("name", "1F"),
            height=d.get("height", 3.0),
            openings=[Opening.from_dict(o) for o in d.get("openings", [])],
            fire_compartments=[FireCompartment.from_dict(fc) for fc in d.get("fire_compartments", [])],
            roof=Roof.from_dict(d.get("roof", {})),
        )


# ============================================================
# Building
# ============================================================
@dataclass
class Building:
    """A single building composed of one or more stories.

    Attributes:
        name:              Machine-readable name / identifier.
        cn_name:           Human-readable Chinese name.
        boundary:          [offset_x, length, offset_y, width] -- position + size.
        wall_thickness:    Exterior wall thickness in metres.
        height:            Summary height (authoritative value from sum of story heights).
        boundary_polygons: Optional polygon list for non-rectangular footprints.
        stories:           Ordered list of stories from bottom to top.
    """
    name: str = ""
    cn_name: str = ""
    boundary: list[float] = field(default_factory=lambda: [0, 20, 0, 10])
    wall_thickness: float = 0.24
    height: float = 3.0
    boundary_polygons: list | None = None
    stories: list[Story] = field(default_factory=list)

    # -- convenience properties -----------------------------------------------

    @property
    def length(self) -> float:
        return self.boundary[1]

    @property
    def width(self) -> float:
        return self.boundary[3]

    @property
    def offset_x(self) -> float:
        return self.boundary[0]

    @property
    def offset_y(self) -> float:
        return self.boundary[2]

    # -- runtime helpers ------------------------------------------------------

    def update_z_offsets(self) -> None:
        """Compute cumulative z_bottom for each story."""
        z = 0.0
        for story in self.stories:
            story.z_bottom = z
            z += story.height

    def get_exterior_walls(self, story_index: int) -> dict[str, list[float]]:
        """Generate 4 exterior wall OBST boxes.

        Returns:
            {wall_id: [x1, x2, y1, y2, z1, z2]}
        """
        ox, L, oy, W = self.boundary[0], self.boundary[1], self.boundary[2], self.boundary[3]
        t = self.wall_thickness
        story = self.stories[story_index]
        z0, z1 = story.z_bottom, story.z_top
        return {
            "y_min": [ox - t / 2, ox + L + t / 2, oy - t,       oy,           z0, z1],
            "y_max": [ox - t / 2, ox + L + t / 2, oy + W,       oy + W + t,   z0, z1],
            "x_min": [ox - t,     ox,              oy - t / 2,   oy + W + t / 2, z0, z1],
            "x_max": [ox + L,     ox + L + t,      oy - t / 2,   oy + W + t / 2, z0, z1],
        }

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict:
        d: dict = {
            "name": self.name,
            "cn_name": self.cn_name,
            "boundary": list(self.boundary),
            "wall_thickness": self.wall_thickness,
            "height": self.height,
            "boundary_polygons": self.boundary_polygons,
            "stories": [s.to_dict() for s in self.stories],
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Building:
        return cls(
            name=d.get("name", ""),
            cn_name=d.get("cn_name", ""),
            boundary=list(d.get("boundary", [0, 20, 0, 10])),
            wall_thickness=d.get("wall_thickness", 0.24),
            height=d.get("height", 3.0),
            boundary_polygons=d.get("boundary_polygons", None),
            stories=[Story.from_dict(s) for s in d.get("stories", [])],
        )


# ============================================================
# BuildingGroup
# ============================================================
@dataclass
class BuildingGroup:
    """A group of buildings for a single simulation scenario.

    Attributes:
        buildings:       List of Building instances.
        heat_source:     Heat source configuration dict.
        simulation_time: Total simulation time in seconds.
        domain:          Computational domain settings.
        output:          Output control settings.
    """
    buildings: list[Building] = field(default_factory=list)
    heat_source: dict = field(default_factory=dict)
    simulation_time: float = 300
    domain: dict = field(default_factory=lambda: {"padding": 5.0, "mesh_cells": [80, 60, 40]})
    output: dict = field(default_factory=lambda: {"slices": True, "devices": True})

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "buildings": [b.to_dict() for b in self.buildings],
            "heat_source": dict(self.heat_source),
            "simulation_time": self.simulation_time,
            "domain": dict(self.domain),
            "output": dict(self.output),
        }

    @classmethod
    def from_dict(cls, data: dict) -> BuildingGroup:
        """Deserialize from dict.

        Handles three input shapes:
          1. ``{"building_group": {...}}`` -- project save/load wrapper
          2. ``{"type": "specialized", "buildings": [...]}`` -- facility JSON
          3. ``{"buildings": [...], ...}`` -- direct / already-unwrapped
        """
        # Unwrap project-save wrapper
        if "building_group" in data:
            data = data["building_group"]

        return cls(
            buildings=[Building.from_dict(b) for b in data.get("buildings", [])],
            heat_source=data.get("heat_source", {}),
            simulation_time=data.get("simulation_time", 300),
            domain=data.get("domain", {"padding": 5.0, "mesh_cells": [80, 60, 40]}),
            output=data.get("output", {"slices": True, "devices": True}),
        )
