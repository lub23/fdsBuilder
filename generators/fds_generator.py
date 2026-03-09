#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@File  : fds_generator.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 2.0
@Desc  : FDS file generator for building models
'''

from models.building import BuildingModel
from models.materials import MATERIAL_LIBRARY
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
        for mat_name in used_materials:
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

        # 每层楼板可能材料不同，生成 FLOOR_xxF 表面
        for story in self.model.stories:
            slab_mat = story.floor_slab.material
            surf_id = f"FLOOR_{story.name}"
            if slab_mat in MATERIAL_LIBRARY:
                thick = MATERIAL_LIBRARY[slab_mat]["THICKNESS"]
                fds += f"&SURF ID='{surf_id}', MATL_ID='{slab_mat}', THICKNESS={thick} /\n"

        return fds + "\n"

    def generate_heat_source(self) -> str:
        hs = self.model.heat_source
        if not hs.get("enabled", False):
            return ""

        fds = "! ========== 外部强辐射热源 ==========\n"
        L, W = self.model.length, self.model.width
        total_h = self.model.total_height
        location = hs.get("location", "north")
        distance = hs.get("distance", 3.0)
        width_ratio = hs.get("width_ratio", 1.5)
        height_ratio = hs.get("height_ratio", 1.0)
        
        # 1. 核心修改：将原本的 flux 概念转换为表面温度 (TMP_FRONT)
        # 默认 800℃，这相当于一个非常猛烈的大型电炉或火墙
        # (如果你的配置文件里传的是 radiation_flux 比如 500000，这里需要改成合理的温度数值如 800~1200)
        temperature = hs.get("temperature", 800.0) 
        if hs.get("radiation_flux") and "temperature" not in hs:
            # 兼容你的旧配置：如果传了超大的flux，强制修正为1000度，防止FDS崩溃
            flux_val = hs.get("radiation_flux")
            if flux_val > 2000:
                temperature = 1000.0
            else:
                temperature = 800.0

        if hs.get("use_ramp", True):
            fds += "! 表面温度时间变化曲线 (F为比例)\n"
            for t, f in hs.get("ramp_points", [(0, 1.0)]):
                # 2. 核心修改：温度的 RAMP 必须用 T (而不是之前可能用错的)
                fds += f"&RAMP ID='HEAT_RAMP', T={t}, F={f} /\n"
            fds += "\n"

        fds += "&SURF ID='HEAT_SOURCE',\n"
        fds += f"      TMP_FRONT={temperature:.1f}"
        if hs.get("use_ramp", True):
            # 3. 核心修改：对应 TMP_FRONT 的爬升曲线属性叫做 RAMP_T，而不是 RAMP_Q
            fds += ",\n      RAMP_T='HEAT_RAMP'"
        fds += ",\n      COLOR='ORANGE' /\n\n"

        # 4. 优化：厚度设为 0.2，防止 0.01 太薄导致 FDS 网格捕捉不到而报错或穿透
        thickness = 0.2 
        
        if location == "north":
            sw, sh = L * width_ratio, total_h * height_ratio
            x1, x2 = -sw / 2, sw / 2
            y1, y2 = W / 2 + distance, W / 2 + distance + thickness
            z1, z2 = 0, sh
        elif location == "south":
            sw, sh = L * width_ratio, total_h * height_ratio
            x1, x2 = -sw / 2, sw / 2
            y1, y2 = -W / 2 - distance - thickness, -W / 2 - distance
            z1, z2 = 0, sh
        elif location == "east":
            sw, sh = W * width_ratio, total_h * height_ratio
            x1, x2 = L / 2 + distance, L / 2 + distance + thickness
            y1, y2 = -sw / 2, sw / 2
            z1, z2 = 0, sh
        else:
            sw, sh = W * width_ratio, total_h * height_ratio
            x1, x2 = -L / 2 - distance - thickness, -L / 2 - distance
            y1, y2 = -sw / 2, sw / 2
            z1, z2 = 0, sh

        fds += f"! 热源位置: {location}侧, 距离建筑 {distance} 米\n"
        fds += self.gen_box(x1, x2, y1, y2, z1, z2, "HEAT_SOURCE")
        return fds + "\n"

    def generate_wall(self, wall_index, story_index=0) -> str:
        """生成单面墙（含开口处理），支持多层"""
        m = self.model
        L, W = m.length, m.width

        story = m.stories[story_index]
        wall = story.walls[wall_index]
        z0 = story.z_bottom

        x1, y1, x2, y2 = wall["x1"], wall["y1"], wall["x2"], wall["y2"]
        thick = wall.get("thickness", m.wall_thickness)
        wall_h = wall.get("height", story.height)

        fx1, fy1 = x1 - L / 2, y1 - W / 2
        fx2, fy2 = x2 - L / 2, y2 - W / 2

        openings = m.get_openings_for_wall(wall_index, story_index)

        wall_len = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if wall_len < 0.01:
            return ""

        is_horizontal = abs(y2 - y1) < abs(x2 - x1)

        if not openings:
            if is_horizontal:
                return self.gen_box(
                    min(fx1, fx2) - thick / 2, max(fx1, fx2) + thick / 2,
                    fy1 - thick / 2, fy1 + thick / 2,
                    z0, z0 + wall_h, "WALL")
            else:
                return self.gen_box(
                    fx1 - thick / 2, fx1 + thick / 2,
                    min(fy1, fy2) + thick / 2, max(fy1, fy2) - thick / 2,
                    z0, z0 + wall_h, "WALL")

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
                            min(sx1, sx2), max(sx1, sx2),
                            sy1 - thick / 2, sy1 + thick / 2,
                            z0 + z_low, z0 + z_up, "WALL")
                    else:
                        fds += self.gen_box(
                            sx1 - thick / 2, sx1 + thick / 2,
                            min(sy1, sy2), max(sy1, sy2),
                            z0 + z_low, z0 + z_up, "WALL")
        return fds

    def generate_combustibles(self, manager, z_offset=0.0) -> str:
        if not manager.items:
            return ""

        fds = ""
        used_matls = {}
        for cb in manager.items:
            matl_id = f"MATL_{cb.preset_key}"
            if matl_id not in used_matls:
                used_matls[matl_id] = cb

        for matl_id, cb in used_matls.items():
            mt = cb.matl
            fds += (f"&MATL ID='{matl_id}',\n"
                    f"      DENSITY={mt['DENSITY']},\n"
                    f"      CONDUCTIVITY={mt['CONDUCTIVITY']},\n"
                    f"      SPECIFIC_HEAT={mt['SPECIFIC_HEAT']} /\n\n")

        used_surfs = {}
        for cb in manager.items:
            surf_id = f"SURF_{cb.preset_key}"
            if surf_id not in used_surfs:
                used_surfs[surf_id] = cb
                fds += (f"&SURF ID='{surf_id}',\n"
                        f"      MATL_ID='MATL_{cb.preset_key}',\n"
                        f"      THICKNESS=0.05,\n"
                        f"      HRRPUA={cb.hrrpua},\n"
                        f"      COLOR='{cb.color}' /\n\n")

        L, W = self.model.length, self.model.width
        for cb in manager.items:
            x1 = cb.x - L / 2
            x2 = cb.x + cb.length - L / 2
            y1 = cb.y - W / 2
            y2 = cb.y + cb.width - W / 2
            z1 = cb.z + z_offset
            z2 = z1 + cb.height
            fds += (f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                    f"{z1:.2f},{z2:.2f},\n"
                    f"      SURF_ID='SURF_{cb.preset_key}',\n"
                    f"      ID='{cb.id}' /  ! {cb.name}\n")

        fds += "\n"
        return fds

    def generate(self) -> str:
        m = self.model
        L, W, t = m.length, m.width, m.wall_thickness
        total_h = m.total_height
        roof_t = m.roof.get("thickness", 0.2)

        chid = m.chid.replace(" ", "_").replace(".", "_").replace("-", "_")
        chid = ''.join(c for c in chid if ord(c) < 128) or "building"

        fds = f"&HEAD CHID='{chid}', TITLE='Auto-generated Building Model' /\n\n"

        # 1. 消除 Warning，使用 FDS 内置标准燃料库，产烟率设为0.1让黑烟明显
        fds += "! ========== 燃烧反应 ==========\n"
        fds += ("&REAC FUEL='METHANE',\n"
                "      SOOT_YIELD=0.01 /\n\n")

        pad = m.domain["padding"]
        mesh = m.domain["mesh_cells"]
        
        # 确保网格尺寸合理
        dx = (L + 2*pad) / mesh[0]
        dy = (W + 2*pad) / mesh[1]
        dz = (total_h + pad) / mesh[2]
        
        # 如果网格太粗，自动调整
        max_cell = 0.5  # 最大网格尺寸0.5m
        if dx > max_cell or dy > max_cell or dz > max_cell:
            mesh = [
                max(int((L + 2*pad) / max_cell), 20),
                max(int((W + 2*pad) / max_cell), 20),
                max(int((total_h + pad) / max_cell), 10),
            ]
        
        fds += "! ========== 计算域 ==========\n"
        fds += (f"&MESH IJK={mesh[0]},{mesh[1]},{mesh[2]}, "
                f"XB={-L/2-pad:.2f},{L/2+pad:.2f},"
                f"{-W/2-pad:.2f},{W/2+pad:.2f},"
                f"0.00,{total_h+pad:.2f} /\n\n")
        
        fds += f"&TIME T_END={m.simulation_time:.1f} /\n\n"

        fds += self.generate_materials()

        # 地板
        fds += "! ========== 地板 ==========\n"
        fds += self.gen_box(-L/2-t/2, L/2+t/2, -W/2-t/2, W/2+t/2, -t, 0, "FLOOR")
        fds += "\n"

        # 收集可燃物
        all_combustible_matls = {}
        all_combustible_surfs = {}
        first_cb_center = None  # 用于记录第一个可燃物的中心点，给切片用

        for story in m.stories:
            for cb in story.combustibles.items:
                matl_id = f"MATL_{cb.preset_key}"
                surf_id = f"SURF_{cb.preset_key}"
                if matl_id not in all_combustible_matls:
                    all_combustible_matls[matl_id] = cb
                if surf_id not in all_combustible_surfs:
                    all_combustible_surfs[surf_id] = cb
                
                # 记录第一个可燃物的坐标，方便后面切片对齐
                if first_cb_center is None:
                    first_cb_center = (
                        cb.x - L/2 + cb.length/2, 
                        cb.y - W/2 + cb.width/2,
                        story.z_bottom + cb.z + cb.height/2
                    )

        if all_combustible_matls:
            fds += "! ========== 可燃物材料/表面 ==========\n"
            for matl_id, cb in all_combustible_matls.items():
                mt = cb.matl
                fds += (f"&MATL ID='{matl_id}',\n"
                        f"      DENSITY={mt['DENSITY']},\n"
                        f"      CONDUCTIVITY={mt['CONDUCTIVITY']},\n"
                        f"      SPECIFIC_HEAT={mt['SPECIFIC_HEAT']} /\n\n")
            for surf_id, cb in all_combustible_surfs.items():
                # 2. 核心修改：加入 IGNITION_TEMPERATURE 引燃温度参数！
                fds += (f"&SURF ID='{surf_id}',\n"
                        f"      MATL_ID='MATL_{cb.preset_key}',\n"
                        f"      THICKNESS=0.05,\n"
                        f"      IGNITION_TEMPERATURE=250.0,\n"  # <--- 关键：达到 250℃ 才会起火
                        f"      HRRPUA={cb.hrrpua},\n"
                        f"      COLOR='{cb.color}' /\n\n")

        for si, story in enumerate(m.stories):
            z0 = story.z_bottom
            slab_t = story.floor_slab.thickness

            fds += f"\n! ========== {story.name} (z={z0:.2f}~{story.z_top:.2f}) ==========\n"

            if si > 0:
                fds += f"! -- 楼板 --\n"
                fds += self.gen_box(
                    -L/2-t/2, L/2+t/2, -W/2-t/2, W/2+t/2,
                    z0 - slab_t, z0, f"FLOOR_{story.name}")

                for hole in story.floor_slab.openings:
                    hx = hole["x"] - L / 2
                    hy = hole["y"] - W / 2
                    fds += (f"&HOLE XB={hx:.2f},{hx+hole['length']:.2f},"
                            f"{hy:.2f},{hy+hole['width']:.2f},"
                            f"{z0-slab_t-0.01:.2f},{z0+0.01:.2f} /  ! {hole.get('name', '洞口')}\n")

            fds += f"! -- 墙体 --\n"
            for wi in range(len(story.walls)):
                fds += self.generate_wall(wi, story_index=si)

            if story.combustibles.items:
                fds += f"! -- 可燃物 --\n"
                for cb in story.combustibles.items:
                    x1 = cb.x - L / 2
                    x2 = cb.x + cb.length - L / 2
                    y1 = cb.y - W / 2
                    y2 = cb.y + cb.width - W / 2
                    z1 = cb.z + z0
                    z2 = z1 + cb.height
                    # 3. 核心修改：用 SURF_IDS 替代 SURF_ID，保证底面不着火
                    fds += (f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                            f"{z1:.2f},{z2:.2f},\n"
                            f"      SURF_IDS='SURF_{cb.preset_key}','INERT','INERT',\n" 
                            f"      ID='{cb.id}' /  ! {cb.name}\n")

        fds += "\n! ========== 屋顶 ==========\n"
        fds += self.gen_box(-L/2-t/2, L/2+t/2, -W/2-t/2, W/2+t/2,
                            total_h, total_h + roof_t, "ROOF")
        fds += "\n"

        # 生成辐射热源
        fds += self.generate_heat_source()

        if m.output.get("slices", True):
            fds += "! ========== 切片输出 ==========\n"
            # 4. 核心修改：动态寻找第一个可燃物的位置作为切片坐标！
            if first_cb_center:
                cx, cy, cz = first_cb_center
                fds += f"&SLCF PBX={cx:.2f}, QUANTITY='TEMPERATURE' /  ! 对准可燃物 X 坐标\n"
                fds += f"&SLCF PBY={cy:.2f}, QUANTITY='TEMPERATURE' /  ! 对准可燃物 Y 坐标\n"
                fds += f"&SLCF PBZ={cz + 0.5:.2f}, QUANTITY='TEMPERATURE' /  ! 可燃物正上方0.5米\n"
                # 加一个看烟气的切片
                fds += f"&SLCF PBY={cy:.2f}, QUANTITY='HRRPUV' /  ! 热释放率\n"
            else:
                fds += "&SLCF PBX=0, QUANTITY='TEMPERATURE' /\n"
                fds += "&SLCF PBY=0, QUANTITY='TEMPERATURE' /\n"
                fds += f"&SLCF PBZ={total_h / 2:.1f}, QUANTITY='TEMPERATURE' /\n"
                
            fds += "&BNDF QUANTITY='WALL TEMPERATURE' /\n\n"

        if m.output.get("devices", True):
            fds += "! ========== 测量点 ==========\n"
            # 可以在可燃物上方加一个测量点，监控它是如何被烤热的
            if first_cb_center:
                cx, cy, cz = first_cb_center
                fds += f"&DEVC XYZ={cx:.2f},{cy:.2f},{cz+0.1:.2f}, QUANTITY='TEMPERATURE', ID='Target_Temp' /\n"
                
            for story in m.stories:
                z_mid = story.z_bottom + story.height / 2
                fds += f"&DEVC XYZ=0,0,{z_mid:.1f}, QUANTITY='TEMPERATURE', ID='temp_{story.name}' /\n"
            fds += "\n"

        fds += "&TAIL /\n"
        return fds