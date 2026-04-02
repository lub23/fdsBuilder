#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File  : fds_generator.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 2.0
@Desc  : FDS file generator for building models
"""

import re
import math
from models.building import BuildingModel
from models.materials import MATERIAL_LIBRARY
from models.combustibles import SPECIALIZED_COMPONENTS, COMBUSTIBLE_LIBRARY


# ============================================================
# FDS生成器
# ============================================================
class FDSGenerator:
    """FDS文件生成器"""

    def __init__(self, model):
        self.model = model

    def gen_box(self, x1, x2, y1, y2, z1, z2, surf="WALL"):
        return f"&OBST XB={x1:.3f},{x2:.3f},{y1:.3f},{y2:.3f},{z1:.3f},{z2:.3f}, SURF_ID='{surf}' /\n"

    def generate_materials(self) -> str:
        fds = "! ========== 材料定义 ==========\n"
        used_materials = set(self.model.materials.values())
        # Also collect materials used by specialized component parts
        component_matls = set()
        for b in self.model.building_group.buildings:
            for story in b.stories:
                for cb in story.combustibles.items:
                    if cb.component_key and cb.material_key:
                        component_matls.add(cb.material_key)

        for mat_name in used_materials | component_matls:
            if mat_name in MATERIAL_LIBRARY:
                mat = MATERIAL_LIBRARY[mat_name]
                fds += f"&MATL ID='{mat_name}', DENSITY={mat['DENSITY']}, CONDUCTIVITY={mat['CONDUCTIVITY']}, SPECIFIC_HEAT={mat['SPECIFIC_HEAT']} /\n"

        fds += "\n! ========== 表面定义 ==========\n"
        surfaces = {
            "WALL": ("walls", "墙体"),
            "FLOOR": ("floor", "地板"),
            "ROOF": ("roof", "屋顶"),
        }
        for surf_name, (mat_key, desc) in surfaces.items():
            mat_name = self.model.materials.get(mat_key, "CONCRETE")
            if mat_name in MATERIAL_LIBRARY:
                thick = MATERIAL_LIBRARY[mat_name]["THICKNESS"]
                fds += f"&SURF ID='{surf_name}', MATL_ID='{mat_name}', THICKNESS={thick} /  ! {desc}\n"
        # Specialized component surfaces
        comp_surfs_done = set()
        for mat_key in component_matls:
            surf_id = f"{mat_key}_SURF"
            if surf_id not in comp_surfs_done and mat_key in MATERIAL_LIBRARY:
                mat = MATERIAL_LIBRARY[mat_key]
                fds += f"&SURF ID='{surf_id}', MATL_ID='{mat_key}', THICKNESS={mat['THICKNESS']} /\n"
                comp_surfs_done.add(surf_id)
        # Also add standard aliases used in component definitions
        for alias in (
            "PROPELLANT_SURF",
            "GASOLINE_SURF",
            "ELECTROLYTE_SURF",
            "STEEL_SURF",
            "ALUMINUM_SURF",
        ):
            mat_key = alias.replace("_SURF", "")
            if mat_key == "PROPELLANT":
                mat_key = "SOLID_PROPELLANT"
            if alias not in comp_surfs_done and mat_key in component_matls:
                if mat_key in MATERIAL_LIBRARY:
                    mat = MATERIAL_LIBRARY[mat_key]
                    fds += f"&SURF ID='{alias}', MATL_ID='{mat_key}', THICKNESS={mat['THICKNESS']} /\n"
                    comp_surfs_done.add(alias)
        # 每层楼板可能材料不同，生成 FLOOR_xxF 表面
        for story in self.model.stories:
            slab_mat = story.floor_slab.material
            surf_id = f"FLOOR_{story.name}"
            if slab_mat in MATERIAL_LIBRARY:
                thick = MATERIAL_LIBRARY[slab_mat]["THICKNESS"]
                fds += (
                    f"&SURF ID='{surf_id}', MATL_ID='{slab_mat}', THICKNESS={thick} /\n"
                )

        return fds + "\n"

    def generate_specialized_components(self, building, story, z0) -> str:
        """Legacy wrapper - not used directly anymore."""
        return ""

    def _generate_specialized_for_building(self, building, story, z0, ox, oy) -> str:
        """Generate OBST blocks for specialized components with coord offset."""
        sc_list = getattr(building, "specialized_components", [])
        if not sc_list:
            return ""

        L, W = building.length, building.width
        x_off, y_off = building.x_offset, building.y_offset
        fds = "! -- 专用组件 --\n"

        for sc_info in sc_list:
            key = sc_info.get("key", "")
            comp = SPECIALIZED_COMPONENTS.get(key)
            if not comp:
                continue
            comp_x = sc_info.get("x", building.wall_thickness + 1.0)
            comp_y = sc_info.get("y", building.wall_thickness + 1.0)
            count = sc_info.get("count", 1)

            for ci in range(count):
                inst_x = comp_x + ci * (comp.total_length + 2.0)
                fds += f"! {comp.name} #{ci + 1}\n"
                for pi, part in enumerate(comp.parts):
                    px = inst_x + part.dx - L / 2 + x_off + ox
                    py = comp_y + part.dy - W / 2 + y_off + oy
                    pz = z0 + part.dz
                    surf = part.surf_id or "INERT"
                    fds += (
                        f"&OBST XB={px:.2f},{px + part.length:.2f},"
                        f"{py:.2f},{py + part.width:.2f},"
                        f"{pz:.2f},{pz + part.height:.2f},\n"
                        f"      SURF_ID='{surf}',\n"
                        f"      ID='{key}_{ci}_{pi}' /\n"
                    )
        return fds

    def _generate_heat_source_shifted(self, ox, oy) -> str:
        """Generate heat source with shifted coordinates and grid strip stitching."""
        hs = self.model.heat_source
        if not hs.get("enabled", False):
            return ""

        fds = "! ========== 外部强辐射热源 ==========\n"
        buildings = self.model.building_group.buildings
        g_xmin = g_ymin = float("inf")
        g_xmax = g_ymax = -float("inf")
        for b in buildings:
            bx = b.x_offset
            by = b.y_offset
            g_xmin = min(g_xmin, bx - b.length / 2)
            g_xmax = max(g_xmax, bx + b.length / 2)
            g_ymin = min(g_ymin, by - b.width / 2)
            g_ymax = max(g_ymax, by + b.width / 2)

        group_cx = (g_xmin + g_xmax) / 2
        group_cy = (g_ymin + g_ymax) / 2
        group_half_L = (g_xmax - g_xmin) / 2
        group_half_W = (g_ymax - g_ymin) / 2
        total_h = self.model.total_height
        distance = hs.get("distance", 3.0)
        width_ratio = hs.get("width_ratio", 1.5)
        height_ratio = hs.get("height_ratio", 1.0)
        elevation = hs.get("elevation", 0)
        duration = hs.get("duration", 1.36)
        azimuth = hs.get("azimuth", 0)

        # T29: 俯仰角彻底修正 - 使用正确的几何公式
        # 辐射源中心坐标：
        # x = bc_x + D * cos(α) * sin(θ)
        # y = bc_y - D * cos(α) * cos(θ)
        # z = bc_z + D * sin(α)
        # 其中 D = 建筑半尺寸 + distance，α=俯仰角，θ=方位角
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
            fds += f"&RAMP ID='HEAT_RAMP', T=0, F=1.0 /\n"
            fds += f"&RAMP ID='HEAT_RAMP', T={duration:.2f}, F=1.0 /\n"
            fds += f"&RAMP ID='HEAT_RAMP', T={duration + 1:.2f}, F=0.0 /\n\n"

        fds += "&SURF ID='HEAT_SOURCE',\n"
        fds += f"      TMP_FRONT={temperature:.1f}"
        if duration > 0:
            fds += ",\n      RAMP_T='HEAT_RAMP'"
        fds += ",\n      COLOR='ORANGE' /\n\n"

        # 使用正确的几何公式计算窄条位置
        az_rad = math.radians(azimuth)
        perp_x = -math.sin(az_rad + math.pi / 2)
        perp_y = math.cos(az_rad + math.pi / 2)

        # Normal direction: from source toward building center
        norm_x = -math.sin(az_rad)
        norm_y = math.cos(az_rad)

        source_W = abs(group_half_L * perp_x) + abs(group_half_W * perp_y)
        if width_ratio > 1.0:
            source_W *= width_ratio
        source_H = total_h * height_ratio

        n_cols = 1 if azimuth == 0 else max(5, int(source_W / 0.5))
        n_rows = 1 if elevation == 0 else max(5, int(source_H / 0.5))

        strip_w = source_W / n_cols
        dh = source_H / n_rows

        elev_rad = math.radians(elevation)

        fds += f"! 热源: 方位角{azimuth}°, 距离{distance}m, 仰角{elevation}°\n"

        if elevation > 0:
            tan_alpha = math.tan(elev_rad)
            cos_alpha = math.cos(elev_rad)
            thickness = dh / cos_alpha if cos_alpha > 1e-10 else 0.2
            for row in range(n_rows):
                z_lo = row * dh
                z_hi = (row + 1) * dh
                # Forward offset along normal for this row
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
                    fds += self.gen_box(
                        x1 + ox,
                        x2 + ox,
                        y1 + oy,
                        y2 + oy,
                        source_cz + z_lo,
                        source_cz + z_hi,
                        "HEAT_SOURCE",
                    )
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
                    fds += self.gen_box(
                        x1 + ox,
                        x2 + ox,
                        y1 + oy,
                        y2 + oy,
                        source_cz + z_lo,
                        source_cz + z_hi,
                        "HEAT_SOURCE",
                    )
        return fds + "\n"

    def generate(self) -> str:
        m = self.model
        buildings = m.building_group.buildings

        # Calculate global domain bounds from all buildings
        g_xmin = g_ymin = float("inf")
        g_xmax = g_ymax = g_zmax = -float("inf")
        for b in buildings:
            bx = b.x_offset
            by = b.y_offset
            g_xmin = min(g_xmin, bx - b.length / 2 - b.wall_thickness / 2)
            g_xmax = max(g_xmax, bx + b.length / 2 + b.wall_thickness / 2)
            g_ymin = min(g_ymin, by - b.width / 2 - b.wall_thickness / 2)
            g_ymax = max(g_ymax, by + b.width / 2 + b.wall_thickness / 2)
            g_zmax = max(g_zmax, b.total_height)

        # Fallback for single building (compat)
        if g_xmin == float("inf"):
            L, W = m.length, m.width
            t = m.wall_thickness
            g_xmin, g_xmax = -L / 2 - t / 2, L / 2 + t / 2
            g_ymin, g_ymax = -W / 2 - t / 2, W / 2 + t / 2
            g_zmax = m.total_height
        else:
            t = buildings[0].wall_thickness if buildings else m.wall_thickness

        total_h = g_zmax
        roof_t = m.roof.get("thickness", 0.2)

        chid = m.chid.replace(" ", "_").replace(".", "_").replace("-", "_")
        chid = "".join(c for c in chid if ord(c) < 128) or "building"

        fds = f"&HEAD CHID='{chid}', TITLE='Auto-generated Building Model' /\n\n"

        fds += "! ========== 燃烧反应 ==========\n"
        fds += "&REAC FUEL='METHANE',\n      SOOT_YIELD=0.01 /\n\n"

        grid_size = m.domain.get("grid_size", 0.5)

        expand_x = max((g_xmax - g_xmin) * 0.2, 5.0)
        expand_y = max((g_ymax - g_ymin) * 0.2, 5.0)
        expand_z = max(total_h * 0.2, 5.0)

        domain_xmin = g_xmin - expand_x
        domain_xmax = g_xmax + expand_x
        domain_ymin = g_ymin - expand_y
        domain_ymax = g_ymax + expand_y
        domain_zmax = total_h + expand_z

        if m.heat_source.get("enabled", False):
            hs = m.heat_source
            azimuth = hs.get("azimuth", 0)
            distance = hs.get("distance", 3.0)

            az_rad = math.radians(azimuth)
            dir_x = math.sin(az_rad)
            dir_y = math.cos(az_rad)
            radius = abs((g_xmax - g_xmin) / 2 * dir_x) + abs(
                (g_ymax - g_ymin) / 2 * dir_y
            )
            source_ox = (g_xmax + g_xmin) / 2 + dir_x * (radius + distance + 15)
            source_oy = (g_ymax + g_ymin) / 2 + dir_y * (radius + distance + 15)
            domain_xmin = min(domain_xmin, source_ox - 5)
            domain_xmax = max(domain_xmax, source_ox + 5)
            domain_ymin = min(domain_ymin, source_oy - 5)
            domain_ymax = max(domain_ymax, source_oy + 5)
        ox = -domain_xmin
        oy = -domain_ymin
        domain_w = domain_xmax - domain_xmin
        domain_d = domain_ymax - domain_ymin
        nx = max(10, math.ceil(domain_w / grid_size))
        ny = max(10, math.ceil(domain_d / grid_size))
        nz = max(10, math.ceil(domain_zmax / grid_size))
        mesh = [nx, ny, nz]

        fds += "! ========== 计算域 ==========\n"
        fds += (
            f"&MESH IJK={mesh[0]},{mesh[1]},{mesh[2]}, "
            f"XB=0.00,{domain_w:.2f},"
            f"0.00,{domain_d:.2f},"
            f"0.00,{domain_zmax:.2f} /\n\n"
        )

        fds += f"&TIME T_END={m.simulation_time:.1f} /\n\n"

        fds += "&DUMP DT_DEVC=10, DT_SLCF=10 /\n\n"

        fds += self.generate_materials()

        # Collect combustible materials/surfaces across all buildings
        all_combustible_matls = {}
        all_combustible_surfs = {}
        first_cb_center = None

        for b in buildings:
            for story in b.stories:
                for cb in story.combustibles.items:
                    # Skip component parts - they use specialized SURFs
                    if cb.component_key:
                        continue
                    matl_id = f"MATL_{cb.preset_key}"
                    surf_id = f"SURF_{cb.preset_key}"
                    if matl_id not in all_combustible_matls:
                        all_combustible_matls[matl_id] = cb
                    if surf_id not in all_combustible_surfs:
                        all_combustible_surfs[surf_id] = cb
                    if first_cb_center is None and not cb.component_key:
                        first_cb_center = (
                            cb.x - b.length / 2 + cb.length / 2 + b.x_offset + ox,
                            cb.y - b.width / 2 + cb.width / 2 + b.y_offset + oy,
                            story.z_bottom + cb.z + cb.height / 2,
                        )

        if all_combustible_matls:
            fds += "! ========== 可燃物材料/表面 ==========\n"
            for matl_id, cb in all_combustible_matls.items():
                mt = cb.matl
                fds += (
                    f"&MATL ID='{matl_id}',\n"
                    f"      DENSITY={mt['DENSITY']},\n"
                    f"      CONDUCTIVITY={mt['CONDUCTIVITY']},\n"
                    f"      SPECIFIC_HEAT={mt['SPECIFIC_HEAT']} /\n\n"
                )
            for surf_id, cb in all_combustible_surfs.items():
                fds += (
                    f"&SURF ID='{surf_id}',\n"
                    f"      MATL_ID='MATL_{cb.preset_key}',\n"
                    f"      THICKNESS=0.05,\n"
                    f"      IGNITION_TEMPERATURE=250.0,\n"
                    f"      HRRPUA={cb.hrrpua},\n"
                    f"      COLOR='{cb.color}' /\n\n"
                )

        # Generate geometry for each building
        for bi, b in enumerate(buildings):
            L, W, t = b.length, b.width, b.wall_thickness
            x_off, y_off = b.x_offset, b.y_offset
            b_total_h = b.total_height
            b_roof_t = b.roof.get("thickness", 0.2)

            bld_label = f"建筑{bi + 1}: {b.name}" if len(buildings) > 1 else ""
            if bld_label:
                fds += f"\n! ########## {bld_label} (offset={x_off:.1f},{y_off:.1f}) ##########\n"

            # Ground floor
            fds += "! ========== 地板 ==========\n"
            fds += self.gen_box(
                x_off - L / 2 - t / 2 + ox,
                x_off + L / 2 + t / 2 + ox,
                y_off - W / 2 - t / 2 + oy,
                y_off + W / 2 + t / 2 + oy,
                0,
                t,
                "FLOOR",
            )
            fds += "\n"

            for si, story in enumerate(b.stories):
                z0 = story.z_bottom + t  # shift z by floor thickness
                slab_t = story.floor_slab.thickness

                fds += f"\n! ========== {story.name} (z={z0:.2f}~{z0 + story.height:.2f}) ==========\n"

                if si > 0:
                    fds += f"! -- 楼板 --\n"
                    fds += self.gen_box(
                        x_off - L / 2 - t / 2 + ox,
                        x_off + L / 2 + t / 2 + ox,
                        y_off - W / 2 - t / 2 + oy,
                        y_off + W / 2 + t / 2 + oy,
                        z0 - slab_t,
                        z0,
                        f"FLOOR_{story.name}",
                    )
                    for hole in story.floor_slab.openings:
                        hx = hole["x"] - L / 2 + x_off + ox
                        hy = hole["y"] - W / 2 + y_off + oy
                        fds += (
                            f"&HOLE XB={hx:.2f},{hx + hole['length']:.2f},"
                            f"{hy:.2f},{hy + hole['width']:.2f},"
                            f"{z0 - slab_t - 0.01:.2f},{z0 + 0.01:.2f} /  ! {hole.get('name', '洞口')}\n"
                        )

                    # Auto-generate stairwell HOLE for 2F+
                    sw_x = t + 0.5 - L / 2 + x_off + ox
                    sw_y = t + 0.5 - W / 2 + y_off + oy
                    sw_l, sw_w = min(4.0, L * 0.3), min(3.0, W * 0.3)
                    fds += (
                        f"&HOLE XB={sw_x:.2f},{sw_x + sw_l:.2f},"
                        f"{sw_y:.2f},{sw_y + sw_w:.2f},"
                        f"{z0 - slab_t - 0.01:.2f},{z0 + 0.01:.2f} /  ! 自动楼梯口\n"
                    )

                fds += f"! -- 墙体 --\n"
                for wi in range(len(story.walls)):
                    fds += self._generate_wall_for_building(b, wi, si, ox, oy, t)

                if story.combustibles.items:
                    fds += f"! -- 可燃物 --\n"
                    for cb in story.combustibles.items:
                        x1 = cb.x - L / 2 + x_off + ox
                        x2 = cb.x + cb.length - L / 2 + x_off + ox
                        y1 = cb.y - W / 2 + y_off + oy
                        y2 = cb.y + cb.width - W / 2 + y_off + oy
                        z1 = cb.z + z0
                        z2 = z1 + cb.height
                        # Component parts use their specific SURF_ID
                        if cb.component_key and cb.material_key:
                            surf = f"{cb.material_key}_SURF"
                            fds += (
                                f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                                f"{z1:.2f},{z2:.2f},\n"
                                f"      SURF_ID='{surf}',\n"
                                f"      ID='{cb.id}' /  ! {cb.name}\n"
                            )
                        else:
                            fds += (
                                f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                                f"{z1:.2f},{z2:.2f},\n"
                                f"      SURF_IDS='SURF_{cb.preset_key}','INERT','INERT',\n"
                                f"      ID='{cb.id}' /  ! {cb.name}\n"
                            )

                # Specialized components
                fds += self._generate_specialized_for_building(b, story, z0, ox, oy)
            fds += "\n! ========== 屋顶 ==========\n"
            fds += self.gen_box(
                x_off - L / 2 - t / 2 + ox,
                x_off + L / 2 + t / 2 + ox,
                y_off - W / 2 - t / 2 + oy,
                y_off + W / 2 + t / 2 + oy,
                b_total_h + t,
                b_total_h + t + b_roof_t,
                "ROOF",
            )
            fds += "\n"

        # Heat source (pass ox, oy for coord shift)
        fds += self._generate_heat_source_shifted(ox, oy)

        # Output: one default SLCF + BNDF, one default DEVC, then custom
        if m.output.get("slices", True):
            fds += "! ========== 切片输出 ==========\n"
            fds += "&SLCF PBZ=1.50, QUANTITY='TEMPERATURE' /\n"
            fds += "&BNDF QUANTITY='WALL TEMPERATURE' /\n"
            for cs in m.output.get("custom_slices", []):
                axis = cs.get("axis", "PBX")
                pos = cs.get("position", 0)
                qty = cs.get("quantity", "TEMPERATURE")
                fds += f"&SLCF {axis}={pos:.2f}, QUANTITY='{qty}' /\n"
            fds += "\n"

        if m.output.get("devices", True):
            fds += "! ========== 测量点 ==========\n"
            dev_x = ox + (g_xmin + g_xmax) / 2
            dev_y = oy + (g_ymin + g_ymax) / 2
            dev_z = 1.5
            fds += f"&DEVC XYZ={dev_x:.2f},{dev_y:.2f},{dev_z:.2f}, QUANTITY='TEMPERATURE', ID='center_temp' /\n"
            for i, cd in enumerate(m.output.get("custom_devices", [])):
                x = cd.get("x", 0)
                y = cd.get("y", 0)
                z = cd.get("z", 0)
                qty = cd.get("quantity", "TEMPERATURE")
                fds += f"&DEVC XYZ={x:.2f},{y:.2f},{z:.2f}, QUANTITY='{qty}', ID='custom_dev_{i + 1}' /\n"
            fds += "\n"

        fds += "&TAIL /\n"
        return fds

    def _generate_wall_for_building(
        self, building, wall_index, story_index=0, ox=0.0, oy=0.0, floor_t=0.0
    ) -> str:
        """Generate wall FDS code for a specific building (with offset)."""
        L, W = building.length, building.width
        t = building.wall_thickness
        x_off, y_off = building.x_offset, building.y_offset

        story = building.stories[story_index]
        wall = story.walls[wall_index]
        z0 = story.z_bottom + floor_t

        x1, y1, x2, y2 = wall["x1"], wall["y1"], wall["x2"], wall["y2"]
        thick = wall.get("thickness", t)
        wall_h = wall.get("height", story.height)

        fx1, fy1 = x1 - L / 2 + x_off + ox, y1 - W / 2 + y_off + oy
        fx2, fy2 = x2 - L / 2 + x_off + ox, y2 - W / 2 + y_off + oy

        openings = [o for o in story.openings if o["wall_index"] == wall_index]

        wall_len = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if wall_len < 0.01:
            return ""

        is_horizontal = abs(y2 - y1) < abs(x2 - x1)

        if not openings:
            if is_horizontal:
                return self.gen_box(
                    min(fx1, fx2) - thick / 2,
                    max(fx1, fx2) + thick / 2,
                    fy1 - thick / 2,
                    fy1 + thick / 2,
                    z0,
                    z0 + wall_h,
                    "WALL",
                )
            else:
                return self.gen_box(
                    fx1 - thick / 2,
                    fx1 + thick / 2,
                    min(fy1, fy2) + thick / 2,
                    max(fy1, fy2) - thick / 2,
                    z0,
                    z0 + wall_h,
                    "WALL",
                )

        fds = ""
        z_splits = [0, wall_h]
        for o in openings:
            z_b = o.get("z_bottom", 0)
            z_t = z_b + o["height"]
            z_splits.extend([z_b, z_t])
        z_splits = sorted(set(z_splits))

        for zi in range(len(z_splits) - 1):
            z_low, z_up = z_splits[zi], z_splits[zi + 1]

            cuts = []
            for o in openings:
                z_b = o.get("z_bottom", 0)
                z_t = z_b + o["height"]
                if not (z_up <= z_b or z_low >= z_t):
                    pos = o["position"]
                    o_width = o["width"]
                    center_dist = pos * wall_len
                    half_w = o_width / 2
                    cuts.append((center_dist - half_w, center_dist + half_w))

            seg_points = [0]
            for cut in cuts:
                seg_points.extend([max(0, cut[0]), min(wall_len, cut[1])])
            seg_points.append(wall_len)
            seg_points = sorted(set(seg_points))

            for si in range(len(seg_points) - 1):
                s_start, s_end = seg_points[si], seg_points[si + 1]

                is_opening = False
                for cut in cuts:
                    if s_start >= cut[0] - 0.001 and s_end <= cut[1] + 0.001:
                        is_opening = True
                        break

                if not is_opening and s_end - s_start > 0.01:
                    t_start = s_start / wall_len
                    t_end = s_end / wall_len
                    sx1 = fx1 + (fx2 - fx1) * t_start
                    sy1 = fy1 + (fy2 - fy1) * t_start
                    sx2 = fx1 + (fx2 - fx1) * t_end
                    sy2 = fy1 + (fy2 - fy1) * t_end

                    if is_horizontal:
                        fds += self.gen_box(
                            min(sx1, sx2),
                            max(sx1, sx2),
                            sy1 - thick / 2,
                            sy1 + thick / 2,
                            z0 + z_low,
                            z0 + z_up,
                            "WALL",
                        )
                    else:
                        fds += self.gen_box(
                            sx1 - thick / 2,
                            sx1 + thick / 2,
                            min(sy1, sy2),
                            max(sy1, sy2),
                            z0 + z_low,
                            z0 + z_up,
                            "WALL",
                        )
        return fds


# ============================================================
# FDS Validation
# ============================================================
def validate_fds(fds_text: str) -> list:
    """Validate FDS text and return list of warning/error strings."""
    warnings = []
    lines = fds_text.split("\n")
    non_comment = [
        l.strip() for l in lines if l.strip() and not l.strip().startswith("!")
    ]
    full_text = " ".join(non_comment)
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
