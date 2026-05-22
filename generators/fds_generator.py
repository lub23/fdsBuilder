#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File  : fds_generator.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 3.0
@Desc  : FDS file generator for boundary-based BuildingGroup model
"""

import re
import math
from models.building import (
    BuildingGroup,
    Building,
    Story,
    Opening,
    FireCompartment,
    Roof,
)
from models.geometry import (
    detect_coplanar_openings,
    wall_length_for_building,
    wall_length_for_fc,
    resolve_negative_offset,
    is_coplanar,
)
from models.materials import MATERIAL_LIBRARY, COMBUSTIBLE_LIBRARY
from models.combustibles import SPECIALIZED_COMPONENTS


# 5cm redundancy expansion in the wall-normal direction for HOLEs
REDUNDANCY = 0.05


def _get_part_ignition_temp(part, component_ignition_temp: float) -> float:
    """Return effective ignition temperature for a component part.

    Uses part.ignition_temp if set (> 0), otherwise falls back to
    COMBUSTIBLE_LIBRARY entry, then to component_ignition_temp.
    """
    # Part has explicit ignition_temp set
    if part.ignition_temp > 0:
        return part.ignition_temp
    # Check COMBUSTIBLE_LIBRARY for the material
    cb = COMBUSTIBLE_LIBRARY.get(part.material_key)
    if cb is not None:
        return cb.get("ignition_temp", component_ignition_temp)
    # Fall back to component-level default
    return component_ignition_temp


def _compute_sibling_overlaps(fc, siblings):
    """Return [(x1, x2, y1, y2), ...] exclusion boxes for *fc*.

    For each sibling compartment on the same story whose boundary area
    is strictly smaller than *fc*'s, add the intersection of the two
    rectangles as an exclusion zone. This keeps items placed in an
    outer compartment from landing inside a nested smaller one.
    """
    def _area(b):
        return (b[1] - b[0]) * (b[3] - b[2])

    fx1, fx2, fy1, fy2 = fc.boundary
    fc_area = _area(fc.boundary)
    excl: list[tuple[float, float, float, float]] = []
    for sib in siblings:
        if sib is fc:
            continue
        if _area(sib.boundary) >= fc_area:
            continue
        sx1, sx2, sy1, sy2 = sib.boundary
        ix1, ix2 = max(fx1, sx1), min(fx2, sx2)
        iy1, iy2 = max(fy1, sy1), min(fy2, sy2)
        if ix2 > ix1 + 1e-6 and iy2 > iy1 + 1e-6:
            excl.append((ix1, ix2, iy1, iy2))
    return excl


# ============================================================
# FDS Generator
# ============================================================
class FDSGenerator:
    """FDS file generator for BuildingGroup."""

    def __init__(self, building_group):
        """Accept a BuildingGroup directly, or a legacy model object.

        Legacy callers may pass an object with a ``building_group`` attribute;
        we extract the BuildingGroup from it.
        """
        if isinstance(building_group, BuildingGroup):
            self.bg = building_group
        elif hasattr(building_group, "building_group"):
            # Legacy compat: old callers pass a model with .building_group
            bg = building_group.building_group
            if isinstance(bg, BuildingGroup):
                self.bg = bg
            else:
                self.bg = BuildingGroup.from_dict(
                    bg if isinstance(bg, dict) else bg.to_dict()
                )
            # Copy top-level fields from legacy model if present
            if hasattr(building_group, "heat_source") and building_group.heat_source:
                self.bg.heat_source = building_group.heat_source
            if hasattr(building_group, "simulation_time"):
                self.bg.simulation_time = building_group.simulation_time
            if hasattr(building_group, "domain"):
                self.bg.domain = building_group.domain
            if hasattr(building_group, "output"):
                self.bg.output = building_group.output
            if hasattr(building_group, "materials"):
                self._materials_override = building_group.materials
        else:
            raise TypeError(f"Expected BuildingGroup, got {type(building_group)}")

    # ------------------------------------------------------------------
    # Low-level emitters
    # ------------------------------------------------------------------
    def _emit_obst(self, lines, bounds, surf="WALL", comment=""):
        """Append an &OBST line.  bounds = [x1, x2, y1, y2, z1, z2]."""
        x1, x2, y1, y2, z1, z2 = bounds
        c = f"  ! {comment}" if comment else ""
        lines.append(
            f"&OBST XB={x1:.3f},{x2:.3f},{y1:.3f},{y2:.3f},{z1:.3f},{z2:.3f}, SURF_ID='{surf}' /{c}\n"
        )

    def _emit_hole(self, lines, bounds, comment=""):
        """Append a &HOLE line.  bounds = [x1, x2, y1, y2, z1, z2]."""
        x1, x2, y1, y2, z1, z2 = bounds
        c = f"  ! {comment}" if comment else ""
        lines.append(
            f"&HOLE XB={x1:.3f},{x2:.3f},{y1:.3f},{y2:.3f},{z1:.3f},{z2:.3f} /{c}\n"
        )

    def gen_box(self, x1, x2, y1, y2, z1, z2, surf="WALL"):
        """Compat helper returning a formatted &OBST string."""
        return f"&OBST XB={x1:.3f},{x2:.3f},{y1:.3f},{y2:.3f},{z1:.3f},{z2:.3f}, SURF_ID='{surf}' /\n"

    # ------------------------------------------------------------------
    # Materials & Surfaces
    # ------------------------------------------------------------------
    def _generate_materials(self, lines):
        """Generate &MATL and &SURF blocks."""
        bg = self.bg
        buildings = bg.buildings

        # Collect which MATL keys are referenced
        wall_matl_keys = set()
        combustible_keys = set()
        component_matl_keys = set()

        # Legacy materials override (for existing UI integration)
        materials_map = getattr(self, "_materials_override", None) or {}
        wall_matl_keys.update(materials_map.values())

        for b in buildings:
            for story in b.stories:
                # FC-level combustibles / components
                for fc in story.fire_compartments:
                    for cb in fc.combustibles:
                        key = cb.get("key", "")
                        if key:
                            combustible_keys.add(key)
                    for sc_info in fc.specialized_components:
                        comp = SPECIALIZED_COMPONENTS.get(sc_info.get("key", ""))
                        if comp:
                            for part in comp.parts:
                                if part.material_key:
                                    component_matl_keys.add(part.material_key)
                # Story-level combustibles / components
                for cb in story.combustibles:
                    key = cb.get("key", "")
                    if key:
                        combustible_keys.add(key)
                for sc_info in story.specialized_components:
                    comp = SPECIALIZED_COMPONENTS.get(sc_info.get("key", ""))
                    if comp:
                        for part in comp.parts:
                            if part.material_key:
                                component_matl_keys.add(part.material_key)

        lines.append("! ========== 追踪粒子 ==========\n")
        lines.append(
            "&PART ID='TRACER',\n"
            "      MASSLESS=.TRUE.,\n"
            "      MONODISPERSE=.TRUE.,\n"
            "      AGE=60.0,\n"
            "      SAMPLING_FACTOR=10 /\n\n"
        )

        lines.append("! ========== 材料定义 ==========\n")

        # Wall / structural materials
        all_structural = wall_matl_keys | component_matl_keys
        for mat_name in sorted(all_structural):
            mat = MATERIAL_LIBRARY.get(mat_name)
            if mat:
                lines.append(
                    f"&MATL ID='{mat_name}', DENSITY={mat['DENSITY']}, "
                    f"CONDUCTIVITY={mat['CONDUCTIVITY']}, SPECIFIC_HEAT={mat['SPECIFIC_HEAT']} /\n"
                )
            else:
                cb = COMBUSTIBLE_LIBRARY.get(mat_name)
                if cb and cb.get("matl"):
                    mt = cb["matl"]
                    hoc = mt.get("HEAT_OF_COMBUSTION", 0)
                    lines.append(
                        f"&MATL ID='{mat_name}', DENSITY={mt['DENSITY']}, "
                        f"CONDUCTIVITY={mt['CONDUCTIVITY']}, SPECIFIC_HEAT={mt['SPECIFIC_HEAT']}"
                        f"{f', HEAT_OF_COMBUSTION={hoc}' if hoc else ''} /\n"
                    )

        # Default structural materials (always need CONCRETE at minimum)
        for default_mat in ("CONCRETE",):
            if default_mat not in all_structural and default_mat in MATERIAL_LIBRARY:
                mat = MATERIAL_LIBRARY[default_mat]
                lines.append(
                    f"&MATL ID='{default_mat}', DENSITY={mat['DENSITY']}, "
                    f"CONDUCTIVITY={mat['CONDUCTIVITY']}, SPECIFIC_HEAT={mat['SPECIFIC_HEAT']} /\n"
                )

        lines.append("\n! ========== 表面定义 ==========\n")

        # Standard surfaces
        surfaces = {
            "WALL": ("walls", "墙体"),
            "FLOOR": ("floor", "地板"),
            "ROOF": ("roof", "屋顶"),
        }
        for surf_name, (mat_key, desc) in surfaces.items():
            mat_name = materials_map.get(mat_key, "CONCRETE")
            if mat_name in MATERIAL_LIBRARY:
                thick = MATERIAL_LIBRARY[mat_name]["THICKNESS"]
                lines.append(
                    f"&SURF ID='{surf_name}', MATL_ID='{mat_name}', THICKNESS={thick}, BACKING='VOID' /  ! {desc}\n"
                )

        comp_surfs_done = set()
        for mat_key in sorted(component_matl_keys):
            if mat_key in comp_surfs_done:
                continue
            if mat_key in COMBUSTIBLE_LIBRARY:
                # Component parts reference surf_id="{mat_key}_SURF" —
                # emit a SURF with HRRPUA/ignition from the combustible library
                cb_def = COMBUSTIBLE_LIBRARY[mat_key]
                surf_id = f"{mat_key}_SURF"
                if surf_id in comp_surfs_done:
                    continue
                hrrpua = cb_def.get("hrrpua", 300)
                ign_temp = cb_def.get("ignition_temp", 250)
                color = cb_def.get("color", "RED")
                bulk_density = cb_def.get("matl", {}).get("DENSITY", 500)
                lines.append(
                    f"&SURF ID='{surf_id}',\n"
                    f"      HRRPUA={hrrpua},\n"
                    f"      IGNITION_TEMPERATURE={ign_temp},\n"
                    f"      BURN_AWAY=.TRUE.,\n"
                    f"      BULK_DENSITY={bulk_density},\n"
                    f"      THICKNESS=0.05,\n"
                    f"      PART_ID='TRACER',\n"
                    f"      COLOR='{color}' /\n\n"
                )
                comp_surfs_done.add(surf_id)
                continue
            surf_id = f"{mat_key}_SURF"
            mat = MATERIAL_LIBRARY.get(mat_key)
            if mat:
                thick = mat.get("THICKNESS", 0.1)
                lines.append(
                    f"&SURF ID='{surf_id}', MATL_ID='{mat_key}', THICKNESS={thick} /\n"
                )
                comp_surfs_done.add(surf_id)

        # Combustible MATL / SURF definitions
        if combustible_keys:
            lines.append("\n! ========== 可燃物热解材料/表面 ==========\n")
            # Define fuel SPEC for pyrolysis (matches REAC fuel)
            lines.append("&SPEC ID='METHANE' /\n\n")
            for ck in sorted(combustible_keys):
                if ck not in COMBUSTIBLE_LIBRARY:
                    continue
                cb_def = COMBUSTIBLE_LIBRARY[ck]
                mt = cb_def.get("matl", {})
                if not mt:
                    continue
                matl_id = f"PYRO_{ck}"
                surf_id = f"SURF_{ck}"
                density = mt.get("DENSITY", 500)
                conductivity = mt.get("CONDUCTIVITY", 0.2)
                specific_heat = mt.get("SPECIFIC_HEAT", 1.0)
                hoc = mt.get("HEAT_OF_COMBUSTION", 0)
                ignition_temp = cb_def.get("ignition_temp", 250.0)
                color = cb_def.get("color", "RED")

                # Pyrolysis MATL: required for BURN_AWAY
                # HEAT_OF_REACTION: endothermic pyrolysis energy (~20% of HOC)
                hor = max(400, int(hoc * 0.2)) if hoc else 500
                lines.append(
                    f"&MATL ID='{matl_id}',\n"
                    f"      DENSITY={density},\n"
                    f"      CONDUCTIVITY={conductivity},\n"
                    f"      SPECIFIC_HEAT={specific_heat},\n"
                    f"      HEAT_OF_REACTION={hor},\n"
                    f"      NU_SPEC=0.8,\n"
                    f"      SPEC_ID='METHANE',\n"
                    f"      REFERENCE_TEMPERATURE={ignition_temp:.1f} /\n\n"
                )

                # SURF with BURN_AWAY: MATL_ID required, BULK_DENSITY on OBST
                lines.append(
                    f"&SURF ID='{surf_id}',\n"
                    f"      MATL_ID='{matl_id}',\n"
                    f"      THICKNESS=0.05,\n"
                    f"      BURN_AWAY=.TRUE.,\n"
                    f"      BACKING='VOID',\n"
                    f"      COLOR='{color}' /\n\n"
                )

        lines.append("\n")

    # ------------------------------------------------------------------
    # Exterior walls
    # ------------------------------------------------------------------
    def _generate_exterior_walls(self, building, story, story_index, lines):
        """Generate 4 exterior wall OBST + openings as HOLE."""
        walls = building.get_exterior_walls(story_index)

        # Merge story-level exterior openings + coplanar FC openings
        all_exterior_openings = list(story.openings)
        all_exterior_openings += detect_coplanar_openings(building, story)

        for wall_id, obst_bounds in walls.items():
            wall_openings = [o for o in all_exterior_openings if o.wall == wall_id]
            self._emit_obst(
                lines, obst_bounds, surf="WALL", comment=f"ext wall {wall_id}"
            )
            for opening in wall_openings:
                hole = self._opening_to_hole(wall_id, obst_bounds, opening, building)
                self._emit_hole(lines, hole, comment=f"{opening.type} on {wall_id}")

    def _opening_to_hole(self, wall_id, obst_bounds, opening, building):
        """Convert an Opening to a HOLE bounding box for an exterior wall."""
        ox, L, oy, W = building.boundary
        t = building.wall_thickness
        w_off, w, h_off, h = opening.boundary

        # Resolve negative w_offset
        if wall_id in ("y_min", "y_max"):
            wall_len = L
        else:
            wall_len = W
        if w_off < 0:
            w_off = resolve_negative_offset(w_off, w, wall_len)

        z0 = obst_bounds[4]  # z_bottom of the wall

        if wall_id == "y_min":
            return [
                ox + w_off,
                ox + w_off + w,
                oy - t - REDUNDANCY,
                oy + REDUNDANCY,
                z0 + h_off,
                z0 + h_off + h,
            ]
        elif wall_id == "y_max":
            return [
                ox + w_off,
                ox + w_off + w,
                oy + W - REDUNDANCY,
                oy + W + t + REDUNDANCY,
                z0 + h_off,
                z0 + h_off + h,
            ]
        elif wall_id == "x_min":
            return [
                ox - t - REDUNDANCY,
                ox + REDUNDANCY,
                oy + w_off,
                oy + w_off + w,
                z0 + h_off,
                z0 + h_off + h,
            ]
        else:  # x_max
            return [
                ox + L - REDUNDANCY,
                ox + L + t + REDUNDANCY,
                oy + w_off,
                oy + w_off + w,
                z0 + h_off,
                z0 + h_off + h,
            ]

    # ------------------------------------------------------------------
    # Fire compartment walls (non-coplanar only)
    # ------------------------------------------------------------------
    def _generate_firewalls(self, building, story, lines):
        """Generate partition wall OBSTs for fire compartments."""
        ox, L, oy, W = building.boundary
        z0, z1 = story.z_bottom, story.z_top

        for fc in story.fire_compartments:
            if fc.firewall_thickness <= 0:
                continue
            x_min, x_max, y_min, y_max = fc.boundary
            ft = fc.firewall_thickness

            # Only non-coplanar boundaries get firewalls
            # x_min boundary
            if x_min > 0 and not is_coplanar(fc.boundary, L, W, "x_min"):
                self._emit_obst(
                    lines,
                    [
                        ox + x_min - ft / 2,
                        ox + x_min + ft / 2,
                        oy + y_min,
                        oy + y_max,
                        z0,
                        z1,
                    ],
                    surf="WALL",
                    comment=f"firewall {fc.name} x_min",
                )
            # x_max boundary
            if abs(x_max - L) > 1e-6 and not is_coplanar(fc.boundary, L, W, "x_max"):
                self._emit_obst(
                    lines,
                    [
                        ox + x_max - ft / 2,
                        ox + x_max + ft / 2,
                        oy + y_min,
                        oy + y_max,
                        z0,
                        z1,
                    ],
                    surf="WALL",
                    comment=f"firewall {fc.name} x_max",
                )
            # y_min boundary
            if y_min > 0 and not is_coplanar(fc.boundary, L, W, "y_min"):
                self._emit_obst(
                    lines,
                    [
                        ox + x_min,
                        ox + x_max,
                        oy + y_min - ft / 2,
                        oy + y_min + ft / 2,
                        z0,
                        z1,
                    ],
                    surf="WALL",
                    comment=f"firewall {fc.name} y_min",
                )
            # y_max boundary
            if abs(y_max - W) > 1e-6 and not is_coplanar(fc.boundary, L, W, "y_max"):
                self._emit_obst(
                    lines,
                    [
                        ox + x_min,
                        ox + x_max,
                        oy + y_max - ft / 2,
                        oy + y_max + ft / 2,
                        z0,
                        z1,
                    ],
                    surf="WALL",
                    comment=f"firewall {fc.name} y_max",
                )

            # Non-coplanar FC openings (not on exterior walls) -> HOLE on firewalls
            for opening in fc.openings:
                if not is_coplanar(fc.boundary, L, W, opening.wall):
                    hole = self._fc_opening_to_hole(fc, opening, building, story)
                    self._emit_hole(lines, hole, comment=f"FC opening {opening.type}")

    def _fc_opening_to_hole(self, fc, opening, building, story):
        """Convert a FireCompartment opening to a HOLE on the partition firewall."""
        ox, _L, oy, _W = building.boundary
        x_min, x_max, y_min, y_max = fc.boundary
        ft = fc.firewall_thickness
        w_off, w, h_off, h = opening.boundary
        z0 = story.z_bottom
        wall_id = opening.wall

        # Determine wall length for negative offset resolution
        wl = wall_length_for_fc(fc.boundary, wall_id)
        if w_off < 0:
            w_off = resolve_negative_offset(w_off, w, wl)

        if wall_id == "x_min":
            wx = ox + x_min
            return [
                wx - ft / 2 - REDUNDANCY,
                wx + ft / 2 + REDUNDANCY,
                oy + y_min + w_off,
                oy + y_min + w_off + w,
                z0 + h_off,
                z0 + h_off + h,
            ]
        elif wall_id == "x_max":
            wx = ox + x_max
            return [
                wx - ft / 2 - REDUNDANCY,
                wx + ft / 2 + REDUNDANCY,
                oy + y_min + w_off,
                oy + y_min + w_off + w,
                z0 + h_off,
                z0 + h_off + h,
            ]
        elif wall_id == "y_min":
            wy = oy + y_min
            return [
                ox + x_min + w_off,
                ox + x_min + w_off + w,
                wy - ft / 2 - REDUNDANCY,
                wy + ft / 2 + REDUNDANCY,
                z0 + h_off,
                z0 + h_off + h,
            ]
        else:  # y_max
            wy = oy + y_max
            return [
                ox + x_min + w_off,
                ox + x_min + w_off + w,
                wy - ft / 2 - REDUNDANCY,
                wy + ft / 2 + REDUNDANCY,
                z0 + h_off,
                z0 + h_off + h,
            ]

    # ------------------------------------------------------------------
    # Roof
    # ------------------------------------------------------------------
    def _generate_roof(self, building, story, lines):
        """Generate roof OBST and its openings as HOLEs."""
        ox, L, oy, W = building.boundary
        t = building.wall_thickness
        z = story.z_top
        roof = story.roof

        # Roof slab OBST
        self._emit_obst(
            lines,
            [
                ox - t / 2,
                ox + L + t / 2,
                oy - t / 2,
                oy + W + t / 2,
                z,
                z + roof.thickness,
            ],
            surf="ROOF",
            comment="roof slab",
        )

        # Roof openings (HOLEs for stairwells, skylights, etc.)
        for ro in roof.openings:
            bnd = ro.get("boundary", ro.get("bnd", [0, 0, 0, 0]))
            self._emit_hole(
                lines,
                [
                    ox + bnd[0],
                    ox + bnd[0] + bnd[1],
                    oy + bnd[2],
                    oy + bnd[2] + bnd[3],
                    z - 0.05,
                    z + roof.thickness + 0.05,
                ],
                comment="roof opening",
            )

    # ------------------------------------------------------------------
    # Combustibles (from fire compartment data)
    # ------------------------------------------------------------------
    def _generate_combustibles(self, building, story, lines, grid_size: float = 0.1):
        """Generate combustible and specialized component OBSTs per FC.

        Specialized components are laid out first (priority), then combustibles
        fill the remaining space. Both share the same layout grid.

        Probe placement (simplified per user request):
        - Specialized components: ONE probe on the part with lowest ignition temp
        - Regular combustibles: ONE probe ABOVE the combustible (not on surface)

        *grid_size* is the FDS cell size used by the current MESH. OBSTs whose
        smallest dimension is below this size are emitted with
        ``THICKEN=.TRUE.`` so FDS keeps them as at least one cell instead of
        snapping them away, and their probe is skipped.
        """
        from models.geometry import layout_items_in_fc

        ox, L, oy, W = building.boundary
        z0 = story.z_bottom
        subgrid_tol = 1e-6

        for fc in story.fire_compartments:
            if not fc.combustibles and not fc.specialized_components:
                continue

            all_items = []

            for sc_info in fc.specialized_components:
                key = sc_info.get("key", "")
                comp = SPECIALIZED_COMPONENTS.get(key)
                if not comp:
                    continue
                is_rocket = key.startswith("ROCKET_VEHICLE")
                is_launch_site = "发射场" in fc.name or "Launch site" in fc.name
                horizontal = is_rocket and not is_launch_site
                for ci in range(sc_info.get("count", 1)):
                    all_items.append(
                        {
                            "length": comp.total_length,
                            "width": comp.total_width,
                            "height": comp.total_height,
                            "key": key,
                            "_type": "component",
                            "_comp": comp,
                            "_instance": ci,
                            "_horizontal": horizontal,
                        }
                    )

            for cb_entry in fc.combustibles:
                key = cb_entry.get("key", "")
                count = cb_entry.get("count", 1)
                if key not in COMBUSTIBLE_LIBRARY:
                    continue
                cb_def = COMBUSTIBLE_LIBRARY[key]
                length = cb_def.get("length", 1.0)
                width = cb_def.get("width", 0.8)
                height = cb_def.get("height", 0.5)
                rotation = cb_entry.get("rotation", 0)
                if rotation == 90:
                    length, width = width, length
                for _ in range(count):
                    all_items.append(
                        {
                            "length": length,
                            "width": width,
                            "height": height,
                            "key": key,
                            "name": cb_def.get("name", key),
                            "_type": "combustible",
                        }
                    )

            exclusions = _compute_sibling_overlaps(fc, story.fire_compartments)
            placed = layout_items_in_fc(
                fc.boundary, all_items, margin=1.0, gap=0.5,
                exclusions=exclusions,
            )

            lines.append(f"! -- 可燃物与组件 ({fc.name}) --\n")
            probe_counters: dict[str, int] = {}
            cb_idx = 0
            for item in placed:
                if item.get("_type") == "component":
                    comp = item["_comp"]
                    ci = item["_instance"]
                    key = item["key"]
                    horizontal = item.get("_horizontal", False)
                    lines.append(f"! {comp.name} #{ci + 1}\n")

                    # Find part with minimum ignition temperature
                    min_ignition_pi = 0
                    min_ignition_temp = float("inf")
                    for pi, part in enumerate(comp.parts):
                        ign_temp = _get_part_ignition_temp(part, comp.ignition_temp)
                        if ign_temp < min_ignition_temp:
                            min_ignition_temp = ign_temp
                            min_ignition_pi = pi

                    # Output all OBSTs and track critical part coordinates
                    crit_px = crit_py = crit_pz = 0.0
                    crit_length = crit_width = crit_height = 0.0
                    for pi, part in enumerate(comp.parts):
                        if horizontal:
                            px = ox + item["x"] + part.dz
                            py = oy + item["y"] + part.dy
                            pz = z0 + part.dx
                            part_length = part.height
                            part_width = part.width
                            part_height = part.length
                        else:
                            px = ox + item["x"] + part.dx
                            py = oy + item["y"] + part.dy
                            pz = z0 + part.dz
                            part_length = part.length
                            part_width = part.width
                            part_height = part.height
                        surf = part.surf_id or "INERT"
                        is_subgrid = (
                            part_length < grid_size - subgrid_tol
                            or part_width < grid_size - subgrid_tol
                            or part_height < grid_size - subgrid_tol
                        )
                        thicken_kv = "THICKEN=.TRUE., " if is_subgrid else ""
                        lines.append(
                            f"&OBST XB={px:.2f},{px + part_length:.2f},"
                            f"{py:.2f},{py + part_width:.2f},"
                            f"{pz:.2f},{pz + part_height:.2f},\n"
                            f"      {thicken_kv}SURF_ID='{surf}',\n"
                            f"      ID='{key}_{fc.name}_{ci}_{pi}' /\n"
                        )
                        # Store coordinates for critical part
                        if pi == min_ignition_pi:
                            crit_px, crit_py, crit_pz = px, py, pz
                            crit_length, crit_width, crit_height = part_length, part_width, part_height

                    # Place ONE probe on the part with minimum ignition temp
                    if not is_subgrid:
                        cx = crit_px + crit_length / 2
                        cy = crit_py + crit_width / 2
                        cz = crit_pz + crit_height
                        probe_key = f"{key}_CRIT"
                        probe_counters[probe_key] = probe_counters.get(probe_key, 0) + 1
                        probe_idx = probe_counters[probe_key]
                        probe_id = f"{probe_key}_{probe_idx:02d}"
                        lines.append(
                            f"&DEVC XYZ={cx:.2f},{cy:.2f},{cz:.2f}, IOR=3, "
                            f"QUANTITY='WALL TEMPERATURE', ID='{probe_id}' /\n"
                        )
                else:
                    key = item["key"]
                    surf_id = f"SURF_{key}"
                    x1 = ox + item["x"]
                    x2 = x1 + item["length"]
                    y1 = oy + item["y"]
                    y2 = y1 + item["width"]
                    z1 = z0
                    z2 = z0 + item["height"]
                    cb_id = f"{key}_{fc.name}_{cb_idx}".replace(" ", "_")
                    is_subgrid = (
                        item["length"] < grid_size - subgrid_tol
                        or item["width"] < grid_size - subgrid_tol
                        or item["height"] < grid_size - subgrid_tol
                    )
                    thicken_kv = "THICKEN=.TRUE., " if is_subgrid else ""
                    cb_def = COMBUSTIBLE_LIBRARY.get(key, {})
                    bulk_density = cb_def.get("matl", {}).get("DENSITY", 500)
                    lines.append(
                        f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                        f"{z1:.2f},{z2:.2f},\n"
                        f"      {thicken_kv}SURF_IDS='{surf_id}','INERT','INERT',\n"
                        f"      BULK_DENSITY={bulk_density},\n"
                        f"      ID='{cb_id}' /  ! {item.get('name', key)}\n"
                    )
                    cb_idx += 1
                    probe_counters[key] = probe_counters.get(key, 0) + 1
                    probe_idx = probe_counters[key]
                    probe_id = f"{key}_{probe_idx:02d}"
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    cz = z2
                    lines.append(
                        f"&DEVC XYZ={cx:.2f},{cy:.2f},{cz:.2f}, IOR=3, "
                        f"QUANTITY='WALL TEMPERATURE', ID='{probe_id}' /\n"
                    )

    # ------------------------------------------------------------------
    # Story-level combustibles (with explicit boundary)
    # ------------------------------------------------------------------
    def _generate_story_combustibles(self, building, story, lines, grid_size: float = 0.1):
        """Generate story-level combustibles/specialized_components with explicit boundary.

        Each entry has its own ``boundary`` (in building-local coords) defining
        where items of that type are distributed.  This is for areas that are not
        covered by any fire compartment.
        """
        from models.geometry import layout_items_in_fc

        ox, _L, oy, _W = building.boundary
        z0 = story.z_bottom
        subgrid_tol = 1e-6

        if not story.combustibles and not story.specialized_components:
            return

        lines.append(f"! -- Story-level 可燃物与组件 ({story.name}) --\n")
        probe_counters: dict[str, int] = {}
        cb_idx = 0

        def _emit_placed(placed_items):
            nonlocal cb_idx
            for item in placed_items:
                if item.get("_type") == "component":
                    comp = item["_comp"]
                    ci = item["_instance"]
                    key = item["key"]
                    horizontal = item.get("_horizontal", False)
                    lines.append(f"! {comp.name} #{ci + 1} (story-level)\n")
                    min_ignition_pi = 0
                    min_ignition_temp = float("inf")
                    for pi, part in enumerate(comp.parts):
                        ign_temp = _get_part_ignition_temp(part, comp.ignition_temp)
                        if ign_temp < min_ignition_temp:
                            min_ignition_temp = ign_temp
                            min_ignition_pi = pi
                    crit_px = crit_py = crit_pz = 0.0
                    crit_length = crit_width = crit_height = 0.0
                    for pi, part in enumerate(comp.parts):
                        if horizontal:
                            px = ox + item["x"] + part.dz
                            py = oy + item["y"] + part.dy
                            pz = z0 + part.dx
                            part_length = part.height
                            part_width = part.width
                            part_height = part.length
                        else:
                            px = ox + item["x"] + part.dx
                            py = oy + item["y"] + part.dy
                            pz = z0 + part.dz
                            part_length = part.length
                            part_width = part.width
                            part_height = part.height
                        surf = part.surf_id or "INERT"
                        sg = (
                            part_length < grid_size - subgrid_tol
                            or part_width < grid_size - subgrid_tol
                            or part_height < grid_size - subgrid_tol
                        )
                        thicken_kv = "THICKEN=.TRUE., " if sg else ""
                        lines.append(
                            f"&OBST XB={px:.2f},{px + part_length:.2f},"
                            f"{py:.2f},{py + part_width:.2f},"
                            f"{pz:.2f},{pz + part_height:.2f},\n"
                            f"      {thicken_kv}SURF_ID='{surf}',\n"
                            f"      ID='{key}_story_{ci}_{pi}' /\n"
                        )
                        if pi == min_ignition_pi:
                            crit_px, crit_py, crit_pz = px, py, pz
                            crit_length, crit_width, crit_height = part_length, part_width, part_height
                    if not sg:
                        cx = crit_px + crit_length / 2
                        cy = crit_py + crit_width / 2
                        cz = crit_pz + crit_height
                        pk = f"{key}_CRIT"
                        probe_counters[pk] = probe_counters.get(pk, 0) + 1
                        pi2 = probe_counters[pk]
                        lines.append(
                            f"&DEVC XYZ={cx:.2f},{cy:.2f},{cz:.2f}, IOR=3, "
                            f"QUANTITY='WALL TEMPERATURE', ID='STORY_{pk}_{pi2:02d}' /\n"
                        )
                else:
                    key = item["key"]
                    surf_id = f"SURF_{key}"
                    x1 = ox + item["x"]
                    x2 = x1 + item["length"]
                    y1 = oy + item["y"]
                    y2 = y1 + item["width"]
                    z1 = z0
                    z2 = z0 + item["height"]
                    cb_id = f"{key}_story_{cb_idx}".replace(" ", "_")
                    cb_idx += 1
                    sg = (
                        item["length"] < grid_size - subgrid_tol
                        or item["width"] < grid_size - subgrid_tol
                        or item["height"] < grid_size - subgrid_tol
                    )
                    thicken_kv = "THICKEN=.TRUE., " if sg else ""
                    cb_def = COMBUSTIBLE_LIBRARY.get(key, {})
                    bulk_density = cb_def.get("matl", {}).get("DENSITY", 500)
                    lines.append(
                        f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                        f"{z1:.2f},{z2:.2f},\n"
                        f"      {thicken_kv}SURF_IDS='{surf_id}','INERT','INERT',\n"
                        f"      BULK_DENSITY={bulk_density},\n"
                        f"      ID='{cb_id}' /  ! {item.get('name', key)} (story-level)\n"
                    )
                    probe_counters[key] = probe_counters.get(key, 0) + 1
                    pi2 = probe_counters[key]
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    cz = z2
                    lines.append(
                        f"&DEVC XYZ={cx:.2f},{cy:.2f},{cz:.2f}, IOR=3, "
                        f"QUANTITY='WALL TEMPERATURE', ID='STORY_{key}_{pi2:02d}' /\n"
                    )

        # Story-level specialized_components
        for sc_info in story.specialized_components:
            boundary = sc_info.get("boundary")
            if not boundary:
                continue
            sc_key = sc_info.get("key", "")
            comp = SPECIALIZED_COMPONENTS.get(sc_key)
            if not comp:
                continue
            is_rocket = sc_key.startswith("ROCKET_VEHICLE")
            items = []
            for ci in range(sc_info.get("count", 1)):
                items.append({
                    "length": comp.total_length,
                    "width": comp.total_width,
                    "height": comp.total_height,
                    "key": sc_key,
                    "_type": "component",
                    "_comp": comp,
                    "_instance": ci,
                    "_horizontal": is_rocket,
                })
            placed = layout_items_in_fc(boundary, items, margin=1.0, gap=0.5)
            _emit_placed(placed)

        # Story-level combustibles
        for cb_entry in story.combustibles:
            boundary = cb_entry.get("boundary")
            if not boundary:
                continue
            key = cb_entry.get("key", "")
            count = cb_entry.get("count", 1)
            if key not in COMBUSTIBLE_LIBRARY:
                continue
            cb_def = COMBUSTIBLE_LIBRARY[key]
            length = cb_def.get("length", 1.0)
            width = cb_def.get("width", 0.8)
            height = cb_def.get("height", 0.5)
            rotation = cb_entry.get("rotation", 0)
            if rotation == 90:
                length, width = width, length
            items = []
            for _ in range(count):
                items.append({
                    "length": length, "width": width, "height": height,
                    "key": key, "name": cb_def.get("name", key),
                    "_type": "combustible",
                })
            placed = layout_items_in_fc(boundary, items, margin=1.0, gap=0.5)
            _emit_placed(placed)

        lines.append("\n")


    # ------------------------------------------------------------------
    # Heat source
    # ------------------------------------------------------------------
    def _generate_heat_source(self, lines, timer_x: float, timer_y: float, timer_z: float):
        """Generate heat source with timer DEVC and radiation SURF.
        
        Uses template:
        - Timer DEVC to control duration
        - Single radiation SURF 
        - 6 domain VENTs (OPEN for non-heat faces, radiation for heat face)
        """
        from models.heat_source import face_fluxes

        hs = self.bg.heat_source
        azimuth = hs.get("azimuth", 0)
        elevation = hs.get("elevation", 0)
        Q_kw = hs.get("net_heat_flux", 1000)
        duration = hs.get("duration", 1.36)

        fluxes = face_fluxes(azimuth, elevation, Q_kw)
        if not fluxes:
            return

        domain, grid_size, num_meshes = self._compute_mesh()
        x0, x1, y0, y1, z0, z1 = domain

        lines.append(
            f"! ========== 外部强辐射热源 (azimuth={azimuth}°, elevation={elevation}°) ==========\n"
        )

        lines.append("! 辐射控制定时器\n")
        lines.append(
            f"&DEVC ID='TIMER->OUT', QUANTITY='TIME', XYZ={timer_x:.2f},{timer_y:.2f},{timer_z:.2f}, SETPOINT={duration:.2f}, INITIAL_STATE=.TRUE. /\n\n"
        )

        emissivity = hs.get("emissivity", 1.0)
        lines.append(
            f"&SURF ID='radiation',\n"
            f"      NET_HEAT_FLUX={Q_kw:.2f},\n"
            f"      EMISSIVITY={emissivity:.2f},\n"
            f"      COLOR='ORANGE' /\n\n"
        )

        lines.append("! Heat source boundary VENTs\n")
        if azimuth == 90:
            rad_face = "XMAX"
        elif azimuth == 180:
            rad_face = "YMIN"
        elif azimuth == 270:
            rad_face = "XMIN"
        else:
            rad_face = "YMAX"
        face_xb = {
            "XMIN": ("OPEN", x0, x0, y0, y1, z0, z1),
            "XMAX": ("OPEN", x1, x1, y0, y1, z0, z1),
            "YMIN": ("OPEN", x0, x1, y0, y0, z0, z1),
            "YMAX": ("OPEN", x0, x1, y1, y1, z0, z1),
            "ZMIN": ("OPEN", x0, x1, y0, y1, z0, z0),
            "ZMAX": ("OPEN", x0, x1, y0, y1, z1, z1),
        }
        face_xb[rad_face] = ("radiation", *face_xb[rad_face][1:])
        for face_name in ("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"):
            surf, x1, x2, y1, y2, z1, z2 = face_xb[face_name]
            extra = ", DEVC_ID='TIMER->OUT'" if surf == "radiation" else ""
            lines.append(
                f"&VENT ID='Domain Vent [{face_name}]', SURF_ID='{surf}'{extra}, "
                f"XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},{z1:.2f},{z2:.2f} /\n"
            )
        lines.append("\n")

    # ------------------------------------------------------------------
    # MESH computation
    # ------------------------------------------------------------------
    def _compute_mesh(self):
        """Compute domain bounding box from all buildings."""
        bg = self.bg
        buildings = bg.buildings

        if not buildings:
            return [0, 10, 0, 10, 0, 10], 0.5, 1

        x_min = min(b.offset_x - b.wall_thickness for b in buildings)
        x_max = max(b.offset_x + b.length + b.wall_thickness for b in buildings)
        y_min = min(b.offset_y - b.wall_thickness for b in buildings)
        y_max = max(b.offset_y + b.width + b.wall_thickness for b in buildings)
        z_max = max(sum(s.height for s in b.stories) for b in buildings)

        base_grid_size = bg.domain.get("grid_size", 0.1)  # 默认0.1m

        expand_x = 2.0  # 固定2m
        expand_y = 2.0
        expand_z = 2.0

        domain = [
            x_min - expand_x,
            x_max + expand_x,
            y_min - expand_y,
            y_max + expand_y,
            0,
            z_max + expand_z,
        ]

        domain_w = domain[1] - domain[0]
        domain_d = domain[3] - domain[2]
        domain_h = domain[5] - domain[4]

        max_cells_per_mesh = 250000  # 每个mesh最大网格数
        max_total_cells = 1000000  # 总网格上限
        max_meshes = 4  # 最大mesh数
        
        grid_size = base_grid_size
        nx = math.ceil(domain_w / grid_size)
        ny = math.ceil(domain_d / grid_size)
        nz = math.ceil(domain_h / grid_size)
        total_cells = nx * ny * nz

        # 如果总cells超限,增大grid_size重试
        while total_cells > max_total_cells and grid_size < 5.0:
            grid_size *= 1.5
            nx = math.ceil(domain_w / grid_size)
            ny = math.ceil(domain_d / grid_size)
            nz = math.ceil(domain_h / grid_size)
            total_cells = nx * ny * nz

        num_meshes = 1
        if nx * ny * nz > max_cells_per_mesh:
            # 单个mesh超限,需要拆分
            num_meshes = math.ceil((nx * ny * nz) / max_cells_per_mesh)
            num_meshes = min(num_meshes, max_meshes)

        domain = [round(x) for x in domain]
        nx = max(10, math.ceil(domain_w / grid_size))
        ny = max(10, math.ceil(domain_d / grid_size))
        nz = max(10, math.ceil(domain_h / grid_size))
        return domain, grid_size, num_meshes

    # ------------------------------------------------------------------
    # Main generate
    # ------------------------------------------------------------------
    def generate(self) -> str:
        """Generate the complete FDS input file as a string."""
        bg = self.bg
        buildings = bg.buildings

        # Ensure z_offsets are computed
        for b in buildings:
            b.update_z_offsets()

        # Determine CHID with工况信息
        chid = bg.name or "building"
        chid = chid.replace(" ", "_").replace(".", "_").replace("-", "_")
        chid = "".join(c for c in chid if ord(c) < 128) or "building"

        hs = bg.heat_source
        heat_flux_kw = int(hs.get("net_heat_flux", 1000))
        azimuth = int(hs.get("azimuth", 0))
        elevation = int(hs.get("elevation", 0))
        duration = int(hs.get("duration", 0) * 1000)
        sim_time = int(bg.simulation_time)

        chid_suffix = f"q{heat_flux_kw}_a{azimuth}_e{elevation}_d{duration}_t{sim_time}"
        full_chid = f"{chid}_{chid_suffix}"

        title = (
            f"Heat Flux={heat_flux_kw}kW/m2, Azimuth={azimuth}, "
            f"Elevation={elevation}, Duration={hs.get('duration', 0)}s, "
            f"SimTime={sim_time}s"
        )

        lines = []

        # HEAD
        lines.append(
            f"&HEAD CHID='{full_chid}', TITLE='{title}' /\n\n"
        )

        # REAC
        lines.append("! ========== 燃烧反应 ==========\n")
        lines.append("&REAC ID='METHANE', FUEL='METHANE', FORMULA='C1H4' /\n\n")

        # MESH
        domain, grid_size, num_meshes = self._compute_mesh()
        domain_w = domain[1] - domain[0]
        domain_d = domain[3] - domain[2]
        domain_h = domain[5] - domain[4]
        nx = max(10, math.ceil(domain_w / grid_size))
        ny = max(10, math.ceil(domain_d / grid_size))
        nz = max(10, math.ceil(domain_h / grid_size))

        lines.append("! ========== 计算域 ==========\n")
        timer_x = (domain[0] + domain[1]) / 2
        timer_z = max(1.0, domain[4] + 1.0)
        if num_meshes == 1:
            timer_y = (domain[2] + domain[3]) / 2
            lines.append(
                f"&MESH IJK={nx},{ny},{nz}, "
                f"XB={domain[0]:.2f},{domain[1]:.2f},"
                f"{domain[2]:.2f},{domain[3]:.2f},"
                f"{domain[4]:.2f},{domain[5]:.2f} /\n\n"
            )
        else:
            lines.append("! 分割为多个网格以避免内存溢出\n")
            half_ny = ny // 2
            ny1 = half_ny
            ny2 = ny - half_ny
            y_mid = domain[2] + half_ny * grid_size
            # Timer goes in Mesh01 center
            timer_y = (domain[2] + y_mid) / 2
            lines.append(
                f"&MESH ID='Mesh01', IJK={nx},{ny1},{nz}, "
                f"XB={domain[0]:.2f},{domain[1]:.2f},"
                f"{domain[2]:.2f},{y_mid:.2f},"
                f"{domain[4]:.2f},{domain[5]:.2f} /\n"
            )
            lines.append(
                f"&MESH ID='Mesh02', IJK={nx},{ny2},{nz}, "
                f"XB={domain[0]:.2f},{domain[1]:.2f},"
                f"{y_mid:.2f},{domain[3]:.2f},"
                f"{domain[4]:.2f},{domain[5]:.2f} /\n\n"
            )

        # TIME
        lines.append(f"&TIME T_END={bg.simulation_time:.1f} /\n\n")

        # DUMP
        lines.append("&DUMP DT_RESTART=300.0, DT_SL3D=0.25 /\n\n")

        # Heat source (SURF + RAMP + VENT) - 前置方便手动调整
        self._generate_heat_source(lines, timer_x, timer_y, timer_z)

        # Output: measurement devices - 前置方便手动调整
        self._generate_devices(lines)

        # Materials & Surfaces
        self._generate_materials(lines)

        # For each building: geometry
        for bi, b in enumerate(buildings):
            bld_label = (
                f"建筑{bi + 1}: {b.name or b.cn_name}" if len(buildings) > 1 else ""
            )
            if bld_label:
                lines.append(
                    f"\n! ########## {bld_label} (offset={b.offset_x:.1f},{b.offset_y:.1f}) ##########\n"
                )

            # Ground floor slab
            ox, L, oy, W = b.boundary
            t = b.wall_thickness
            lines.append("! ========== 地板 ==========\n")
            lines.append(
                self.gen_box(
                    ox - t / 2,
                    ox + L + t / 2,
                    oy - t / 2,
                    oy + W + t / 2,
                    0,
                    t,
                    "FLOOR",
                )
            )
            lines.append("\n")

            for si, story in enumerate(b.stories):
                z0 = story.z_bottom
                lines.append(
                    f"\n! ========== {story.name} (z={z0:.2f}~{story.z_top:.2f}) ==========\n"
                )

                # Exterior walls + openings
                lines.append("! -- 外墙 --\n")
                self._generate_exterior_walls(b, story, si, lines)

                # Fire compartment walls
                if story.fire_compartments:
                    lines.append("! -- 防火墙 --\n")
                    self._generate_firewalls(b, story, lines)

                # Combustibles (FC-level + story-level)
                self._generate_combustibles(b, story, lines, grid_size=grid_size)
                self._generate_story_combustibles(b, story, lines, grid_size=grid_size)

            # Roof: use the last story's roof
            if b.stories:
                last_story = b.stories[-1]
                lines.append("\n! ========== 屋顶 ==========\n")
                self._generate_roof(b, last_story, lines)
            lines.append("\n")

        # Output: slices
        output = bg.output
        if output.get("slices", True):
            lines.append("! ========== 切片输出 ==========\n")
            lines.append("&SLCF PBZ=1.50, QUANTITY='TEMPERATURE' /\n")
            lines.append("&BNDF QUANTITY='WALL TEMPERATURE' /\n")
            for cs in output.get("custom_slices", []):
                axis = cs.get("axis", "PBX")
                pos = cs.get("position", 0)
                qty = cs.get("quantity", "TEMPERATURE")
                lines.append(f"&SLCF {axis}={pos:.2f}, QUANTITY='{qty}' /\n")
            # 3D volume slices for fire visualization
            if output.get("volume_slices", True):
                domain, dgrid, _ = self._compute_mesh()
                x0, x1, y0, y1, z0, z1 = domain
                half = dgrid / 2
                vol_slices = [
                    ("HRRPUV", "hrr"),
                    ("DENSITY", "density"),
                    ("TEMPERATURE", "temp"),
                    ("RADIATION LOSS", "radiation"),
                ]
                for qty, fyi in vol_slices:
                    lines.append(
                        f"&SLCF QUANTITY='{qty}', VECTOR=.TRUE., CELL_CENTERED=.TRUE.,\n"
                        f"      XB={x0+half:.2f},{x1-half:.2f},{y0+half:.2f},{y1-half:.2f},"
                        f"{z0+half:.2f},{z1-half:.2f}, FYI='{fyi}' /\n"
                    )
            lines.append("\n")

        # TAIL
        lines.append("&TAIL /\n")

        return "".join(lines)

    # ------------------------------------------------------------------
    # Measurement devices (extracted for prepending)
    # ------------------------------------------------------------------
    def _generate_devices(self, lines):
        """Generate measurement devices (DEVC) - called before geometry for easy adjustment."""
        output = self.bg.output
        buildings = self.bg.buildings
        if not output.get("devices", True):
            return

        lines.append("! ========== 测量点 ==========\n")
        if buildings:
            g_xmin = min(b.offset_x for b in buildings)
            g_xmax = max(b.offset_x + b.length for b in buildings)
            g_ymin = min(b.offset_y for b in buildings)
            g_ymax = max(b.offset_y + b.width for b in buildings)
            dev_x = (g_xmin + g_xmax) / 2
            dev_y = (g_ymin + g_ymax) / 2
        else:
            dev_x = dev_y = 0.0
        dev_z = 1.5
        lines.append(
            f"&DEVC XYZ={dev_x:.2f},{dev_y:.2f},{dev_z:.2f}, QUANTITY='TEMPERATURE', ID='center_temp' /\n"
        )
        rad_z = dev_z + 10.0  # elevated position for radiation measurement
        lines.append(
            f"&DEVC XYZ={dev_x:.2f},{dev_y:.2f},{rad_z:.2f}, QUANTITY='RADIATION LOSS', ID='radiation_loss' /\n"
        )
        for i, cd in enumerate(output.get("custom_devices", [])):
            x = cd.get("x", 0)
            y = cd.get("y", 0)
            z = cd.get("z", 0)
            qty = cd.get("quantity", "TEMPERATURE")
            lines.append(
                f"&DEVC XYZ={x:.2f},{y:.2f},{z:.2f}, QUANTITY='{qty}', ID='custom_dev_{i + 1}' /\n"
            )
        lines.append("\n")


# ============================================================
# FDS Validation
# ============================================================
def validate_fds(fds_text: str) -> list:
    """Validate FDS text and return list of warning/error strings."""
    warnings = []
    # Check for required namelists
    required = ["HEAD", "MESH", "TIME", "REAC", "TAIL"]
    for nml in required:
        if f"&{nml}" not in fds_text:
            warnings.append(f"缺少必需的 &{nml} 名称列表")
    # Check T_END > 0
    t_end_match = re.search(r"T_END\s*=\s*([\d.]+)", fds_text)
    if t_end_match:
        if float(t_end_match.group(1)) <= 0:
            warnings.append("T_END 应大于 0")
    # Check XB coordinate ordering (x1 < x2, y1 < y2, z1 < z2)
    xb_pattern = re.compile(
        r"XB\s*=\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)"
    )
    for match in xb_pattern.finditer(fds_text):
        coords = [float(match.group(i)) for i in range(1, 7)]
        if coords[0] > coords[1]:
            warnings.append(f"XB坐标错误: X1({coords[0]:.2f}) > X2({coords[1]:.2f})")
        if coords[2] > coords[3]:
            warnings.append(f"XB坐标错误: Y1({coords[2]:.2f}) > Y2({coords[3]:.2f})")
        if coords[4] > coords[5]:
            warnings.append(f"XB坐标错误: Z1({coords[4]:.2f}) > Z2({coords[5]:.2f})")

    # Check SURF_ID references exist
    surf_defs = set(re.findall(r"&SURF\s+ID='([^']+)'", fds_text))
    surf_refs = set(re.findall(r"SURF_ID='([^']+)'", fds_text))
    # Also collect from SURF_IDS
    for m in re.finditer(
        r"SURF_IDS='([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'", fds_text
    ):
        for g in m.groups():
            surf_refs.add(g)
    # Remove built-in surfaces
    builtin_surfs = {"INERT", "OPEN", "MIRROR", "PERIODIC"}
    missing_surfs = surf_refs - surf_defs - builtin_surfs
    for s in missing_surfs:
        warnings.append(f"引用了未定义的 SURF_ID: '{s}'")

    # Check MATL_ID references
    matl_defs = set(re.findall(r"&MATL\s+ID='([^']+)'", fds_text))
    matl_refs = set(re.findall(r"MATL_ID='([^']+)'", fds_text))
    missing_matls = matl_refs - matl_defs
    for m in missing_matls:
        warnings.append(f"引用了未定义的 MATL_ID: '{m}'")

    # Check duplicate IDs (skip RAMP entries which share IDs by design)
    id_pattern = re.compile(r"&(?!RAMP)\w+[^/]*\bID='([^']+)'")
    all_ids = id_pattern.findall(fds_text)
    seen = set()
    for id_val in all_ids:
        if id_val in seen:
            warnings.append(f"重复的 ID: '{id_val}'")
        seen.add(id_val)
    # Check namelist closure (every & has matching /)
    open_count = fds_text.count("&")
    close_count = fds_text.count(" /")
    if open_count > close_count + 2:  # allow some tolerance
        warnings.append(
            f"可能存在未闭合的名称列表 (& 数量: {open_count}, / 数量约: {close_count})"
        )
    return warnings
