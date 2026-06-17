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

# Stefan-Boltzmann constant in kW/m²/K⁴
SIGMA_SB = 5.670374419e-11


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
    # Radiation-source orientation helpers
    # ------------------------------------------------------------------
    def _source_orientation(self):
        """Unit vector pointing toward the external radiation source.

        ``RADIATIVE HEAT FLUX GAS`` gauges on inert targets use this as their
        ``ORIENTATION`` so they face the incoming flux; rockets are laid down
        along its horizontal projection (i.e. nose toward the source / door).

        Azimuth convention matches the heat-source faces / window probe:
        0°→+Y, 90°→+X, 180°→-Y, 270°→-X.  Elevation tilts the vector upward.
        """
        hs = self.bg.heat_source
        az = math.radians(hs.get("azimuth", 0))
        el = math.radians(hs.get("elevation", 0))
        ce = math.cos(el)
        return (ce * math.sin(az), ce * math.cos(az), math.sin(el))

    def _source_horizontal_dir(self):
        """Dominant horizontal axis/sign of the source direction.

        Returns ``("x"|"y", +1|-1)`` — the axis a laid-down rocket lies along
        and the sign its nose points toward (toward the door/source).
        """
        hx, hy, _ = self._source_orientation()
        if abs(hx) >= abs(hy):
            return ("x", 1 if hx >= 0 else -1)
        return ("y", 1 if hy >= 0 else -1)

    @staticmethod
    def _part_box(item, part, ox, oy, z0):
        """World-space box + extents for one component part.

        Honours the item's lay-down orientation (``_horizontal`` / ``_axis`` /
        ``_sign``).  Vertical components keep the native part frame; horizontal
        rockets rotate their long (height) axis onto the chosen ground axis,
        with ``_sign`` < 0 mirroring the nose to the opposite end.

        Returns ``(px, py, pz, ext_x, ext_y, ext_z)``.
        """
        if not item.get("_horizontal"):
            px = ox + item["x"] + part.dx
            py = oy + item["y"] + part.dy
            pz = z0 + part.dz
            return px, py, pz, part.length, part.width, part.height

        comp = item["_comp"]
        axis = item.get("_axis", "x")
        sign = item.get("_sign", 1)
        long_extent = comp.total_height  # rocket's vertical axis becomes ground length
        along = part.dz if sign >= 0 else (long_extent - part.dz - part.height)
        if axis == "x":
            px = ox + item["x"] + along
            py = oy + item["y"] + part.dy
            pz = z0 + part.dx
            return px, py, pz, part.height, part.width, part.length
        # axis == "y"
        py = oy + item["y"] + along
        px = ox + item["x"] + part.dy
        pz = z0 + part.dx
        return px, py, pz, part.width, part.height, part.length

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
            # METHANE species is auto-created by &REAC FUEL='METHANE'.
            # Explicit &SPEC ID='METHANE' would cause ERROR(155) in FDS 6.10.1+
            # (duplicate species ID). The REAC-generated SPEC is referenced
            # via SPEC_ID='METHANE' in the pyrolyzing MATL blocks below.
            surf_spec_id = "METHANE"
            for ck in sorted(combustible_keys):
                if ck not in COMBUSTIBLE_LIBRARY:
                    continue
                cb_def = COMBUSTIBLE_LIBRARY[ck]
                mt = cb_def.get("matl", {})
                if not mt:
                    continue
                surf_id = f"SURF_{ck}"
                density = mt.get("DENSITY", 500)
                conductivity = mt.get("CONDUCTIVITY", 0.2)
                specific_heat = mt.get("SPECIFIC_HEAT", 1.0)
                color = cb_def.get("color", "RED")

                # Non-burnable items (e.g. metal goods) are inert radiation
                # targets: a plain MATL + a non-pyrolysing SURF, no IGNITION /
                # BURN_AWAY.  Their probe is a heat-flux gauge (see below).
                if not cb_def.get("burnable", True):
                    matl_id = f"INERT_{ck}"
                    lines.append(
                        f"&MATL ID='{matl_id}',\n"
                        f" DENSITY={density},\n"
                        f" CONDUCTIVITY={conductivity},\n"
                        f" SPECIFIC_HEAT={specific_heat} /\n\n"
                    )
                    lines.append(
                        f"&SURF ID='{surf_id}',\n"
                        f"      MATL_ID='{matl_id}',\n"
                        f"      THICKNESS=0.05,\n"
                        f"      COLOR='{color}' /\n\n"
                    )
                    continue

                matl_id = f"PYRO_{ck}"
                hoc = mt.get("HEAT_OF_COMBUSTION", 0)
                ignition_temp = cb_def.get("ignition_temp", 250.0)
                hor = max(400, int(hoc * 0.2)) if hoc else 500

                lines.append(
                    f"&MATL ID='{matl_id}',\n"
                    f" DENSITY={density},\n"
                    f" CONDUCTIVITY={conductivity},\n"
                    f" SPECIFIC_HEAT={specific_heat},\n"
                    f" HEAT_OF_REACTION={hor},\n"
                    f" NU_SPEC=0.8,\n"
                    f" SPEC_ID='{surf_spec_id}',\n"
                    f" REFERENCE_TEMPERATURE={ignition_temp:.1f} /\n\n"
                )

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
    def _emit_heat_flux_devc(self, lines, cx, cy, cz, devc_id):
        """Emit a RADIATIVE HEAT FLUX GAS gauge facing the radiation source.

        Sits just above the target top; its ORIENTATION points toward the
        source/door.  Used for every combustible (burnable + metal) and for
        inert specialized components.
        """
        sx, sy, sz = self._source_orientation()
        lines.append(
            f"&DEVC XYZ={cx:.2f},{cy:.2f},{cz + 0.10:.2f},\n"
            f"      QUANTITY='RADIATIVE HEAT FLUX GAS',\n"
            f"      ORIENTATION={sx:.3f},{sy:.3f},{sz:.3f},\n"
            f"      ID='{devc_id}' /\n"
        )

    def _emit_temp_devc(self, lines, cx, cy, cz, devc_id):
        """Emit a gas TEMPERATURE point probe just above an item's top."""
        lines.append(
            f"&DEVC XYZ={cx:.2f},{cy:.2f},{cz + 0.10:.2f}, "
            f"QUANTITY='TEMPERATURE', ID='{devc_id}' /\n"
        )

    def _emit_item_probes(self, lines, cx, cy, cz, base):
        """Two probes above an item: gas temperature + radiative heat flux.

        Applied uniformly to every combustible (burnable and metal).  IDs are
        derived from the OBST base (name-based, unique).
        """
        self._emit_temp_devc(lines, cx, cy, cz, f"T_{base}")
        self._emit_heat_flux_devc(lines, cx, cy, cz, f"HF_{base}")

    def _emit_component(self, lines, item, ox, oy, z0, grid_size, base):
        """Emit one specialized component's OBSTs + its two probes.

        Components are inert single-metal targets; like combustibles they get
        two probes above the top: a gas ``TEMPERATURE`` point and a
        ``RADIATIVE HEAT FLUX GAS`` gauge facing the source.
        """
        subgrid_tol = 1e-6
        comp = item["_comp"]
        ci = item["_instance"]
        lines.append(f"! {comp.name} #{ci + 1}\n")
        bx_lo = by_lo = float("inf")
        bx_hi = by_hi = z_top = -float("inf")
        for pi, part in enumerate(comp.parts):
            px, py, pz, ex, ey, ez = self._part_box(item, part, ox, oy, z0)
            is_subgrid = (
                ex < grid_size - subgrid_tol
                or ey < grid_size - subgrid_tol
                or ez < grid_size - subgrid_tol
            )
            thicken_kv = "THICKEN=.TRUE., " if is_subgrid else ""
            surf = part.surf_id or "INERT"
            lines.append(
                f"&OBST XB={px:.2f},{px + ex:.2f},"
                f"{py:.2f},{py + ey:.2f},"
                f"{pz:.2f},{pz + ez:.2f},\n"
                f" {thicken_kv}SURF_ID='{surf}',\n"
                f" ID='{base}_{pi}' /\n"
            )
            bx_lo, by_lo = min(bx_lo, px), min(by_lo, py)
            bx_hi, by_hi = max(bx_hi, px + ex), max(by_hi, py + ey)
            z_top = max(z_top, pz + ez)
        self._emit_item_probes(
            lines, (bx_lo + bx_hi) / 2, (by_lo + by_hi) / 2, z_top, base
        )

    def _emit_combustible(self, lines, item, ox, oy, z0, grid_size, base):
        """Emit one combustible OBST + its two probes.

        Burnable items keep a pyrolysing surface; non-burnable (metal) items
        are inert blocks.  Either way, two probes are placed above the item:
        a gas ``TEMPERATURE`` point and a ``RADIATIVE HEAT FLUX GAS`` gauge
        facing the source.  Probe IDs are derived from the OBST ID.
        """
        subgrid_tol = 1e-6
        key = item["key"]
        surf_id = f"SURF_{key}"
        cb_def = COMBUSTIBLE_LIBRARY.get(key, {})
        burnable = cb_def.get("burnable", True)
        x1 = ox + item["x"]
        x2 = x1 + item["length"]
        y1 = oy + item["y"]
        y2 = y1 + item["width"]
        z1 = z0
        z2 = z0 + item["height"]
        is_subgrid = (
            item["length"] < grid_size - subgrid_tol
            or item["width"] < grid_size - subgrid_tol
            or item["height"] < grid_size - subgrid_tol
        )
        thicken_kv = "THICKEN=.TRUE., " if is_subgrid else ""
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        label = item.get("name", key)
        if burnable:
            bulk_density = cb_def.get("matl", {}).get("DENSITY", 500)
            lines.append(
                f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                f"{z1:.2f},{z2:.2f},\n"
                f" {thicken_kv}SURF_IDS='{surf_id}','INERT','INERT',\n"
                f" BULK_DENSITY={bulk_density},\n"
                f" ID='{base}' / ! {label}\n"
            )
        else:
            lines.append(
                f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                f"{z1:.2f},{z2:.2f},\n"
                f" {thicken_kv}SURF_ID='{surf_id}',\n"
                f" ID='{base}' / ! {label} (inert target)\n"
            )
        # Two probes above every combustible (burnable + metal).
        self._emit_item_probes(lines, cx, cy, z2, base)

    def _component_item(self, comp, key, ci, horizontal):
        """Build a layout item dict for a specialized component instance.

        When *horizontal* (laid-down rocket), the footprint is rotated so the
        component's vertical (height) axis lies along the source/door axis and
        the layout reserves the correct ground area.
        """
        axis = sign = None
        if horizontal:
            axis, sign = self._source_horizontal_dir()
            if axis == "x":
                fl, fw, fh = comp.total_height, comp.total_width, comp.total_length
            else:
                fl, fw, fh = comp.total_width, comp.total_height, comp.total_length
        else:
            fl, fw, fh = comp.total_length, comp.total_width, comp.total_height
        return {
            "length": fl,
            "width": fw,
            "height": fh,
            "key": key,
            "_type": "component",
            "_comp": comp,
            "_instance": ci,
            "_horizontal": horizontal,
            "_axis": axis,
            "_sign": sign,
        }

    def _generate_combustibles(self, building, story, si, lines, grid_size: float = 0.1, bi: int = 0):
        """Generate combustible and specialized component OBSTs per FC.

        Specialized components are laid out first (priority), then combustibles
        fill the remaining space. Both share the same layout grid.

        Probe placement:
        - Burnable combustibles: a thermocouple (WALL TEMPERATURE) on top.
        - Non-burnable combustibles / specialized components (inert metal):
          a RADIATIVE HEAT FLUX GAS gauge facing the source.

        IDs are ``{key}_B{bi}S{si}_{seq}`` (globally unique, name-based); probe
        IDs prefix ``TC_`` / ``HF_`` onto that base so they never collide with
        the OBST they belong to.

        *grid_size* is the FDS cell size used by the current MESH. OBSTs whose
        smallest dimension is below this size are emitted with
        ``THICKEN=.TRUE.`` so FDS keeps them as at least one cell instead of
        snapping them away.
        """
        from models.geometry import layout_items_in_fc

        ox, L, oy, W = building.boundary
        z0 = story.z_bottom

        # Single running sequence per (building, story) so IDs never collide
        # across fire compartments within the same story.
        tag = f"B{bi}S{si}"
        seq = 0

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
                    all_items.append(self._component_item(comp, key, ci, horizontal))

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
            for item in placed:
                base = f"{item['key']}_{tag}_{seq:03d}".replace(" ", "_")
                if item.get("_type") == "component":
                    self._emit_component(lines, item, ox, oy, z0, grid_size, base)
                else:
                    self._emit_combustible(lines, item, ox, oy, z0, grid_size, base)
                seq += 1

    # ------------------------------------------------------------------
    # Story-level combustibles (with explicit boundary)
    # ------------------------------------------------------------------
    def _generate_story_combustibles(self, building, story, lines, grid_size: float = 0.1, bi: int = 0):
        """Generate story-level combustibles/specialized_components with explicit boundary.

        Each entry has its own ``boundary`` (in building-local coords) defining
        where items of that type are distributed.  This is for areas that are not
        covered by any fire compartment.  Probe/ID rules match
        ``_generate_combustibles``.
        """
        from models.geometry import layout_items_in_fc

        ox, _L, oy, _W = building.boundary
        z0 = story.z_bottom

        if not story.combustibles and not story.specialized_components:
            return

        lines.append(f"! -- Story-level 可燃物与组件 ({story.name}) --\n")
        tag = f"B{bi}STORY"
        seq = 0

        def _emit_placed(placed_items):
            nonlocal seq
            for item in placed_items:
                base = f"{item['key']}_{tag}_{seq:03d}".replace(" ", "_")
                if item.get("_type") == "component":
                    self._emit_component(lines, item, ox, oy, z0, grid_size, base)
                else:
                    self._emit_combustible(lines, item, ox, oy, z0, grid_size, base)
                seq += 1

        # Story-level specialized_components
        for sc_info in story.specialized_components:
            boundary = sc_info.get("boundary")
            if not boundary:
                continue
            sc_key = sc_info.get("key", "")
            comp = SPECIALIZED_COMPONENTS.get(sc_key)
            if not comp:
                continue
            horizontal = sc_key.startswith("ROCKET_VEHICLE")
            items = [
                self._component_item(comp, sc_key, ci, horizontal)
                for ci in range(sc_info.get("count", 1))
            ]
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
        """Generate heat source with timer DEVC and per-face radiation SURF/VENT.

        Supports multi-face radiation via vector decomposition of (azimuth, elevation, Q)
        onto 1-3 domain faces. Each face with non-zero flux gets its own SURF+VENT pair.
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

        if duration > 0:
            lines.append("! 辐射控制定时器\n")
            lines.append(
                f"&DEVC ID='TIMER->OUT', QUANTITY='TIME', XYZ={timer_x:.2f},{timer_y:.2f},{timer_z:.2f}, "
                f"SETPOINT={duration:.2f}, INITIAL_STATE=.TRUE. /\n\n"
            )

        lines.append("! Per-face radiation surfaces\n")
        face_xb = {
            "XMIN": (x0, x0, y0, y1, z0, z1),
            "XMAX": (x1, x1, y0, y1, z0, z1),
            "YMIN": (x0, x1, y0, y0, z0, z1),
            "YMAX": (x0, x1, y1, y1, z0, z1),
            "ZMIN": (x0, x1, y0, y1, z0, z0),
            "ZMAX": (x0, x1, y0, y1, z1, z1),
        }

        emissivity = hs.get("emissivity", 1.0)
        rad_faces = {f for f in fluxes if f != "ZMIN"}
        for face_name in sorted(rad_faces):
            face_flux = fluxes[face_name]
            # Convert net_heat_flux to equivalent fixed surface temperature (K).
            # Matches FDS example back_wall_test_2.fds pattern:
            #   TMP_FRONT + TAU_T=0.0 + HEAT_TRANSFER_COEFFICIENT=0.0
            # No MATL_ID needed - TMP_FRONT directly sets gas-phase temperature at boundary.
            temp_front = face_flux
            surf_id = f"radiation_{face_name}"
            lines.append(
                f"&SURF ID='{surf_id}', TMP_FRONT={temp_front:.0f}, "
                f"TAU_T=-0.01, EMISSIVITY=1.0, "
                f"HEAT_TRANSFER_COEFFICIENT=0.0, COLOR='ORANGE' /\n\n"
            )

        lines.append("! Heat source boundary VENTs\n")
        has_timer = duration > 0
        all_domain_faces = ("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX")
        for face_name in all_domain_faces:
            if face_name in rad_faces:
                surf_id = f"radiation_{face_name}"
                extra = ", DEVC_ID='TIMER->OUT'" if has_timer else ""
            else:
                surf_id = "OPEN"
                extra = ""
            xb = face_xb[face_name]
            lines.append(
                f"&VENT ID='Domain Vent [{face_name}]', SURF_ID='{surf_id}'{extra}, "
                f"XB={xb[0]:.2f},{xb[1]:.2f},{xb[2]:.2f},{xb[3]:.2f},{xb[4]:.2f},{xb[5]:.2f} /\n"
            )
        lines.append("\n")

    # ------------------------------------------------------------------
    # MESH computation
    # ------------------------------------------------------------------
    def _compute_mesh(self):
        """Compute domain bounding box and the MESH partitioning for it.

        Returns:
            (domain, grid_size, num_meshes)
            - domain: integer-rounded [x0,x1,y0,y1,z0,z1] in metres.
            - grid_size: float, metres per cell.  Always positive.
            - num_meshes: 1, 2 or 4 meshes arranged 1×1, 1×2 or 2×2.

        Reading order:
        1. ``bg.domain["num_meshes"]`` (if present) is a USER override.
           Values ``1`` / ``2`` / ``4`` are honoured as-is.
        2. ``bg.domain["grid_size"]`` (if present) overrides the default.
           The default raises to **1.0 m** so the integers stay tractable
           for industrial-scale scenarios.
        3. With no override, the default is **4 meshes (2×2)** for MPI parallel
           execution.  The grid is still grown if the cell count would exceed
           the 1 M-cell budget.
        """
        bg = self.bg
        buildings = bg.buildings

        if not buildings:
            return [0, 10, 0, 10, 0, 10], 1.0, 1

        x_min = min(b.offset_x - b.wall_thickness for b in buildings)
        x_max = max(b.offset_x + b.length + b.wall_thickness for b in buildings)
        y_min = min(b.offset_y - b.wall_thickness for b in buildings)
        y_max = max(b.offset_y + b.width + b.wall_thickness for b in buildings)
        z_max = max(sum(s.height for s in b.stories) for b in buildings)

        base_grid_size = bg.domain.get("grid_size", 1.0)
        if base_grid_size <= 0:
            base_grid_size = 1.0

        expand_x = 2.0
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

        # Round domain bounds to integers so MESH XB coordinates stay tidy.
        domain = [int(round(v)) for v in domain]
        domain_w = domain[1] - domain[0]
        domain_d = domain[3] - domain[2]
        domain_h = domain[5] - domain[4]

        user_num_meshes = bg.domain.get("num_meshes")
        max_meshes = 4
        max_total_cells = 1000000

        grid_size = base_grid_size

        def _cells(dx: float, dy: float, dz: float) -> tuple:
            return (
                max(10, int(round(dx / grid_size))),
                max(10, int(round(dy / grid_size))),
                max(10, int(round(dz / grid_size))),
            )

        nx, ny, nz = _cells(domain_w, domain_d, domain_h)
        total_cells = nx * ny * nz

        if user_num_meshes is None:
            while total_cells > max_total_cells and grid_size < 5.0:
                grid_size *= 1.5
                nx, ny, nz = _cells(domain_w, domain_d, domain_h)
                total_cells = nx * ny * nz

            # Default to 4 meshes (2×2) so runs are MPI-parallel by default.
            num_meshes = max_meshes
        else:
            num_meshes = int(user_num_meshes)
            if num_meshes not in (1, 2, 4):
                num_meshes = min(max(num_meshes, 1), max_meshes)
                if num_meshes >= 3:
                    num_meshes = 4

        nx = max(10, int(round(domain_w / grid_size)))
        ny = max(10, int(round(domain_d / grid_size)))
        nz = max(10, int(round(domain_h / grid_size)))
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
        self._num_meshes = num_meshes  # 保存供启动时查询 MPI 进程数
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
        elif num_meshes == 2:
            lines.append("! 分割为 2 个网格 (Y 方向)\n")
            half_ny = ny // 2
            ny1 = half_ny
            ny2 = ny - half_ny
            y_mid = domain[2] + half_ny * grid_size
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
        else:
            # num_meshes >= 3 → 2×2 网格划分 (X 和 Y 双向分割)
            lines.append("! 分割为 4 个网格 (X×Y 双向分割) 以充分利用多核 MPI\n")
            half_nx = nx // 2
            half_ny = ny // 2
            nx1 = half_nx
            nx2 = nx - half_nx
            ny1 = half_ny
            ny2 = ny - half_ny
            x_mid = domain[0] + half_nx * grid_size
            y_mid = domain[2] + half_ny * grid_size
            # Timer 放在 Mesh01 (左下象限) 中心
            timer_x = (domain[0] + x_mid) / 2
            timer_y = (domain[2] + y_mid) / 2
            lines.append(
                f"&MESH ID='Mesh01', IJK={nx1},{ny1},{nz}, "
                f"XB={domain[0]:.2f},{x_mid:.2f},"
                f"{domain[2]:.2f},{y_mid:.2f},"
                f"{domain[4]:.2f},{domain[5]:.2f} /\n"
            )
            lines.append(
                f"&MESH ID='Mesh02', IJK={nx2},{ny1},{nz}, "
                f"XB={x_mid:.2f},{domain[1]:.2f},"
                f"{domain[2]:.2f},{y_mid:.2f},"
                f"{domain[4]:.2f},{domain[5]:.2f} /\n"
            )
            lines.append(
                f"&MESH ID='Mesh03', IJK={nx1},{ny2},{nz}, "
                f"XB={domain[0]:.2f},{x_mid:.2f},"
                f"{y_mid:.2f},{domain[3]:.2f},"
                f"{domain[4]:.2f},{domain[5]:.2f} /\n"
            )
            lines.append(
                f"&MESH ID='Mesh04', IJK={nx2},{ny2},{nz}, "
                f"XB={x_mid:.2f},{domain[1]:.2f},"
                f"{y_mid:.2f},{domain[3]:.2f},"
                f"{domain[4]:.2f},{domain[5]:.2f} /\n\n"
            )

        # TIME
        lines.append(f"&TIME T_END={bg.simulation_time:.1f} /\n\n")

        # DUMP
        lines.append("&DUMP DT_RESTART=300.0, DT_SL3D=0.25 /\n\n")

        # Heat source (SURF + VENT) - 前置方便手动调整
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
                self._generate_combustibles(b, story, si, lines, grid_size=grid_size, bi=bi)
                self._generate_story_combustibles(b, story, lines, grid_size=grid_size, bi=bi)

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
            lines.append("&SLCF PBZ=1.50, QUANTITY='HRRPUV' /\n")
            lines.append("&BNDF QUANTITY='WALL TEMPERATURE' /\n")
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

        # Window heat flux probe — 暂时移除,探针坐标与网格边界存在偏差需后续debug
        # self._generate_window_flux_probe(lines)

        # TAIL
        lines.append("&TAIL /\n")

        return "".join(lines)

    # ------------------------------------------------------------------
    # Window heat flux probe (nearest opening to radiation source)
    # ------------------------------------------------------------------
    def _generate_window_flux_probe(self, lines):
        """Place an INCIDENT HEAT FLUX probe at the door/window nearest the radiation source.

        The probe sits at the center of the opening on the radiation-facing wall,
        allowing the simulation to report actual incident flux reaching that opening.
        The result is written to ``*_devc.csv`` and picked up by the UI panel.
        """
        hs = self.bg.heat_source
        azimuth = hs.get("azimuth", 0)
        if not self.bg.buildings:
            return

        # Get domain bounds to locate radiation source plane
        domain, _, _ = self._compute_mesh()
        x0, x1, y0, y1, z0, z1 = domain

        # Determine radiation-facing direction
        # azimuth 0° → YMAX (north), 90° → XMAX (east), 180° → YMIN (south), 270° → XMIN (west)
        rad_wall = "y_max"
        rad_plane_coord = y1
        if azimuth == 90:
            rad_wall = "x_max"
            rad_plane_coord = x1
        elif azimuth == 180:
            rad_wall = "y_min"
            rad_plane_coord = y0
        elif azimuth == 270:
            rad_wall = "x_min"
            rad_plane_coord = x0

        # Collect all exterior openings across all buildings/stories
        candidates: list[tuple[float, float, float, float, str]] = []
        for b in self.bg.buildings:
            ox, L, oy, W = b.boundary
            for si, story in enumerate(b.stories):
                story_openings = list(story.openings)
                story_openings += detect_coplanar_openings(b, story)
                z0_s = story.z_bottom

                for op in story_openings:
                    if op.wall != rad_wall:
                        continue
                    w_off, w, h_off, h = op.boundary
                    if rad_wall in ("y_min", "y_max"):
                        wall_len = L
                    else:
                        wall_len = W
                    if w_off < 0:
                        w_off = resolve_negative_offset(w_off, w, wall_len)
                    # Opening center in world coords
                    if rad_wall == "y_min":
                        cx = ox + w_off + w / 2
                        cy = oy
                        dist = oy - rad_plane_coord  # negative if behind plane
                    elif rad_wall == "y_max":
                        cx = ox + w_off + w / 2
                        cy = oy + W
                        dist = rad_plane_coord - (oy + W)
                    elif rad_wall == "x_min":
                        cx = ox
                        cy = oy + w_off + w / 2
                        dist = ox - rad_plane_coord
                    else:
                        cx = ox + L
                        cy = oy + w_off + w / 2
                        dist = rad_plane_coord - (ox + L)
                    cz = z0_s + h_off + h / 2
                    candidates.append((dist, cx, cy, cz, op.type))

        if not candidates:
            return

        # Pick the one with minimum positive distance to radiation plane
        valid = [(d, cx, cy, cz, t) for d, cx, cy, cz, t in candidates if d >= 0]
        if not valid:
            valid = candidates
        valid.sort(key=lambda x: x[0])
        _, cx, cy, cz, otype = valid[0]

        # IOR mapping: gauge faces outward (toward the radiation source)
        ior_map = {"y_min": -2, "y_max": 2, "x_min": -1, "x_max": 1}
        ior = ior_map.get(rad_wall, 2)

        lines.append("! ========== 窗口入射热通量探针 ==========\n")
        # NOTE: 使用 GAUGE HEAT FLUX (气相量) 而非 INCIDENT HEAT FLUX (壁面量),
        # 因为探针位于洞口中心(空腔),没有固体表面支撑 INCIDENT HEAT FLUX 的计算。
        # RADIATIVE 是 &SURF 参数,不能用于 &DEVC,会触发 ERROR(101)
        lines.append(
            f"&DEVC XYZ={cx:.2f},{cy:.2f},{cz:.2f}, IOR={ior}, "
            f"QUANTITY='GAUGE HEAT FLUX', "
            f"ID='window_heat_flux'  ! nearest {otype} to radiation source\n\n"
        )

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
