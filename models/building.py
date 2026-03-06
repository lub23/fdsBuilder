#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@File  : building.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 2.0
@Desc  : Building model class for FDS generation
'''

from ui.styles import *
from models.combustibles import CombustibleManager

# ============================================================
# 建筑模型类
# ============================================================
class BuildingModel:
    """建筑模型数据类"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """重置为默认值"""
        self.chid = "building"
        self.length = 20.0
        self.width = 15.0
        self.height = 6.0
        self.wall_thickness = 0.25
        
        self.materials = {
            "walls": "CONCRETE",
            "floor": "CONCRETE",
            "roof": "CONCRETE"
        }
        self.walls = []
        self.openings = []
        
        self.heat_source = {
            "enabled": False,
            "location": "north",
            "distance": 3.0,
            "width_ratio": 1.5,
            "height_ratio": 1.0,
            "radiation_flux": 50.0,
            "use_ramp": True,
            "ramp_points": [(0, 0.0), (100, 1.0), (500, 1.0)]
        }
        
        self.domain = {
            "padding": 5.0,
            "mesh_cells": [80, 60, 40]
        }
        
        self.simulation_time = 60.0
        
        self.output = {
            "slices": True,
            "devices": True
        }
        self.combustible_mgr = CombustibleManager()
        # 初始化外墙
        self._generate_external_walls()
    
    def _generate_external_walls(self):
        """根据length/width自动生成外墙"""
        L, W, H, t = self.length, self.width, self.height, self.wall_thickness
        
        self.walls = [
            {"x1": 0, "y1": 0, "x2": L, "y2": 0, "thickness": t, "height": H, "is_external": True, "name": "south"},
            {"x1": L, "y1": 0, "x2": L, "y2": W, "thickness": t, "height": H, "is_external": True, "name": "east"},
            {"x1": L, "y1": W, "x2": 0, "y2": W, "thickness": t, "height": H, "is_external": True, "name": "north"},
            {"x1": 0, "y1": W, "x2": 0, "y2": 0, "thickness": t, "height": H, "is_external": True, "name": "west"},
        ]
    
    def update_external_walls(self):
        """更新外墙尺寸（保留内墙和开口）"""
        L, W, H, t = self.length, self.width, self.height, self.wall_thickness
        
        # 保留内墙
        internal_walls = [w for w in self.walls if not w.get("is_external", False)]
        
        # 重新生成外墙
        external_walls = [
            {"x1": 0, "y1": 0, "x2": L, "y2": 0, "thickness": t, "height": H, "is_external": True, "name": "south"},
            {"x1": L, "y1": 0, "x2": L, "y2": W, "thickness": t, "height": H, "is_external": True, "name": "east"},
            {"x1": L, "y1": W, "x2": 0, "y2": W, "thickness": t, "height": H, "is_external": True, "name": "north"},
            {"x1": 0, "y1": W, "x2": 0, "y2": 0, "thickness": t, "height": H, "is_external": True, "name": "west"},
        ]
        
        self.walls = external_walls + internal_walls
    
    def add_wall(self, x1, y1, x2, y2, thickness=None, height=None, name=""):
        """添加内墙"""
        wall = {
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "thickness": thickness or self.wall_thickness,
            "height": height or self.height,
            "is_external": False,
            "name": name
        }
        self.walls.append(wall)
        return len(self.walls) - 1  # 返回墙体索引
    
    def add_opening(self, wall_index, opening_type, position, width, height, z_bottom=0):
        """添加开口"""
        opening = {
            "wall_index": wall_index,
            "type": opening_type,  # "door" or "window"
            "position": position,  # 0-1，沿墙位置
            "width": width,
            "height": height,
            "z_bottom": z_bottom
        }
        self.openings.append(opening)
    
    def get_wall_length(self, wall_index):
        """获取墙体长度"""
        if wall_index >= len(self.walls):
            return 0
        w = self.walls[wall_index]
        return ((w["x2"] - w["x1"])**2 + (w["y2"] - w["y1"])**2)**0.5
    
    def get_openings_for_wall(self, wall_index):
        """获取某墙体上的所有开口"""
        return [o for o in self.openings if o["wall_index"] == wall_index]
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "chid": self.chid,
            "length": self.length,
            "width": self.width,
            "height": self.height,
            "wall_thickness": self.wall_thickness,
            "materials": self.materials.copy(),
            "walls": [w.copy() for w in self.walls],
            "openings": [o.copy() for o in self.openings],
            "heat_source": self.heat_source.copy(),
            "domain": self.domain.copy(),
            "simulation_time": self.simulation_time,
            "output": self.output.copy(),
            "combustibles": self.combustible_mgr.to_list()
        }
    
    def from_dict(self, data: dict):
        """从字典加载"""
        self.chid = data.get("chid", "building")
        self.length = data.get("length", 20.0)
        self.width = data.get("width", 15.0)
        self.height = data.get("height", 6.0)
        self.wall_thickness = data.get("wall_thickness", 0.25)
        self.materials = data.get("materials", self.materials)
        self.walls = data.get("walls", [])
        self.openings = data.get("openings", [])
        self.heat_source = data.get("heat_source", self.heat_source)
        self.domain = data.get("domain", self.domain)
        self.simulation_time = data.get("simulation_time", 60.0)
        self.output = data.get("output", self.output)
        self.combustible_mgr.from_list(data.get("combustibles", []))
        
        # 如果没有墙体数据，自动生成外墙
        if self.walls:
            self._identify_external_walls()
        else:
            self._generate_external_walls()

    def _identify_external_walls(self):
        """识别并标记外墙"""
        L, W = self.length, self.width
        tolerance = 0.1
        
        # 定义外墙边界
        external_edges = [
            (0, 0, L, 0, "south"),      # 南
            (L, 0, L, W, "east"),       # 东
            (L, W, 0, W, "north"),      # 北
            (0, W, 0, 0, "west"),       # 西
        ]
        
        matched = [False] * 4
        
        for wall in self.walls:
            x1, y1, x2, y2 = wall["x1"], wall["y1"], wall["x2"], wall["y2"]
            
            for i, (ex1, ey1, ex2, ey2, name) in enumerate(external_edges):
                if matched[i]:
                    continue
                # 检查是否匹配（正向或反向）
                if (abs(x1-ex1)<tolerance and abs(y1-ey1)<tolerance and 
                    abs(x2-ex2)<tolerance and abs(y2-ey2)<tolerance) or \
                (abs(x1-ex2)<tolerance and abs(y1-ey2)<tolerance and 
                    abs(x2-ex1)<tolerance and abs(y2-ey1)<tolerance):
                    wall["is_external"] = True
                    wall["name"] = name
                    matched[i] = True
                    break
            else:
                wall["is_external"] = wall.get("is_external", False)
        
        # 补充缺失的外墙
        for i, (ex1, ey1, ex2, ey2, name) in enumerate(external_edges):
            if not matched[i]:
                self.walls.insert(i, {
                    "x1": ex1, "y1": ey1, "x2": ex2, "y2": ey2,
                    "thickness": self.wall_thickness,
                    "height": self.height,
                    "is_external": True,
                    "name": name
                })
