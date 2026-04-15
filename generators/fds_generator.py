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
from models.building import BuildingGroup, Building, Story, Opening, FireCompartment, Roof
from models.geometry import detect_coplanar_openings, wall_length_for_building, wall_length_for_fc, resolve_negative_offset, is_coplanar
from models.materials import MATERIAL_LIBRARY, COMBUSTIBLE_LIBRARY
from models.combustibles import SPECIALIZED_COMPONENTS


# 5cm redundancy expansion in the wall-normal direction for HOLEs
REDUNDANCY = 0.05


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
                self.bg = BuildingGroup.from_dict(bg if isinstance(bg, dict) else bg.to_dict())
            # Copy top-level fields from legacy model if present
            if hasattr(building_group, "heat_source") and building_group.heat_source:
                self.bg.heat_source = building_group.heat_source
            if hasattr(building_group, "simulation_time"):
                self.bg.simulation_time = building_group.simulation_time
            if hasattr(building_group, "domain"):
                self.bg.domain = building_group.domain
            if hasattr(building_group, "output"):
                self.bg.output = building_group.output
            if hasattr(building_group, "chid"):
                self._chid_override = building_group.chid
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

        lines.append("! ========== 材料定义 ==========\n")

        # Wall / structural materials
        all_structural = wall_matl_keys | component_matl_keys
        for mat_name in sorted(all_structural):
            if mat_name in MATERIAL_LIBRARY:
                mat = MATERIAL_LIBRARY[mat_name]
                lines.append(
                    f"&MATL ID='{mat_name}', DENSITY={mat['DENSITY']}, "
                    f"CONDUCTIVITY={mat['CONDUCTIVITY']}, SPECIFIC_HEAT={mat['SPECIFIC_HEAT']} /\n"
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
                lines.append(f"&SURF ID='{surf_name}', MATL_ID='{mat_name}', THICKNESS={thick} /  ! {desc}\n")

        # Specialized component surfaces
        comp_surfs_done = set()
        for mat_key in sorted(component_matl_keys):
            surf_id = f"{mat_key}_SURF"
            if surf_id in comp_surfs_done:
                continue
            mat = MATERIAL_LIBRARY.get(mat_key) or COMBUSTIBLE_LIBRARY.get(mat_key)
            if mat:
                thick = mat.get("THICKNESS", 0.1)
                lines.append(f"&SURF ID='{surf_id}', MATL_ID='{mat_key}', THICKNESS={thick} /\n")
                comp_surfs_done.add(surf_id)

        # Combustible MATL / SURF definitions
        if combustible_keys:
            lines.append("\n! ========== 可燃物材料/表面 ==========\n")
            for ck in sorted(combustible_keys):
                if ck not in COMBUSTIBLE_LIBRARY:
                    continue
                cb_def = COMBUSTIBLE_LIBRARY[ck]
                mt = cb_def.get("matl", {})
                if not mt:
                    continue
                matl_id = f"MATL_{ck}"
                surf_id = f"SURF_{ck}"
                lines.append(
                    f"&MATL ID='{matl_id}',\n"
                    f"      DENSITY={mt.get('DENSITY', 1000)},\n"
                    f"      CONDUCTIVITY={mt.get('CONDUCTIVITY', 0.2)},\n"
                    f"      SPECIFIC_HEAT={mt.get('SPECIFIC_HEAT', 1.0)} /\n\n"
                )
                hrrpua = cb_def.get("hrrpua", 300)
                color = cb_def.get("color", "RED")
                lines.append(
                    f"&SURF ID='{surf_id}',\n"
                    f"      MATL_ID='{matl_id}',\n"
                    f"      THICKNESS=0.05,\n"
                    f"      IGNITION_TEMPERATURE=250.0,\n"
                    f"      HRRPUA={hrrpua},\n"
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
            self._emit_obst(lines, obst_bounds, surf="WALL", comment=f"ext wall {wall_id}")
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
            return [ox + w_off, ox + w_off + w,
                    oy - t - REDUNDANCY, oy + REDUNDANCY,
                    z0 + h_off, z0 + h_off + h]
        elif wall_id == "y_max":
            return [ox + w_off, ox + w_off + w,
                    oy + W - REDUNDANCY, oy + W + t + REDUNDANCY,
                    z0 + h_off, z0 + h_off + h]
        elif wall_id == "x_min":
            return [ox - t - REDUNDANCY, ox + REDUNDANCY,
                    oy + w_off, oy + w_off + w,
                    z0 + h_off, z0 + h_off + h]
        else:  # x_max
            return [ox + L - REDUNDANCY, ox + L + t + REDUNDANCY,
                    oy + w_off, oy + w_off + w,
                    z0 + h_off, z0 + h_off + h]

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
                self._emit_obst(lines,
                    [ox + x_min - ft/2, ox + x_min + ft/2, oy + y_min, oy + y_max, z0, z1],
                    surf="WALL", comment=f"firewall {fc.name} x_min")
            # x_max boundary
            if abs(x_max - L) > 1e-6 and not is_coplanar(fc.boundary, L, W, "x_max"):
                self._emit_obst(lines,
                    [ox + x_max - ft/2, ox + x_max + ft/2, oy + y_min, oy + y_max, z0, z1],
                    surf="WALL", comment=f"firewall {fc.name} x_max")
            # y_min boundary
            if y_min > 0 and not is_coplanar(fc.boundary, L, W, "y_min"):
                self._emit_obst(lines,
                    [ox + x_min, ox + x_max, oy + y_min - ft/2, oy + y_min + ft/2, z0, z1],
                    surf="WALL", comment=f"firewall {fc.name} y_min")
            # y_max boundary
            if abs(y_max - W) > 1e-6 and not is_coplanar(fc.boundary, L, W, "y_max"):
                self._emit_obst(lines,
                    [ox + x_min, ox + x_max, oy + y_max - ft/2, oy + y_max + ft/2, z0, z1],
                    surf="WALL", comment=f"firewall {fc.name} y_max")

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
            return [wx - ft/2 - REDUNDANCY, wx + ft/2 + REDUNDANCY,
                    oy + y_min + w_off, oy + y_min + w_off + w,
                    z0 + h_off, z0 + h_off + h]
        elif wall_id == "x_max":
            wx = ox + x_max
            return [wx - ft/2 - REDUNDANCY, wx + ft/2 + REDUNDANCY,
                    oy + y_min + w_off, oy + y_min + w_off + w,
                    z0 + h_off, z0 + h_off + h]
        elif wall_id == "y_min":
            wy = oy + y_min
            return [ox + x_min + w_off, ox + x_min + w_off + w,
                    wy - ft/2 - REDUNDANCY, wy + ft/2 + REDUNDANCY,
                    z0 + h_off, z0 + h_off + h]
        else:  # y_max
            wy = oy + y_max
            return [ox + x_min + w_off, ox + x_min + w_off + w,
                    wy - ft/2 - REDUNDANCY, wy + ft/2 + REDUNDANCY,
                    z0 + h_off, z0 + h_off + h]

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
        self._emit_obst(lines,
            [ox - t/2, ox + L + t/2, oy - t/2, oy + W + t/2, z, z + roof.thickness],
            surf="ROOF", comment="roof slab")

        # Roof openings (HOLEs for stairwells, skylights, etc.)
        for ro in roof.openings:
            bnd = ro.get("boundary", ro.get("bnd", [0, 0, 0, 0]))
            self._emit_hole(lines,
                [ox + bnd[0], ox + bnd[0] + bnd[1],
                 oy + bnd[2], oy + bnd[2] + bnd[3],
                 z - 0.05, z + roof.thickness + 0.05],
                comment="roof opening")

    # ------------------------------------------------------------------
    # Combustibles (from fire compartment data)
    # ------------------------------------------------------------------
    def _generate_combustibles(self, building, story, lines):
        """Generate combustible and specialized component OBSTs per FC.

        Specialized components are laid out first (priority), then combustibles
        fill the remaining space. Both share the same layout grid.
        """
        from models.geometry import layout_items_in_fc
        ox, L, oy, W = building.boundary
        z0 = story.z_bottom

        for fc in story.fire_compartments:
            if not fc.combustibles and not fc.specialized_components:
                continue

            # Build unified item list: specialized first (priority), then combustibles
            all_items = []

            # 1. Specialized components (priority)
            for sc_info in fc.specialized_components:
                key = sc_info.get("key", "")
                comp = SPECIALIZED_COMPONENTS.get(key)
                if not comp:
                    continue
                for ci in range(sc_info.get("count", 1)):
                    all_items.append({
                        "length": comp.total_length,
                        "width": comp.total_width,
                        "height": comp.total_height,
                        "key": key,
                        "_type": "component",
                        "_comp": comp,
                        "_instance": ci,
                    })

            # 2. Combustibles
            for cb_entry in fc.combustibles:
                key = cb_entry.get("key", "")
                count = cb_entry.get("count", 1)
                if key not in COMBUSTIBLE_LIBRARY:
                    continue
                cb_def = COMBUSTIBLE_LIBRARY[key]
                for _ in range(count):
                    all_items.append({
                        "length": cb_def.get("length", 1.0),
                        "width": cb_def.get("width", 0.8),
                        "height": cb_def.get("height", 0.5),
                        "key": key,
                        "name": cb_def.get("name", key),
                        "_type": "combustible",
                    })

            placed = layout_items_in_fc(fc.boundary, all_items, margin=1.0, gap=0.5)

            lines.append(f"! -- 可燃物与组件 ({fc.name}) --\n")
            cb_idx = 0
            for item in placed:
                if item.get("_type") == "component":
                    comp = item["_comp"]
                    ci = item["_instance"]
                    key = item["key"]
                    lines.append(f"! {comp.name} #{ci + 1}\n")
                    for pi, part in enumerate(comp.parts):
                        px = ox + item["x"] + part.dx
                        py = oy + item["y"] + part.dy
                        pz = z0 + part.dz
                        surf = part.surf_id or "INERT"
                        lines.append(
                            f"&OBST XB={px:.2f},{px + part.length:.2f},"
                            f"{py:.2f},{py + part.width:.2f},"
                            f"{pz:.2f},{pz + part.height:.2f},\n"
                            f"      SURF_ID='{surf}',\n"
                            f"      ID='{key}_{ci}_{pi}' /\n"
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
                    lines.append(
                        f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                        f"{z1:.2f},{z2:.2f},\n"
                        f"      SURF_IDS='{surf_id}','INERT','INERT',\n"
                        f"      ID='{cb_id}' /  ! {item.get('name', key)}\n"
                    )
                    cb_idx += 1

    # ------------------------------------------------------------------
    # Heat source
    # ------------------------------------------------------------------
    def _generate_heat_source(self, lines):
        """Generate external heat source (radiation panel)."""
        hs = self.bg.heat_source
        if not hs.get("enabled", False):
            return

        buildings = self.bg.buildings
        if not buildings:
            return

        lines.append("! ========== 外部强辐射热源 ==========\n")

        # Compute group bounding box
        g_xmin = min(b.offset_x for b in buildings)
        g_xmax = max(b.offset_x + b.length for b in buildings)
        g_ymin = min(b.offset_y for b in buildings)
        g_ymax = max(b.offset_y + b.width for b in buildings)

        group_cx = (g_xmin + g_xmax) / 2
        group_cy = (g_ymin + g_ymax) / 2
        group_half_L = (g_xmax - g_xmin) / 2
        group_half_W = (g_ymax - g_ymin) / 2

        total_h = max(
            sum(s.height for s in b.stories) for b in buildings
        ) if buildings else 10.0

        distance = hs.get("distance", 3.0)
        width_ratio = hs.get("width_ratio", 1.5)
        height_ratio = hs.get("height_ratio", 1.0)
        elevation = hs.get("elevation", 0)
        duration = hs.get("duration", 1.36)
        azimuth = hs.get("azimuth", 0)

        D = max(group_half_L, group_half_W) + distance
        theta = math.radians(azimuth)
        alpha = math.radians(elevation)

        source_cx = group_cx + D * math.cos(alpha) * math.sin(theta)
        source_cy = group_cy - D * math.cos(alpha) * math.cos(theta)
        source_cz = D * math.sin(alpha)

        temperature = hs.get("temperature", 800.0)
        if hs.get("radiation_flux") and "temperature" not in hs:
            flux_val = hs.get("radiation_flux")
            temperature = 1000.0 if flux_val > 20000 else 800.0

        if duration > 0:
            lines.append(f"&RAMP ID='HEAT_RAMP', T=0, F=1.0 /\n")
            lines.append(f"&RAMP ID='HEAT_RAMP', T={duration:.2f}, F=1.0 /\n")
            lines.append(f"&RAMP ID='HEAT_RAMP', T={duration + 1:.2f}, F=0.0 /\n\n")

        lines.append("&SURF ID='HEAT_SOURCE',\n")
        lines.append(f"      TMP_FRONT={temperature:.1f}")
        if duration > 0:
            lines.append(",\n      RAMP_T='HEAT_RAMP'")
        lines.append(",\n      COLOR='ORANGE' /\n\n")

        # Strip geometry
        az_rad = math.radians(azimuth)
        perp_x = -math.sin(az_rad + math.pi / 2)
        perp_y = math.cos(az_rad + math.pi / 2)
        norm_x = -math.sin(az_rad)
        norm_y = math.cos(az_rad)

        source_W = 2 * (abs(group_half_L * perp_x) + abs(group_half_W * perp_y))
        if width_ratio > 1.0:
            source_W *= width_ratio
        source_H = total_h * height_ratio

        n_cols = 1 if azimuth % 90 == 0 else max(5, int(source_W / 0.5))
        n_rows = 1 if elevation == 0 else max(5, int(source_H / 0.5))

        strip_w = source_W / n_cols
        dh = source_H / n_rows

        elev_rad = math.radians(elevation)

        lines.append(f"! 热源: 方位角{azimuth}°, 距离{distance}m, 仰角{elevation}°\n")

        if elevation > 0:
            tan_alpha = math.tan(elev_rad)
            cos_alpha = math.cos(elev_rad)
            thickness = dh / cos_alpha if cos_alpha > 1e-10 else 0.2
            for row in range(n_rows):
                z_lo = row * dh
                z_hi = (row + 1) * dh
                fwd_offset = row * dh / tan_alpha if tan_alpha > 1e-10 else 0
                for col in range(n_cols):
                    perp_pos = -source_W / 2 + (col + 0.5) * strip_w
                    cx = source_cx + perp_x * perp_pos + norm_x * fwd_offset
                    cy = source_cy + perp_y * perp_pos + norm_y * fwd_offset
                    obst_x1 = cx - perp_x * strip_w / 2 - norm_x * thickness / 2
                    obst_x2 = cx + perp_x * strip_w / 2 + norm_x * thickness / 2
                    obst_y1 = cy - perp_y * strip_w / 2 - norm_y * thickness / 2
                    obst_y2 = cy + perp_y * strip_w / 2 + norm_y * thickness / 2
                    x1, x2 = min(obst_x1, obst_x2), max(obst_x1, obst_x2)
                    y1, y2 = min(obst_y1, obst_y2), max(obst_y1, obst_y2)
                    lines.append(self.gen_box(x1, x2, y1, y2,
                                              source_cz + z_lo, source_cz + z_hi,
                                              "HEAT_SOURCE"))
        else:
            thickness = 0.2
            for row in range(n_rows):
                z_lo = row * dh
                z_hi = (row + 1) * dh
                for col in range(n_cols):
                    perp_pos = -source_W / 2 + (col + 0.5) * strip_w
                    cx = source_cx + perp_x * perp_pos
                    cy = source_cy + perp_y * perp_pos
                    obst_x1 = cx - perp_x * strip_w / 2 - norm_x * thickness / 2
                    obst_x2 = cx + perp_x * strip_w / 2 + norm_x * thickness / 2
                    obst_y1 = cy - perp_y * strip_w / 2 - norm_y * thickness / 2
                    obst_y2 = cy + perp_y * strip_w / 2 + norm_y * thickness / 2
                    x1, x2 = min(obst_x1, obst_x2), max(obst_x1, obst_x2)
                    y1, y2 = min(obst_y1, obst_y2), max(obst_y1, obst_y2)
                    lines.append(self.gen_box(x1, x2, y1, y2,
                                              source_cz + z_lo, source_cz + z_hi,
                                              "HEAT_SOURCE"))
        lines.append("\n")

    # ------------------------------------------------------------------
    # MESH computation
    # ------------------------------------------------------------------
    def _compute_mesh(self):
        """Compute domain bounding box from all buildings."""
        bg = self.bg
        buildings = bg.buildings

        if not buildings:
            return [0, 10, 0, 10, 0, 10], 0.5

        x_min = min(b.offset_x - b.wall_thickness for b in buildings)
        x_max = max(b.offset_x + b.length + b.wall_thickness for b in buildings)
        y_min = min(b.offset_y - b.wall_thickness for b in buildings)
        y_max = max(b.offset_y + b.width + b.wall_thickness for b in buildings)
        z_max = max(sum(s.height for s in b.stories) for b in buildings)

        grid_size = bg.domain.get("grid_size", 0.5)

        expand_x = max((x_max - x_min) * 0.2, 5.0)
        expand_y = max((y_max - y_min) * 0.2, 5.0)
        expand_z = max(z_max * 0.2, 5.0)

        domain = [
            x_min - expand_x,
            x_max + expand_x,
            y_min - expand_y,
            y_max + expand_y,
            0,
            z_max + expand_z,
        ]

        # Extend for heat source if enabled
        if bg.heat_source.get("enabled", False):
            hs = bg.heat_source
            azimuth = hs.get("azimuth", 0)
            distance = hs.get("distance", 3.0)
            az_rad = math.radians(azimuth)
            dir_x = math.sin(az_rad)
            dir_y = math.cos(az_rad)
            radius = abs((x_max - x_min) / 2 * dir_x) + abs((y_max - y_min) / 2 * dir_y)
            source_ox = (x_max + x_min) / 2 + dir_x * (radius + distance + 15)
            source_oy = (y_max + y_min) / 2 + dir_y * (radius + distance + 15)
            domain[0] = min(domain[0], source_ox - 5)
            domain[1] = max(domain[1], source_ox + 5)
            domain[2] = min(domain[2], source_oy - 5)
            domain[3] = max(domain[3], source_oy + 5)

        return domain, grid_size

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

        # Determine CHID
        chid = getattr(self, "_chid_override", "") or ""
        if not chid:
            if buildings:
                chid = buildings[0].name or "building"
            else:
                chid = "building"
        chid = chid.replace(" ", "_").replace(".", "_").replace("-", "_")
        chid = "".join(c for c in chid if ord(c) < 128) or "building"

        lines = []

        # HEAD
        lines.append(f"&HEAD CHID='{chid}', TITLE='Auto-generated Building Model' /\n\n")

        # REAC
        lines.append("! ========== 燃烧反应 ==========\n")
        lines.append("&REAC FUEL='METHANE',\n      SOOT_YIELD=0.01 /\n\n")

        # MESH
        domain, grid_size = self._compute_mesh()
        domain_w = domain[1] - domain[0]
        domain_d = domain[3] - domain[2]
        domain_h = domain[5] - domain[4]
        nx = max(10, math.ceil(domain_w / grid_size))
        ny = max(10, math.ceil(domain_d / grid_size))
        nz = max(10, math.ceil(domain_h / grid_size))

        lines.append("! ========== 计算域 ==========\n")
        lines.append(
            f"&MESH IJK={nx},{ny},{nz}, "
            f"XB={domain[0]:.2f},{domain[1]:.2f},"
            f"{domain[2]:.2f},{domain[3]:.2f},"
            f"{domain[4]:.2f},{domain[5]:.2f} /\n\n"
        )

        # TIME
        lines.append(f"&TIME T_END={bg.simulation_time:.1f} /\n\n")

        # DUMP
        lines.append("&DUMP DT_DEVC=10, DT_SLCF=10 /\n\n")

        # Materials & Surfaces
        self._generate_materials(lines)

        # For each building: geometry
        for bi, b in enumerate(buildings):
            bld_label = f"建筑{bi + 1}: {b.name or b.cn_name}" if len(buildings) > 1 else ""
            if bld_label:
                lines.append(f"\n! ########## {bld_label} (offset={b.offset_x:.1f},{b.offset_y:.1f}) ##########\n")

            # Ground floor slab
            ox, L, oy, W = b.boundary
            t = b.wall_thickness
            lines.append("! ========== 地板 ==========\n")
            lines.append(self.gen_box(
                ox - t / 2, ox + L + t / 2,
                oy - t / 2, oy + W + t / 2,
                0, t, "FLOOR"
            ))
            lines.append("\n")

            for si, story in enumerate(b.stories):
                z0 = story.z_bottom
                lines.append(f"\n! ========== {story.name} (z={z0:.2f}~{story.z_top:.2f}) ==========\n")

                # Exterior walls + openings
                lines.append("! -- 外墙 --\n")
                self._generate_exterior_walls(b, story, si, lines)

                # Fire compartment walls
                if story.fire_compartments:
                    lines.append("! -- 防火墙 --\n")
                    self._generate_firewalls(b, story, lines)

                # Combustibles
                self._generate_combustibles(b, story, lines)

            # Roof: use the last story's roof
            if b.stories:
                last_story = b.stories[-1]
                lines.append("\n! ========== 屋顶 ==========\n")
                self._generate_roof(b, last_story, lines)
            lines.append("\n")

        # Heat source
        self._generate_heat_source(lines)

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
            lines.append("\n")

        # Output: devices
        if output.get("devices", True):
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
            lines.append(f"&DEVC XYZ={dev_x:.2f},{dev_y:.2f},{dev_z:.2f}, QUANTITY='TEMPERATURE', ID='center_temp' /\n")
            for i, cd in enumerate(output.get("custom_devices", [])):
                x = cd.get("x", 0)
                y = cd.get("y", 0)
                z = cd.get("z", 0)
                qty = cd.get("quantity", "TEMPERATURE")
                lines.append(f"&DEVC XYZ={x:.2f},{y:.2f},{z:.2f}, QUANTITY='{qty}', ID='custom_dev_{i + 1}' /\n")
            lines.append("\n")

        # TAIL
        lines.append("&TAIL /\n")

        return "".join(lines)


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
