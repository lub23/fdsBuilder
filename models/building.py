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
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional

from models.combustibles import CombustibleManager

# ============================================================
# 布局模式
# ============================================================
class LayoutMode(Enum):
    ENCLOSURE = "围合型布局"


def compute_layout(buildings, mode: LayoutMode = None, spacing: float = 5.0):
    """Compute (x_offset, y_offset) for each building using enclosure pattern.

    Enclosure pattern (≤5 buildings):
      #1=NE, #2=SE, #3=SW, #4=NW, #5=center
    Fire separation = max(max_height * 1.2, spacing, 10m)
    Returns list of (x, y) tuples, one per building.
    """
    if not buildings:
        return []
    n = len(buildings)
    if n == 1:
        return [(0.0, 0.0)]

    # ENCLOSURE pattern
    max_h = max(b.total_height for b in buildings)
    sep = max(max_h * 1.2, spacing, 10.0)

    max_l = max(b.length for b in buildings)
    max_w = max(b.width for b in buildings)

    # Distance between building centers
    yard_x = max_l + sep
    yard_y = max_w + sep

    # Corner positions: NE, SE, SW, NW, center
    corners = [
        (yard_x / 2, yard_y / 2),  # NE
        (yard_x / 2, -yard_y / 2),  # SE
        (-yard_x / 2, -yard_y / 2),  # SW
        (-yard_x / 2, yard_y / 2),  # NW
        (0.0, 0.0),  # center
    ]

    offsets = []
    for i in range(n):
        if i < len(corners):
            offsets.append(corners[i])
        else:
            # Extra buildings: linear extension along +X
            offsets.append((yard_x / 2 + (i - 4) * (max_l + sep), 0.0))
    return offsets

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
class FireCompartment:
    """防火分区 - 用于将某一层分为不同区域"""

    id: str = ""
    name: str = "防火分区1"
    x_min: float = 0.0
    x_max: float = 0.0
    y_min: float = 0.0
    y_max: float = 0.0
    firewall_thickness: float = 0.2
    firewall_material: str = "CONCRETE"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "x_min": self.x_min,
            "x_max": self.x_max,
            "y_min": self.y_min,
            "y_max": self.y_max,
            "firewall_thickness": self.firewall_thickness,
            "firewall_material": self.firewall_material,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d.get("id", ""),
            name=d.get("name", "防火分区1"),
            x_min=d.get("x_min", 0.0),
            x_max=d.get("x_max", 0.0),
            y_min=d.get("y_min", 0.0),
            y_max=d.get("y_max", 0.0),
            firewall_thickness=d.get("firewall_thickness", 0.2),
            firewall_material=d.get("firewall_material", "CONCRETE"),
        )

@dataclass
class Story:
    """单层"""
    name: str = "1F"
    height: float = 3.0           # 层高（地板到天花板）
    walls: List[Dict] = field(default_factory=list)
    openings: List[Dict] = field(default_factory=list)
    combustibles: CombustibleManager = field(default_factory=CombustibleManager)
    fire_compartments: List[FireCompartment] = field(default_factory=list)  # 防火分区
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

    def get_firewall_obsts(self) -> list:
        """Return internal wall dicts generated from fire compartment boundaries."""
        walls = []
        for fc in self.fire_compartments:
            t = fc.firewall_thickness
            # Vertical partition walls (along X boundaries)
            if fc.x_min > 0:
                walls.append(
                    {
                        "name": f"{fc.name}_X左",
                        "x1": fc.x_min,
                        "y1": fc.y_min,
                        "x2": fc.x_min,
                        "y2": fc.y_max,
                        "thickness": t,
                        "height": self.height,
                        "is_external": False,
                        "is_fire_partition": True,
                        "material": fc.firewall_material,
                    }
                )
            if fc.x_max > 0 and fc.x_max != fc.x_min:
                # Only add right boundary if not covered by next compartment's left
                is_rightmost = not any(
                    abs(other.x_min - fc.x_max) < 0.01
                    for other in self.fire_compartments
                    if other.id != fc.id
                )
                if not is_rightmost:
                    continue  # skip, next compartment will add it
            # Horizontal partition walls (along Y boundaries)
            if fc.y_min > 0:
                walls.append(
                    {
                        "name": f"{fc.name}_Y下",
                        "x1": fc.x_min,
                        "y1": fc.y_min,
                        "x2": fc.x_max,
                        "y2": fc.y_min,
                        "thickness": t,
                        "height": self.height,
                        "is_external": False,
                        "is_fire_partition": True,
                        "material": fc.firewall_material,
                    }
                )
        # Deduplicate by position
        seen = set()
        unique = []
        for w in walls:
            key = (
                round(w["x1"], 2),
                round(w["y1"], 2),
                round(w["x2"], 2),
                round(w["y2"], 2),
            )
            if key not in seen:
                seen.add(key)
                unique.append(w)
        return unique

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
        s.fire_compartments = [
            FireCompartment.from_dict(fc) for fc in d.get("fire_compartments", [])
        ]
        return s

# ============================================================
# 单体建筑类
# ============================================================
class Building:
    """单体建筑 - 包含多个楼层"""
    
    def __init__(
        self,
        name: str = "建筑1",
        length: float = 20.0,
        width: float = 15.0,
        wall_thickness: float = 0.25,
    ):
        self.name = name
        self.length = length
        self.width = width
        self.wall_thickness = wall_thickness
        self.x_offset: float = 0.0
        self.y_offset: float = 0.0
        self.rotation: float = 0.0  # rotation angle in degrees
        self.stories: List[Story] = [Story(name="1F", height=3.0)]

        self.roof = {"thickness": 0.2, "material": "CONCRETE"}
        self.materials = {"walls": "CONCRETE", "floor": "CONCRETE", "roof": "CONCRETE"}
        self.specialized_components: list = []  # e.g. [{"key": "AIRCRAFT_SMALL", "count": 2}]
        self.update_z_offsets()
        self.update_external_walls()

    @property
    def total_height(self) -> float:
        return sum(s.height for s in self.stories)

    def update_z_offsets(self):
        z = 0.0
        for s in self.stories:
            s.z_bottom = z
            z += s.height

    def update_external_walls(self):
        L, W, t = self.length, self.width, self.wall_thickness
        ext_walls = [
            {
                "name": "南墙",
                "x1": 0,
                "y1": 0,
                "x2": L,
                "y2": 0,
                "thickness": t,
                "is_external": True,
            },
            {
                "name": "北墙",
                "x1": 0,
                "y1": W,
                "x2": L,
                "y2": W,
                "thickness": t,
                "is_external": True,
            },
            {
                "name": "西墙",
                "x1": 0,
                "y1": 0,
                "x2": 0,
                "y2": W,
                "thickness": t,
                "is_external": True,
            },
            {
                "name": "东墙",
                "x1": L,
                "y1": 0,
                "x2": L,
                "y2": W,
                "thickness": t,
                "is_external": True,
            },
        ]
        for story in self.stories:
            # Keep internal walls AND fire partition walls
            internal = [
                w
                for w in story.walls
                if not w.get("is_external") and not w.get("is_fire_partition")
            ]
            partition = [w for w in story.walls if w.get("is_fire_partition")]
            story.walls = copy.deepcopy(ext_walls) + internal + partition
            for w in story.walls:
                w["height"] = story.height

    def add_story(self, name: str = None, height: float = 3.0) -> Story:
        idx = len(self.stories) + 1
        s = Story(name=name or f"{idx}F", height=height)
        self.stories.append(s)
        self.update_z_offsets()
        self.update_external_walls()
        return s

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "length": self.length,
            "width": self.width,
            "wall_thickness": self.wall_thickness,
            "x_offset": self.x_offset,
            "y_offset": self.y_offset,
            "stories": [s.to_dict() for s in self.stories],
            "roof": self.roof,
            "materials": self.materials.copy(),
            "specialized_components": self.specialized_components,
        }
    
    @classmethod
    def from_dict(cls, d) -> "Building":
        b = cls(
            name=d.get("name", "建筑1"),
            length=d.get("length", 20.0),
            width=d.get("width", 15.0),
            wall_thickness=d.get("wall_thickness", 0.25),
        )
        b.x_offset = d.get("x_offset", 0.0)
        b.y_offset = d.get("y_offset", 0.0)
        if "stories" in d:
            b.stories = [Story.from_dict(s) for s in d["stories"]]
        b.roof = d.get("roof", {"thickness": 0.2, "material": "CONCRETE"})
        b.materials = d.get("materials", b.materials)
        b.specialized_components = d.get("specialized_components", [])
        b.update_z_offsets()
        b.update_external_walls()
        return b


# ============================================================
# 建筑群类
# ============================================================
class BuildingGroup:
    """建筑群 - 包含多个单体建筑"""

    def __init__(self):
        self.buildings: List[Building] = [Building()]
        self.fire_separation: float = 0.0
        self.heat_source = {
            "enabled": False,
            "azimuth": 0,  # 0-360 degrees, 0=north, 90=east
            "distance": 3.0,
            "width_ratio": 1.5,
            "height_ratio": 1.0,
            "radiation_flux": 50.0,
            "use_ramp": False,
            "elevation": 0,
            "duration": 1.36,
        }
        self.simulation_time = 20.0
        self.domain = {"grid_size": 0.5}
        self.output = {
            "slices": True,
            "devices": True,
            "custom_slices": [],
            "custom_devices": [],
        }

    def add_building(self, building: Building = None) -> Building:
        if building is None:
            building = Building(name=f"建筑{len(self.buildings) + 1}")
        self.buildings.append(building)
        return building

    def remove_building(self, index: int):
        if len(self.buildings) > 1:
            del self.buildings[index]
    
    @property
    def total_length(self) -> float:
        if not self.buildings:
            return 0
        return max(b.length for b in self.buildings)

    @property
    def total_width(self) -> float:
        if not self.buildings:
            return 0
        return max(b.width for b in self.buildings)

    @property
    def max_height(self) -> float:
        if not self.buildings:
            return 0
        return max(b.total_height for b in self.buildings)

    def to_dict(self) -> dict:
        return {
            "buildings": [b.to_dict() for b in self.buildings],
            "fire_separation": self.fire_separation,
            "heat_source": self.heat_source.copy(),
            "simulation_time": self.simulation_time,
            "domain": self.domain.copy(),
            "output": self.output.copy(),
        }

    @classmethod
    def from_dict(cls, d) -> "BuildingGroup":
        g = cls()
        g.buildings = [Building.from_dict(b) for b in d["buildings"]]
        g.fire_separation = d.get("fire_separation", 5.0)
        g.heat_source = d.get("heat_source", g.heat_source)
        g.simulation_time = d.get("simulation_time", 20.0)
        g.domain = d.get("domain", g.domain)
        g.output = d.get("output", g.output)
        return g


# ============================================================
# 建筑模型类（兼容旧接口）
# ============================================================
class BuildingModel:
    """
    建筑模型数据类
    20260305 支持多层建筑，每层单独定义墙体/开口/可燃物，自动计算层高和外墙高度。
    20260320 支持建筑群，多个独立建筑每个有自己的外墙。
    """

    def __init__(self):
        self.chid = "building"
        # 使用建筑群
        self.building_group = BuildingGroup()

        # 兼容旧接口的属性
        self.length = 20.0
        self.width = 15.0
        self.wall_thickness = 0.25
        self.stories: List[Story] = self.building_group.buildings[0].stories
        self.roof = self.building_group.buildings[0].roof
        self.materials = self.building_group.buildings[0].materials

        self.heat_source = self.building_group.heat_source
        self.simulation_time = self.building_group.simulation_time
        self.domain = self.building_group.domain
        self.output = self.building_group.output

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
        return self.building_group.max_height

    def update_z_offsets(self):
        """计算每层的z偏移"""
        for building in self.building_group.buildings:
            building.update_z_offsets()

    def add_story(
        self, name: str = None, height: float = 3.0, copy_from: int = -1
    ) -> Story:
        """添加一层"""
        building = self.building_group.buildings[0]
        return building.add_story(name, height)

    def remove_story(self, index: int):
        building = self.building_group.buildings[0]
        if len(building.stories) > 1:
            del building.stories[index]
            building.update_z_offsets()

    def get_story(self, index: int) -> Story:
        return self.stories[index]
    
    # ── 外墙（每层都要） ────────────────────────────────
    def update_external_walls(self):
        """为每栋建筑每层生成外墙"""
        for building in self.building_group.buildings:
            building.update_external_walls()

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
            "building_group": self.building_group.to_dict(),
            "heat_source": self.heat_source.copy(),
            "domain": self.domain.copy(),
            "simulation_time": self.simulation_time,
            "output": self.output.copy()
        }
    
    def from_dict(self, data: dict):
        """从字典加载"""
        self.chid = data.get("chid", "building")
        self.building_group = BuildingGroup.from_dict(data["building_group"])
        # 同步兼容属性
        if self.building_group.buildings:
            b = self.building_group.buildings[0]
            self.length = b.length
            self.width = b.width
            self.wall_thickness = b.wall_thickness
            self.stories = b.stories
            self.roof = b.roof
            self.materials = b.materials
       
        self.heat_source = data.get("heat_source", self.heat_source)
        self.domain = data.get("domain", self.domain)
        self.simulation_time = data.get("simulation_time", 20.0)
        self.output = data.get("output", self.output)
        
        self.update_z_offsets()
        if not any(w.get("is_external") for s in self.stories for w in s.walls):
            self.update_external_walls()