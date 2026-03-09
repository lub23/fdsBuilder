#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@File  : building.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 2.0
@Desc  : Building model class for FDS generation
'''
import copy
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from ui.styles import *
from models.combustibles import CombustibleManager

@dataclass
class WallData:
    """墙体"""
    x1: float = 0
    y1: float = 0
    x2: float = 0
    y2: float = 0
    thickness: float = 0.24
    height: float = 3.0      # 该墙实际高度（通常=层高）
    name: str = ""
    is_external: bool = False
    material: str = "CONCRETE"

    def to_dict(self): return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d): return cls(**d)

@dataclass
class OpeningData:
    """开口（门/窗）"""
    wall_index: int = 0
    type: str = "door"        # door / window
    position: float = 0.5     # 沿墙相对位置 0~1
    width: float = 1.0
    height: float = 2.0
    z_bottom: float = 0.0     # 相对于本层地板

    def to_dict(self): return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d): return cls(**d)


@dataclass
class FloorSlab:
    """楼板（含开口/洞口）"""
    thickness: float = 0.2
    material: str = "CONCRETE"
    openings: List[Dict] = field(default_factory=list)
    # 每个开口: {"x": 5, "y": 3, "length": 2, "width": 2, "name": "楼梯间"}

    def to_dict(self):
        return {"thickness": self.thickness, "material": self.material,
                "openings": self.openings}

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("thickness", 0.2), d.get("material", "CONCRETE"),
                   d.get("openings", []))


@dataclass
class Story:
    """单层"""
    name: str = "1F"
    height: float = 3.0           # 层高（地板到天花板）
    walls: List[Dict] = field(default_factory=list)
    openings: List[Dict] = field(default_factory=list)
    combustibles: CombustibleManager = field(default_factory=CombustibleManager)
    floor_slab: FloorSlab = field(default_factory=FloorSlab)   # 本层地板
    # 顶层的 roof 由 BuildingModel 统一处理

    @property
    def z_bottom(self) -> float:
        """由 BuildingModel 计算后注入"""
        return getattr(self, '_z_bottom', 0.0)

    @z_bottom.setter
    def z_bottom(self, v):
        self._z_bottom = v

    @property
    def z_top(self) -> float:
        return self.z_bottom + self.height

    def to_dict(self):
        return {
            "name": self.name,
            "height": self.height,
            "walls": self.walls,
            "openings": self.openings,
            "combustibles": self.combustibles.to_list(),
            "floor_slab": self.floor_slab.to_dict(),
        }

    @classmethod
    def from_dict(cls, d):
        s = cls()
        s.name = d.get("name", "1F")
        s.height = d.get("height", 3.0)
        s.walls = d.get("walls", [])
        s.openings = d.get("openings", [])
        s.combustibles = CombustibleManager()
        s.combustibles.from_list(d.get("combustibles", []))
        s.floor_slab = FloorSlab.from_dict(d.get("floor_slab", {}))
        return s

# ============================================================
# 建筑模型类
# ============================================================
class BuildingModel:
    """
    建筑模型数据类
    20260305 支持多层建筑，每层单独定义墙体/开口/可燃物，自动计算层高和外墙高度。
    """
    
    def __init__(self):
        self.chid = "building"
        self.length = 20.0
        self.width = 15.0
        self.wall_thickness = 0.25

        # 多层
        self.stories: List[Story] = [Story(name="1F", height=3.0)]

        # 屋顶
        self.roof = {"thickness": 0.2, "material": "CONCRETE"}
        
        self.materials = {
            "walls": "CONCRETE",
            "floor": "CONCRETE",
            "roof": "CONCRETE"
        }
        
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
        
        # 模拟参数
        self.simulation_time = 20.0
        self.domain = {"padding": 5.0, "mesh_cells": [80, 60, 40]}
        self.output = {"slices": True, "devices": True}

        self.update_z_offsets()
        self.update_external_walls()
    
    @property
    def height(self) -> float:
        return self.total_height

    @height.setter
    def height(self, v):
        if self.stories:
            self.stories[0].height = v
            self.update_z_offsets()

    # ── 层管理 ───────────────────────────────────────
    @property
    def num_stories(self) -> int:
        return len(self.stories)

    @property
    def total_height(self) -> float:
        return sum(s.height for s in self.stories)

    def update_z_offsets(self):
        """计算每层的z偏移"""
        z = 0.0
        for s in self.stories:
            s.z_bottom = z
            z += s.height

    def add_story(self, name: str = None, height: float = 3.0,
                  copy_from: int = -1) -> Story:
        """添加一层"""
        idx = len(self.stories) + 1
        s = Story(name=name or f"{idx}F", height=height)
        # 可选：从某层复制墙体布局
        if 0 <= copy_from < len(self.stories):
            src = self.stories[copy_from]
            s.walls = copy.deepcopy(src.walls)
            s.openings = copy.deepcopy(src.openings)
        self.stories.append(s)
        self.update_z_offsets()
        self.update_external_walls()
        return s

    def remove_story(self, index: int):
        if len(self.stories) <= 1:
            return
        del self.stories[index]
        self.update_z_offsets()

    def get_story(self, index: int) -> Story:
        return self.stories[index]
    
    # ── 外墙（每层都要） ────────────────────────────────
    def update_external_walls(self):
        """为每层生成外墙"""
        L, W, t = self.length, self.width, self.wall_thickness
        ext_walls = [
            {"name": "南墙", "x1": 0, "y1": 0, "x2": L, "y2": 0,
             "thickness": t, "is_external": True},
            {"name": "北墙", "x1": 0, "y1": W, "x2": L, "y2": W,
             "thickness": t, "is_external": True},
            {"name": "西墙", "x1": 0, "y1": 0, "x2": 0, "y2": W,
             "thickness": t, "is_external": True},
            {"name": "东墙", "x1": L, "y1": 0, "x2": L, "y2": W,
             "thickness": t, "is_external": True},
        ]
        for story in self.stories:
            # 保留内墙，替换外墙
            internal = [w for w in story.walls if not w.get("is_external")]
            import copy
            story.walls = copy.deepcopy(ext_walls) + internal
            # 每面墙高度=层高
            for w in story.walls:
                w["height"] = story.height
    @property
    def walls(self):
        """兼容：返回当前活动层的墙体"""
        return self.stories[0].walls if self.stories else []

    @walls.setter
    def walls(self, v):
        if self.stories:
            self.stories[0].walls = v

    @property
    def openings(self):
        return self.stories[0].openings if self.stories else []

    @openings.setter
    def openings(self, v):
        if self.stories:
            self.stories[0].openings = v

    @property
    def combustible_mgr(self):
        return self.stories[0].combustibles if self.stories else CombustibleManager()

    def get_openings_for_wall(self, wall_index, story_index=0):
        if story_index < len(self.stories):
            story = self.stories[story_index]
            return [o for o in story.openings if o["wall_index"] == wall_index]
        return []
    
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
    
     # ── 序列化 ──────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "chid": self.chid,
            "length": self.length,
            "width": self.width,
            "wall_thickness": self.wall_thickness,
            "stories": [s.to_dict() for s in self.stories],
            "roof": self.roof,
            "materials": self.materials.copy(),
            "heat_source": self.heat_source.copy(),
            "domain": self.domain.copy(),
            "simulation_time": self.simulation_time,
            "output": self.output.copy()
        }
    
    def from_dict(self, data: dict):
        """从字典加载"""
        self.chid = data.get("chid", "building")
        self.length = data.get("length", 20.0)
        self.width = data.get("width", 15.0)
        self.wall_thickness = data.get("wall_thickness", 0.25)
        # 多层
        if "stories" in data:
            self.stories = [Story.from_dict(s) for s in data["stories"]]
        else:
            # 兼容旧格式：单层
            s = Story(name="1F", height=data.get("height", 3.0))
            s.walls = data.get("walls", [])
            s.openings = data.get("openings", [])
            s.combustibles.from_list(data.get("combustibles", []))
            self.stories = [s]
        self.roof = data.get("roof", {"thickness": 0.2, "material": "CONCRETE"})
        self.materials = data.get("materials", {"walls": "CONCRETE", "floor": "CONCRETE", "roof": "CONCRETE"})
        self.heat_source = data.get("heat_source", self.heat_source)
        self.domain = data.get("domain", self.domain)
        self.simulation_time = data.get("simulation_time", 20.0)
        self.output = data.get("output", self.output)
        
        self.update_z_offsets()
        if not any(w.get("is_external") for s in self.stories for w in s.walls):
            self.update_external_walls()