#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Building model dataclasses for FDS generation.

Classes: Opening, Roof, FireCompartment, Story, Building, BuildingGroup.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from models.combustibles import Combustible


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

    wall: str  # "x_min", "x_max", "y_min", "y_max"
    type: str  # "door", "window", "opening", "loading_dock", "ribbon_window"
    boundary: list[float]  # [w_offset, width, h_offset, height]

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
        openings = d.get("openings", [])
        if isinstance(openings, list):
            openings = [o for o in openings if isinstance(o, dict)]
        else:
            openings = []
        return cls(
            thickness=d.get("thickness", 0.2),
            material=d.get("material", "CONCRETE"),
            openings=openings,
        )


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
            "combustibles": [
                c if isinstance(c, dict) else c.to_dict() for c in self.combustibles
            ],
            "specialized_components": [dict(sc) for sc in self.specialized_components],
        }

    @classmethod
    def from_dict(cls, d: dict) -> FireCompartment:
        fc = cls(
            name=d.get("name", ""),
            boundary=list(d.get("boundary", [0, 0, 0, 0])),
            firewall_thickness=d.get("firewall_thickness", 0.3),
            firewall_material=d.get("firewall_material", "CONCRETE"),
            openings=[Opening.from_dict(o) for o in d.get("openings", [])],
            combustibles=d.get("combustibles", []),
            specialized_components=d.get("specialized_components", []),
        )

        fc_length = fc.boundary[1] - fc.boundary[0]
        fc_width = fc.boundary[3] - fc.boundary[2]

        for cb in fc.combustibles:
            if not isinstance(cb, dict):
                continue
            key = cb.get("key", cb.get("preset_key", ""))
            length = cb.get("length", 1.0)
            width = cb.get("width", 1.0)
            rotation = cb.get("rotation", 0)
            if rotation == 90:
                length, width = width, length
            if length > fc_length or width > fc_width:
                print(
                    f"WARNING: {fc.name}: {key} exceeds bounds "
                    f"({length}x{width}) vs room ({fc_length}x{fc_width})"
                )

        return fc


# ============================================================
# Story
# ============================================================
@dataclass
class Story:
    """A single story (floor) in a building.

    Attributes:
        name:                   Story label, e.g. "1F", "2F".
        height:                 Floor-to-ceiling height in metres.
        openings:               Exterior openings on this story.
        fire_compartments:      Fire compartments within this story.
        combustibles:           Story-level combustibles with explicit ``boundary``.
        specialized_components: Story-level specialized components with explicit ``boundary``.
        roof:                   Roof/floor-slab above this story.
        z_bottom:               Runtime-computed bottom elevation (set by Building.update_z_offsets).
    """

    name: str = "1F"
    height: float = 3.0
    openings: list[Opening] = field(default_factory=list)
    fire_compartments: list[FireCompartment] = field(default_factory=list)
    combustibles: list[dict] = field(default_factory=list)
    specialized_components: list[dict] = field(default_factory=list)
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
            "combustibles": list(self.combustibles),
            "specialized_components": list(self.specialized_components),
            "roof": self.roof.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Story:
        return cls(
            name=d.get("name", "1F"),
            height=d.get("height", 3.0),
            openings=[Opening.from_dict(o) for o in d.get("openings", [])],
            fire_compartments=[
                FireCompartment.from_dict(fc) for fc in d.get("fire_compartments", [])
            ],
            combustibles=list(d.get("combustibles", [])),
            specialized_components=list(d.get("specialized_components", [])),
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
        stories:           Ordered list of stories from bottom to top.
    """

    name: str = ""
    cn_name: str = ""
    boundary: list[float] = field(default_factory=lambda: [0, 20, 0, 10])
    wall_thickness: float = 0.24
    height: float = 3.0
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
        ox, L, oy, W = (
            self.boundary[0],
            self.boundary[1],
            self.boundary[2],
            self.boundary[3],
        )
        t = self.wall_thickness
        story = self.stories[story_index]
        z0, z1 = story.z_bottom, story.z_top
        return {
            "y_min": [ox - t / 2, ox + L + t / 2, oy - t, oy, z0, z1],
            "y_max": [ox - t / 2, ox + L + t / 2, oy + W, oy + W + t, z0, z1],
            "x_min": [ox - t, ox, oy - t / 2, oy + W + t / 2, z0, z1],
            "x_max": [ox + L, ox + L + t, oy - t / 2, oy + W + t / 2, z0, z1],
        }

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict:
        d: dict = {
            "name": self.name,
            "cn_name": self.cn_name,
            "boundary": list(self.boundary),
            "wall_thickness": self.wall_thickness,
            "height": self.height,
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
        heat_source:     Heat source configuration dict:
                         {azimuth(°), elevation(°), net_heat_flux(kW/m²), duration(s)}.
        simulation_time: Total simulation time in seconds.
        domain:          Computational domain settings.
        output:          Output control settings.
    """

    buildings: list[Building] = field(default_factory=list)
    name: str = ""
    heat_source: dict = field(default_factory=lambda: {
        "azimuth": 0,
        "elevation": 0,
        "net_heat_flux": 1000,
        "duration": 1.36,
    })
    simulation_time: float = 1800
    domain: dict = field(
        default_factory=lambda: {"padding": 5.0, "grid_size": 1.0}
    )
    output: dict = field(default_factory=lambda: {"slices": True, "devices": True})

    # -- convenience properties -----------------------------------------------

    @property
    def building_group(self) -> BuildingGroup:
        """Compat: let code that does ``model.building_group`` work when model IS a BuildingGroup."""
        return self

    @property
    def total_height(self) -> float:
        """Max height across all buildings (sum of story heights)."""
        if not self.buildings:
            return 0.0
        return max(sum(s.height for s in b.stories) for b in self.buildings)

    @property
    def num_stories(self) -> int:
        """Number of stories in the first building."""
        if self.buildings:
            return len(self.buildings[0].stories)
        return 0

    @property
    def length(self) -> float:
        """Length of the first building (compat)."""
        if self.buildings:
            return self.buildings[0].length
        return 0.0

    @property
    def width(self) -> float:
        """Width of the first building (compat)."""
        if self.buildings:
            return self.buildings[0].width
        return 0.0

    # -- runtime helpers ------------------------------------------------------

    def update_z_offsets(self) -> None:
        """Compute cumulative z_bottom for every story in every building."""
        for b in self.buildings:
            b.update_z_offsets()

    def add_building(self, building: Building) -> None:
        """Append a building to the group."""
        self.buildings.append(building)

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "buildings": [b.to_dict() for b in self.buildings],
            "name": self.name,
            "heat_source": dict(self.heat_source),
            "simulation_time": self.simulation_time,
            "domain": dict(self.domain),
            "output": dict(self.output),
        }

    @classmethod
    def from_dict(cls, data: dict) -> BuildingGroup:
        """Deserialize from dict, migrating legacy heat_source fields.

        Migration:
          - Legacy fields ``enabled``, ``distance``, ``width_ratio``,
            ``height_ratio``, ``location``, ``use_ramp`` are dropped.
          - Missing fields get 2026-04-19 defaults.
        """
        # Unwrap project-save wrapper
        if "building_group" in data:
            data = data["building_group"]

        raw_hs = data.get("heat_source", {}) or {}
        hs = {
            "azimuth": raw_hs.get("azimuth", 0),
            "elevation": raw_hs.get("elevation", 0),
            "net_heat_flux": float(raw_hs.get("net_heat_flux", 1000)),
            "duration": raw_hs.get("duration", 1.36),
        }

        domain = data.get("domain", {"padding": 5.0, "grid_size": 1.0})
        # Legacy configs may have mesh_cells; drop it in favor of grid_size.
        if "grid_size" not in domain:
            domain = {"padding": domain.get("padding", 5.0), "grid_size": 1.0}
        return cls(
            buildings=[Building.from_dict(b) for b in data.get("buildings", [])],
            name=data.get("name", ""),
            heat_source=hs,
            simulation_time=data.get("simulation_time", 1800),
            domain=domain,
            output=data.get("output", {"slices": True, "devices": True}),
        )
