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
    
    def __init__(self, model: BuildingModel):
        self.model = model
    
    def gen_box(self, x1, x2, y1, y2, z1, z2, surf="WALL"):
        """生成障碍物块"""
        return f"&OBST XB={x1:.3f},{x2:.3f},{y1:.3f},{y2:.3f},{z1:.3f},{z2:.3f}, SURF_ID='{surf}' /\n"
    
    def generate_materials(self) -> str:
        """生成材料和表面定义"""
        fds = "! ========== 材料定义 ==========\n"
        
        used_materials = set()
        for mat in self.model.materials.values():
            used_materials.add(mat)
        
        for mat_name in used_materials:
            if mat_name in MATERIAL_LIBRARY:
                mat = MATERIAL_LIBRARY[mat_name]
                fds += f"&MATL ID='{mat_name}', "
                fds += f"DENSITY={mat['DENSITY']}, "
                fds += f"CONDUCTIVITY={mat['CONDUCTIVITY']}, "
                fds += f"SPECIFIC_HEAT={mat['SPECIFIC_HEAT']} /\n"
        
        fds += "\n! ========== 表面定义 ==========\n"
        
        surfaces = {
            "WALL": ("walls", "墙体"),
            "FLOOR": ("floor", "地板"),
            "ROOF": ("roof", "屋顶")
        }
        
        for surf_name, (mat_key, desc) in surfaces.items():
            mat_name = self.model.materials.get(mat_key, "CONCRETE")
            if mat_name in MATERIAL_LIBRARY:
                thick = MATERIAL_LIBRARY[mat_name]["THICKNESS"]
                fds += f"&SURF ID='{surf_name}', MATL_ID='{mat_name}', THICKNESS={thick} /  ! {desc}\n"
        
        return fds + "\n"
    
    def generate_heat_source(self) -> str:
        """生成热源定义"""
        hs = self.model.heat_source
        
        if not hs.get("enabled", False):
            return ""
        
        fds = "! ========== 热源定义 ==========\n"
        
        L, W, H = self.model.length, self.model.width, self.model.height
        location = hs.get("location", "north")
        distance = hs.get("distance", 3.0)
        width_ratio = hs.get("width_ratio", 1.5)
        height_ratio = hs.get("height_ratio", 1.0)
        flux = hs.get("radiation_flux", 50.0)
        
        if hs.get("use_ramp", True):
            fds += "! 热通量时间变化曲线\n"
            for t, f in hs.get("ramp_points", [(0, 1.0)]):
                fds += f"&RAMP ID='HEAT_RAMP', T={t}, F={f} /\n"
            fds += "\n"
        
        fds += "&SURF ID='HEAT_SOURCE',\n"
        fds += f"      EXTERNAL_FLUX={flux}"
        if hs.get("use_ramp", True):
            fds += ",\n      RAMP_Q='HEAT_RAMP'"
        fds += ",\n      COLOR='ORANGE' /\n\n"
        
        thickness = 0.01
        # 坐标转换：模型坐标以左下角为原点，FDS以中心为原点
        if location == "north":
            source_width = L * width_ratio
            source_height = H * height_ratio
            x1, x2 = -source_width/2, source_width/2
            y1, y2 = W/2 + distance, W/2 + distance + thickness
            z1, z2 = 0, source_height
        elif location == "south":
            source_width = L * width_ratio
            source_height = H * height_ratio
            x1, x2 = -source_width/2, source_width/2
            y1, y2 = -W/2 - distance - thickness, -W/2 - distance
            z1, z2 = 0, source_height
        elif location == "east":
            source_width = W * width_ratio
            source_height = H * height_ratio
            x1, x2 = L/2 + distance, L/2 + distance + thickness
            y1, y2 = -source_width/2, source_width/2
            z1, z2 = 0, source_height
        else:  # west
            source_width = W * width_ratio
            source_height = H * height_ratio
            x1, x2 = -L/2 - distance - thickness, -L/2 - distance
            y1, y2 = -source_width/2, source_width/2
            z1, z2 = 0, source_height
        
        fds += f"! 热源位置: {location}侧\n"
        fds += self.gen_box(x1, x2, y1, y2, z1, z2, "HEAT_SOURCE")
        
        return fds + "\n"
    
    def generate_wall(self, wall_index) -> str:
        """生成单面墙（含开口处理）"""
        m = self.model
        L, W, H = m.length, m.width, m.height
        
        wall = m.walls[wall_index]
        x1, y1, x2, y2 = wall["x1"], wall["y1"], wall["x2"], wall["y2"]
        thick = wall.get("thickness", m.wall_thickness)
        wall_h = wall.get("height", H)
        
        # 坐标转换：模型左下角原点 -> FDS中心原点
        fx1, fy1 = x1 - L/2, y1 - W/2
        fx2, fy2 = x2 - L/2, y2 - W/2
        
        # 获取该墙的开口
        openings = m.get_openings_for_wall(wall_index)
        
        # 墙体长度和方向
        wall_len = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
        if wall_len < 0.01:
            return ""
        
        # 判断水平/垂直
        is_horizontal = abs(y2 - y1) < abs(x2 - x1)
        
        if not openings:
            if is_horizontal:
                return self.gen_box(min(fx1,fx2)-thick/2, max(fx1,fx2)+thick/2, fy1-thick/2, fy1+thick/2, 0, wall_h, "WALL")
            else:
                return self.gen_box(fx1-thick/2, fx1+thick/2, min(fy1,fy2)+thick/2, max(fy1,fy2)-thick/2, 0, wall_h, "WALL")
        
        # 有开口，需要切分墙体
        fds = ""
        
        # 收集所有高度分割点
        z_splits = [0, wall_h]
        for o in openings:
            z_b = o.get("z_bottom", 0)
            z_t = z_b + o["height"]
            z_splits.extend([z_b, z_t])
        z_splits = sorted(set(z_splits))
        
        # 对每个高度段处理
        for zi in range(len(z_splits) - 1):
            z_low, z_up = z_splits[zi], z_splits[zi + 1]
            
            # 找出与此高度段重叠的开口
            cuts = []
            for o in openings:
                z_b = o.get("z_bottom", 0)
                z_t = z_b + o["height"]
                
                if not (z_up <= z_b or z_low >= z_t):
                    pos = o["position"]
                    o_width = o["width"]
                    # position是沿墙的相对位置(0-1)，转为实际距离
                    center_dist = pos * wall_len
                    half_w = o_width / 2
                    cuts.append((center_dist - half_w, center_dist + half_w))
            
            # 按距离分段
            seg_points = [0]
            for cut in cuts:
                seg_points.extend([max(0, cut[0]), min(wall_len, cut[1])])
            seg_points.append(wall_len)
            seg_points = sorted(set(seg_points))
            
            # 生成每个墙段
            for si in range(len(seg_points) - 1):
                s_start, s_end = seg_points[si], seg_points[si + 1]
                
                # 检查是否在开口内
                is_opening = False
                for cut in cuts:
                    if s_start >= cut[0] - 0.001 and s_end <= cut[1] + 0.001:
                        is_opening = True
                        break
                
                if not is_opening and s_end - s_start > 0.01:
                    # 计算实际坐标
                    t_start = s_start / wall_len
                    t_end = s_end / wall_len
                    
                    sx1 = fx1 + (fx2 - fx1) * t_start
                    sy1 = fy1 + (fy2 - fy1) * t_start
                    sx2 = fx1 + (fx2 - fx1) * t_end
                    sy2 = fy1 + (fy2 - fy1) * t_end
                    
                    if is_horizontal:
                        fds += self.gen_box(min(sx1,sx2), max(sx1,sx2), sy1-thick/2, sy1+thick/2, z_low, z_up, "WALL")
                    else:
                        fds += self.gen_box(sx1-thick/2, sx1+thick/2, min(sy1,sy2), max(sy1,sy2), z_low, z_up, "WALL")
        
        return fds

    def generate_combustibles(self, manager) -> str:
        """生成可燃物 FDS 代码"""
        if not manager.items:
            return ""

        fds = "! ── 可燃物 ──────────────────────────────\n"

        # 收集用到的材料，去重
        used_matls = {}
        for cb in manager.items:
            matl_id = f"MATL_{cb.preset_key}"
            if matl_id not in used_matls:
                used_matls[matl_id] = cb

        # MATL
        for matl_id, cb in used_matls.items():
            m = cb.matl
            fds += (
                f"&MATL ID='{matl_id}',\n"
                f"      DENSITY={m['DENSITY']},\n"
                f"      CONDUCTIVITY={m['CONDUCTIVITY']},\n"
                f"      SPECIFIC_HEAT={m['SPECIFIC_HEAT']} /\n\n"
            )

        # SURF
        used_surfs = {}
        for cb in manager.items:
            surf_id = f"SURF_{cb.preset_key}"
            if surf_id not in used_surfs:
                used_surfs[surf_id] = cb
                fds += (
                    f"&SURF ID='{surf_id}',\n"
                    f"      MATL_ID='MATL_{cb.preset_key}',\n"
                    f"      THICKNESS=0.05,\n"
                    f"      HRRPUA={cb.hrrpua},\n"
                    f"      COLOR='{cb.color}' /\n\n"
                )

        # OBST
        for cb in manager.items:
            L, W = self.model.length, self.model.width
            x1 = cb.x - L/2
            x2 = cb.x + cb.length - L/2
            y1 = cb.y - W/2
            y2 = cb.y + cb.width - W/2
            fds += (
                f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                f"{cb.z:.2f},{cb.z + cb.height:.2f},\n"
                f"      SURF_ID='SURF_{cb.preset_key}',\n"
                f"      ID='{cb.id}' /  ! {cb.name}\n"
            )

        fds += "\n"
        return fds
    
    def generate(self) -> str:
        """生成完整的FDS输入文件"""
        m = self.model
        L, W, H = m.length, m.width, m.height
        t = m.wall_thickness
        
        chid = m.chid.replace(" ", "_").replace(".", "_").replace("-", "_")
        chid = ''.join(c for c in chid if ord(c) < 128)
        if not chid:
            chid = "building"
        
        fds = f"&HEAD CHID='{chid}', TITLE='Auto-generated Building Model' /\n\n"

        fds += "\n! ========== 燃烧反应 ==========\n"
        fds += ("&REAC FUEL='CELLULOSE',\n"
                "      FORMULA='C6H10O5',\n"
                "      HEAT_OF_COMBUSTION=18000,\n"
                "      SOOT_YIELD=0.015 /\n\n")
        
        # 计算域
        pad = m.domain["padding"]
        mesh = m.domain["mesh_cells"]
        
        fds += "! ========== 计算域 ==========\n"
        fds += f"&MESH IJK={mesh[0]},{mesh[1]},{mesh[2]}, "
        fds += f"XB={-L/2-pad:.2f},{L/2+pad:.2f},{-W/2-pad:.2f},{W/2+pad:.2f},0,{H+pad:.2f} /\n\n"
        fds += f"&TIME T_END={m.simulation_time:.1f} /\n\n"
        
        # 材料和表面
        fds += self.generate_materials()
        
        # 建筑结构 - 墙体
        fds += "! ========== 墙体 ==========\n"
        for i, wall in enumerate(m.walls):
            name = wall.get("name", f"wall_{i}")
            is_ext = "外墙" if wall.get("is_external", False) else "内墙"
            fds += f"! {name} ({is_ext})\n"
            fds += self.generate_wall(i)
        
        # 地板
        fds += "\n! ========== 地板 ==========\n"
        fds += self.gen_box(-L/2-t/2, L/2+t/2, -W/2-t/2, W/2+t/2, -t, 0, "FLOOR")
        
        # 屋顶
        fds += "\n! ========== 屋顶 ==========\n"
        fds += self.gen_box(-L/2-t/2, L/2+t/2, -W/2-t/2, W/2+t/2, H, H+t, "ROOF")
        fds += "\n"
        
        # 热源
        fds += self.generate_heat_source()

        fds += self.generate_combustibles(m.combustible_mgr)
        
        # 输出
        if m.output.get("slices", True):
            fds += "! ========== 切片输出 ==========\n"
            fds += "&SLCF PBX=0, QUANTITY='TEMPERATURE' /\n"
            fds += "&SLCF PBY=0, QUANTITY='TEMPERATURE' /\n"
            fds += "&SLCF PBZ=2, QUANTITY='TEMPERATURE' /\n"
            fds += "&BNDF QUANTITY='WALL TEMPERATURE' /\n\n"
        
        if m.output.get("devices", True):
            fds += "! ========== 测量点 ==========\n"
            fds += f"&DEVC XYZ=0,0,{H/2}, QUANTITY='TEMPERATURE', ID='temp_center' /\n\n"
        
        fds += "&TAIL /\n"
        
        return fds