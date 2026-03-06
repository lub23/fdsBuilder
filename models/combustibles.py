#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@File  : combustibles.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 2.0
@Desc  : Combustible model class for FDS generation
'''


"""可燃物模型与分布生成器"""

import random
import math
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Tuple


class DistributionMethod(Enum):
    UNIFORM_GRID = "均匀网格"
    RANDOM = "随机分布"
    ALONG_WALLS = "沿墙分布"
    CLUSTERED = "聚集分布"
    DIAGONAL = "对角线分布"
    RING = "环形分布"


# ── 可燃物模板库 ──────────────────────────────────────────────
COMBUSTIBLE_PRESETS = {
    "WOOD_TABLE": {
        "name": "木桌",
        "length": 1.2, "width": 0.8, "height": 0.75,
        "hrrpua": 300, "ignition_temp": 350, "color": "BROWN",
        "matl": {"DENSITY": 500, "CONDUCTIVITY": 0.14,
                 "SPECIFIC_HEAT": 2.85, "HEAT_OF_COMBUSTION": 18000,
                 "REFERENCE_TEMPERATURE": 350},
    },
    "WOOD_CHAIR": {
        "name": "木椅",
        "length": 0.5, "width": 0.5, "height": 0.9,
        "hrrpua": 250, "ignition_temp": 350, "color": "BROWN",
        "matl": {"DENSITY": 450, "CONDUCTIVITY": 0.14,
                 "SPECIFIC_HEAT": 2.85, "HEAT_OF_COMBUSTION": 18000,
                 "REFERENCE_TEMPERATURE": 350},
    },
    "FABRIC_SOFA": {
        "name": "布艺沙发",
        "length": 2.0, "width": 0.9, "height": 0.85,
        "hrrpua": 500, "ignition_temp": 280, "color": "RED",
        "matl": {"DENSITY": 100, "CONDUCTIVITY": 0.16,
                 "SPECIFIC_HEAT": 1.35, "HEAT_OF_COMBUSTION": 25000,
                 "REFERENCE_TEMPERATURE": 280},
    },
    "BOOKSHELF": {
        "name": "书架(含书)",
        "length": 1.0, "width": 0.4, "height": 1.8,
        "hrrpua": 400, "ignition_temp": 340, "color": "SALMON",
        "matl": {"DENSITY": 650, "CONDUCTIVITY": 0.14,
                 "SPECIFIC_HEAT": 2.5, "HEAT_OF_COMBUSTION": 16000,
                 "REFERENCE_TEMPERATURE": 340},
    },
    "PLASTIC_BIN": {
        "name": "塑料垃圾桶",
        "length": 0.4, "width": 0.4, "height": 0.6,
        "hrrpua": 600, "ignition_temp": 260, "color": "GRAY",
        "matl": {"DENSITY": 950, "CONDUCTIVITY": 0.18,
                 "SPECIFIC_HEAT": 1.67, "HEAT_OF_COMBUSTION": 40000,
                 "REFERENCE_TEMPERATURE": 260},
    },
    "CARDBOARD_BOX": {
        "name": "纸箱",
        "length": 0.6, "width": 0.4, "height": 0.5,
        "hrrpua": 350, "ignition_temp": 300, "color": "KHAKI",
        "matl": {"DENSITY": 200, "CONDUCTIVITY": 0.06,
                 "SPECIFIC_HEAT": 1.33, "HEAT_OF_COMBUSTION": 16000,
                 "REFERENCE_TEMPERATURE": 300},
    },
    "MATTRESS": {
        "name": "床垫",
        "length": 2.0, "width": 1.5, "height": 0.25,
        "hrrpua": 450, "ignition_temp": 270, "color": "IVORY",
        "matl": {"DENSITY": 150, "CONDUCTIVITY": 0.12,
                 "SPECIFIC_HEAT": 1.5, "HEAT_OF_COMBUSTION": 30000,
                 "REFERENCE_TEMPERATURE": 270},
    },
    "CURTAIN": {
        "name": "窗帘(折叠)",
        "length": 0.3, "width": 1.5, "height": 2.0,
        "hrrpua": 700, "ignition_temp": 250, "color": "MAGENTA",
        "matl": {"DENSITY": 80, "CONDUCTIVITY": 0.1,
                 "SPECIFIC_HEAT": 1.2, "HEAT_OF_COMBUSTION": 28000,
                 "REFERENCE_TEMPERATURE": 250},
    },
}


@dataclass
class Combustible:
    """单个可燃物"""
    id: str = ""
    preset_key: str = "WOOD_TABLE"
    name: str = "木桌"
    # 位置
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    # 尺寸
    length: float = 1.2
    width: float = 0.8
    height: float = 0.75
    # 燃烧参数
    hrrpua: float = 300.0       # kW/m²
    ignition_temp: float = 350  # °C
    color: str = "BROWN"
    matl: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = f"CB_{uuid.uuid4().hex[:6]}"

    @classmethod
    def from_preset(cls, key: str, x=0, y=0, z=0) -> "Combustible":
        p = COMBUSTIBLE_PRESETS[key]
        return cls(
            preset_key=key, name=p["name"],
            x=x, y=y, z=z,
            length=p["length"], width=p["width"], height=p["height"],
            hrrpua=p["hrrpua"], ignition_temp=p["ignition_temp"],
            color=p["color"], matl=dict(p["matl"]),
        )

    @property
    def bounds(self) -> Tuple[float, float, float, float, float, float]:
        return (self.x, self.x + self.length,
                self.y, self.y + self.width,
                self.z, self.z + self.height)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Combustible":
        return cls(**d)


class CombustibleManager:
    """可燃物管理器：增删改 + 分布生成"""

    def __init__(self):
        self.items: List[Combustible] = []

    # ── CRUD ─────────────────────────────────────────────
    def add(self, item: Combustible):
        self.items.append(item)

    def remove(self, item_id: str):
        self.items = [c for c in self.items if c.id != item_id]

    def get(self, item_id: str) -> Optional[Combustible]:
        return next((c for c in self.items if c.id == item_id), None)

    def clear(self):
        self.items.clear()

    # ── 序列化 ───────────────────────────────────────────
    def to_list(self) -> list:
        return [c.to_dict() for c in self.items]

    def from_list(self, data: list):
        self.items = [Combustible.from_dict(d) for d in data]

    # ── 分布生成 ─────────────────────────────────────────
    def generate(self, preset_key: str, count: int,
                method: DistributionMethod,
                room_length: float, room_width: float,
                wall_thickness: float = 0.2,
                margin: float = 0.3,
                seed: Optional[int] = None,
                **kwargs) -> List[Combustible]:
        if seed is not None:
            random.seed(seed)

        p = COMBUSTIBLE_PRESETS[preset_key]
        obj_l, obj_w = p["length"], p["width"]

        # 建筑内部空间边界
        interior_x_min = wall_thickness
        interior_x_max = room_length - wall_thickness
        interior_y_min = wall_thickness
        interior_y_max = room_width - wall_thickness

        # 通用放置边界（含margin，且保证物体不超出）
        x_min = interior_x_min + margin
        x_max = interior_x_max - margin - obj_l
        y_min = interior_y_min + margin
        y_max = interior_y_max - margin - obj_w

        if x_max <= x_min or y_max <= y_min:
            return []

        positions = {
            DistributionMethod.UNIFORM_GRID: self._grid,
            DistributionMethod.RANDOM:       self._random,
            DistributionMethod.ALONG_WALLS:  self._along_walls,
            DistributionMethod.CLUSTERED:    self._clustered,
            DistributionMethod.DIAGONAL:     self._diagonal,
            DistributionMethod.RING:         self._ring,
        }[method](
            count, x_min, x_max, y_min, y_max, obj_l, obj_w,
            # 沿墙分布需要内部边界
            interior_x_min=interior_x_min, interior_x_max=interior_x_max,
            interior_y_min=interior_y_min, interior_y_max=interior_y_max,
            **kwargs
        )

        new_items = []
        for (x, y) in positions[:count]:
            # 最终裁剪，确保不超出内部空间
            x = max(interior_x_min, min(x, interior_x_max - obj_l))
            y = max(interior_y_min, min(y, interior_y_max - obj_w))
            cb = Combustible.from_preset(
                preset_key, x=round(x, 2), y=round(y, 2), z=0)
            self.items.append(cb)
            new_items.append(cb)
        return new_items

    # ── 分布算法 ─────────────────────────────────────────
    @staticmethod
    def _grid(count, x_min, x_max, y_min, y_max, ol, ow, **kw):
        cols = max(1, int(math.ceil(math.sqrt(count * (x_max - x_min) / (y_max - y_min)))))
        rows = max(1, int(math.ceil(count / cols)))
        dx = (x_max - x_min) / max(cols, 1)
        dy = (y_max - y_min) / max(rows, 1)
        pts = []
        for r in range(rows):
            for c in range(cols):
                if len(pts) >= count:
                    break
                pts.append((x_min + c * dx + dx / 2 - ol / 2,
                            y_min + r * dy + dy / 2 - ow / 2))
        return pts

    @staticmethod
    def _random(count, x_min, x_max, y_min, y_max, ol, ow, **kw):
        pts = []
        max_attempts = count * 50
        for _ in range(max_attempts):
            if len(pts) >= count:
                break
            x = random.uniform(x_min, x_max)
            y = random.uniform(y_min, y_max)
            # 简单防重叠
            ok = all(abs(x - px) > ol * 0.8 or abs(y - py) > ow * 0.8
                     for px, py in pts)
            if ok:
                pts.append((x, y))
        return pts

    @staticmethod
    def _along_walls(count, x_min, x_max, y_min, y_max, ol, ow,
                    interior_x_min=0, interior_x_max=0,
                    interior_y_min=0, interior_y_max=0, **kw):
        """沿墙分布：物体紧贴内墙面"""
        pts = []
        gap = 0.1  # 离墙面间隙

        # 四面墙的可放置段
        segments = []

        # 南墙 (y_min侧)：物体y紧贴南墙内面
        wall_y = interior_y_min + gap
        x = interior_x_min + gap
        while x + ol <= interior_x_max - gap:
            segments.append((x, wall_y, 'south'))
            x += ol + 0.3

        # 北墙 (y_max侧)
        wall_y = interior_y_max - gap - ow
        x = interior_x_min + gap
        while x + ol <= interior_x_max - gap:
            segments.append((x, wall_y, 'north'))
            x += ol + 0.3

        # 西墙 (x_min侧)
        wall_x = interior_x_min + gap
        y = interior_y_min + gap + ow  # 跳过角落
        while y + ow <= interior_y_max - gap - ow:
            segments.append((wall_x, y, 'west'))
            y += ow + 0.3

        # 东墙 (x_max侧)
        wall_x = interior_x_max - gap - ol
        y = interior_y_min + gap + ow
        while y + ow <= interior_y_max - gap - ow:
            segments.append((wall_x, y, 'east'))
            y += ow + 0.3

        # 均匀选取
        if len(segments) > count:
            step = len(segments) / count
            selected = [segments[int(i * step)] for i in range(count)]
        else:
            selected = segments

        return [(x, y) for x, y, _ in selected]

    @staticmethod
    def _clustered(count, x_min, x_max, y_min, y_max, ol, ow,
                   clusters=3, spread=1.5, **kw):
        pts = []
        centers = [(random.uniform(x_min + 1, x_max - 1),
                     random.uniform(y_min + 1, y_max - 1))
                    for _ in range(min(clusters, count))]
        per_cluster = max(1, count // len(centers))
        for cx, cy in centers:
            for _ in range(per_cluster):
                if len(pts) >= count:
                    break
                x = max(x_min, min(x_max, random.gauss(cx, spread)))
                y = max(y_min, min(y_max, random.gauss(cy, spread)))
                pts.append((x, y))
        return pts

    @staticmethod
    def _diagonal(count, x_min, x_max, y_min, y_max, ol, ow, **kw):
        pts = []
        for i in range(count):
            t = i / max(count - 1, 1)
            pts.append((x_min + t * (x_max - x_min),
                        y_min + t * (y_max - y_min)))
        return pts

    @staticmethod
    def _ring(count, x_min, x_max, y_min, y_max, ol, ow, **kw):
        cx = (x_min + x_max) / 2
        cy = (y_min + y_max) / 2
        rx = (x_max - x_min) / 2 * 0.7
        ry = (y_max - y_min) / 2 * 0.7
        pts = []
        for i in range(count):
            a = 2 * math.pi * i / count
            pts.append((cx + rx * math.cos(a) - ol / 2,
                        cy + ry * math.sin(a) - ow / 2))
        return pts

    # ── 碰撞检测 ─────────────────────────────────────────
    def check_overlaps(self) -> List[Tuple[str, str]]:
        """返回所有重叠的可燃物id对"""
        overlaps = []
        for i, a in enumerate(self.items):
            for b in self.items[i + 1:]:
                if (a.x < b.x + b.length and a.x + a.length > b.x and
                    a.y < b.y + b.width and a.y + a.width > b.y):
                    overlaps.append((a.id, b.id))
        return overlaps