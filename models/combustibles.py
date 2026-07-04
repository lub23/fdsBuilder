#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File  : combustibles.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 2.0
@Desc  : Combustible model class for FDS generation
"""

import random
import math
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Tuple
from models.materials import COMBUSTIBLE_LIBRARY


class DistributionMethod(Enum):
    UNIFORM_GRID = "均匀网格"
    RANDOM = "随机分布"
    ALONG_WALLS = "沿墙分布"
    CLUSTERED = "聚集分布"
    DIAGONAL = "对角线分布"
    RING = "环形分布"


@dataclass
class ComponentPart:
    """Single OBST within a specialized component"""

    dx: float  # relative X offset from component origin
    dy: float
    dz: float
    length: float
    width: float
    height: float
    material_key: str  # key into MATERIAL_LIBRARY or COMBUSTIBLE_LIBRARY
    surf_id: str = ""  # custom SURF if needed
    ignition_temp: float = 0.0  # 0 means use component-level default


@dataclass
class SpecializedComponent:
    """Multi-OBST facility-specific object (e.g. aircraft, car, electrolysis cell)"""

    key: str
    name: str
    category: str  # e.g. "hangar", "garage", "electrolysis"
    size_class: str  # "large", "medium", "small"
    parts: List[ComponentPart] = field(default_factory=list)
    total_length: float = 10.0
    total_width: float = 5.0
    total_height: float = 3.0
    hrrpua: float = 300.0
    ignition_temp: float = 350.0

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "category": self.category,
            "size_class": self.size_class,
            "parts": [
                {
                    "dx": p.dx,
                    "dy": p.dy,
                    "dz": p.dz,
                    "length": p.length,
                    "width": p.width,
                    "height": p.height,
                    "material_key": p.material_key,
                    "surf_id": p.surf_id,
                    "ignition_temp": p.ignition_temp,
                }
                for p in self.parts
            ],
            "total_length": self.total_length,
            "total_width": self.total_width,
            "total_height": self.total_height,
            "hrrpua": self.hrrpua,
            "ignition_temp": self.ignition_temp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpecializedComponent":
        parts = [ComponentPart(**p) for p in d.get("parts", [])]
        return cls(
            key=d["key"],
            name=d["name"],
            category=d.get("category", ""),
            size_class=d.get("size_class", "medium"),
            parts=parts,
            total_length=d.get("total_length", 10.0),
            total_width=d.get("total_width", 5.0),
            total_height=d.get("total_height", 3.0),
            hrrpua=d.get("hrrpua", 300.0),
            ignition_temp=d.get("ignition_temp", 350.0),
        )


SPECIALIZED_COMPONENTS = {
    # ══════════════════════════════════════════════
    # Aircraft (12-14 OBST per model)
    # ══════════════════════════════════════════════
    "AIRCRAFT_SMALL": SpecializedComponent(
        key="AIRCRAFT_SMALL",
        name="小型固定翼飞机",
        category="hangar",
        size_class="small",
        total_length=12.0,
        total_width=11.0,
        total_height=3.8,
        hrrpua=1200,
        ignition_temp=210,
        parts=[
            # 1. 前机身
            ComponentPart(
                dx=0,
                dy=3.8,
                dz=0.6,
                length=4.0,
                width=3.4,
                height=1.8,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 2. 驾驶舱玻璃罩
            ComponentPart(
                dx=0.5,
                dy=4.0,
                dz=2.4,
                length=2.0,
                width=3.0,
                height=0.8,
                material_key="GLASS",
                surf_id="GLASS_SURF",
            ),
            # 3. 后机身
            ComponentPart(
                dx=4.0,
                dy=4.0,
                dz=0.6,
                length=7.0,
                width=3.0,
                height=1.6,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 4. 尾锥
            ComponentPart(
                dx=11.0,
                dy=4.5,
                dz=0.8,
                length=1.0,
                width=2.0,
                height=1.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 5. 左机翼
            ComponentPart(
                dx=3.0,
                dy=0,
                dz=1.0,
                length=3.5,
                width=3.8,
                height=0.25,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 6. 右机翼
            ComponentPart(
                dx=3.0,
                dy=7.2,
                dz=1.0,
                length=3.5,
                width=3.8,
                height=0.25,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 7. 左发动机吊舱
            ComponentPart(
                dx=3.5,
                dy=1.5,
                dz=0.3,
                length=2.0,
                width=1.0,
                height=0.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 8. 右发动机吊舱
            ComponentPart(
                dx=3.5,
                dy=8.5,
                dz=0.3,
                length=2.0,
                width=1.0,
                height=0.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 9. 垂直尾翼
            ComponentPart(
                dx=10.0,
                dy=5.0,
                dz=2.2,
                length=1.5,
                width=0.2,
                height=1.6,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 10. 水平尾翼
            ComponentPart(
                dx=10.0,
                dy=3.0,
                dz=2.2,
                length=1.5,
                width=5.0,
                height=0.15,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 11. 前起落架
            ComponentPart(
                dx=1.0,
                dy=4.8,
                dz=0,
                length=0.6,
                width=1.4,
                height=0.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 12. 主起落架
            ComponentPart(
                dx=5.0,
                dy=3.0,
                dz=0,
                length=0.8,
                width=5.0,
                height=0.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "AIRCRAFT_MEDIUM": SpecializedComponent(
        key="AIRCRAFT_MEDIUM",
        name="中型运输机",
        category="hangar",
        size_class="medium",
        total_length=25.0,
        total_width=22.0,
        total_height=7.0,
        hrrpua=1400,
        ignition_temp=210,
        parts=[
            # 1. 前机身
            ComponentPart(
                dx=0,
                dy=8.5,
                dz=1.0,
                length=8.0,
                width=5.0,
                height=3.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 2. 驾驶舱
            ComponentPart(
                dx=0.5,
                dy=9.0,
                dz=4.5,
                length=3.0,
                width=4.0,
                height=1.2,
                material_key="GLASS",
                surf_id="GLASS_SURF",
            ),
            # 3. 中机身
            ComponentPart(
                dx=8.0,
                dy=8.5,
                dz=1.0,
                length=10.0,
                width=5.0,
                height=3.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 4. 后机身/尾段
            ComponentPart(
                dx=18.0,
                dy=9.0,
                dz=1.5,
                length=7.0,
                width=4.0,
                height=2.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 5. 左机翼
            ComponentPart(
                dx=8.0,
                dy=0,
                dz=2.0,
                length=6.0,
                width=8.5,
                height=0.4,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 6. 右机翼
            ComponentPart(
                dx=8.0,
                dy=13.5,
                dz=2.0,
                length=6.0,
                width=8.5,
                height=0.4,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 7. 左内发动机
            ComponentPart(
                dx=9.0,
                dy=4.0,
                dz=1.0,
                length=2.5,
                width=1.2,
                height=1.2,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 8. 右内发动机
            ComponentPart(
                dx=9.0,
                dy=16.8,
                dz=1.0,
                length=2.5,
                width=1.2,
                height=1.2,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 9. 左外发动机
            ComponentPart(
                dx=9.5,
                dy=1.5,
                dz=1.2,
                length=2.0,
                width=1.0,
                height=1.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 10. 右外发动机
            ComponentPart(
                dx=9.5,
                dy=19.5,
                dz=1.2,
                length=2.0,
                width=1.0,
                height=1.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 11. 垂直尾翼
            ComponentPart(
                dx=22.0,
                dy=10.0,
                dz=4.0,
                length=3.0,
                width=0.3,
                height=3.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 12. 水平尾翼
            ComponentPart(
                dx=22.0,
                dy=7.0,
                dz=4.0,
                length=3.0,
                width=8.0,
                height=0.2,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 13. 主起落架
            ComponentPart(
                dx=11.0,
                dy=7.5,
                dz=0,
                length=1.5,
                width=7.0,
                height=1.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "AIRCRAFT_LARGE": SpecializedComponent(
        key="AIRCRAFT_LARGE",
        name="大型运输机",
        category="hangar",
        size_class="large",
        total_length=40.0,
        total_width=36.0,
        total_height=12.0,
        hrrpua=1500,
        ignition_temp=210,
        parts=[
            # 1. 前机身（含机头）
            ComponentPart(
                dx=0,
                dy=14.0,
                dz=2.0,
                length=12.0,
                width=8.0,
                height=5.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 2. 驾驶舱
            ComponentPart(
                dx=0.5,
                dy=15.0,
                dz=7.0,
                length=4.0,
                width=6.0,
                height=2.0,
                material_key="GLASS",
                surf_id="GLASS_SURF",
            ),
            # 3. 中机身（货舱）
            ComponentPart(
                dx=12.0,
                dy=14.0,
                dz=2.0,
                length=16.0,
                width=8.0,
                height=5.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 4. 后机身
            ComponentPart(
                dx=28.0,
                dy=15.0,
                dz=3.0,
                length=12.0,
                width=6.0,
                height=4.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 5. 左机翼
            ComponentPart(
                dx=12.0,
                dy=0,
                dz=3.5,
                length=10.0,
                width=14.0,
                height=0.6,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 6. 右机翼
            ComponentPart(
                dx=12.0,
                dy=22.0,
                dz=3.5,
                length=10.0,
                width=14.0,
                height=0.6,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 7. 左内发动机
            ComponentPart(
                dx=14.0,
                dy=7.0,
                dz=2.0,
                length=3.5,
                width=2.0,
                height=2.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 8. 右内发动机
            ComponentPart(
                dx=14.0,
                dy=27.0,
                dz=2.0,
                length=3.5,
                width=2.0,
                height=2.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 9. 左外发动机
            ComponentPart(
                dx=14.5,
                dy=3.0,
                dz=2.5,
                length=3.0,
                width=1.5,
                height=1.5,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 10. 右外发动机
            ComponentPart(
                dx=14.5,
                dy=31.5,
                dz=2.5,
                length=3.0,
                width=1.5,
                height=1.5,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 11. 垂直尾翼
            ComponentPart(
                dx=35.0,
                dy=16.5,
                dz=7.0,
                length=5.0,
                width=3.0,
                height=5.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 12. 水平尾翼
            ComponentPart(
                dx=35.0,
                dy=10.0,
                dz=7.0,
                length=5.0,
                width=16.0,
                height=0.3,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 13. 主起落架
            ComponentPart(
                dx=17.0,
                dy=12.0,
                dz=0,
                length=2.5,
                width=12.0,
                height=2.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 14. 左翼尖小翼
            ComponentPart(
                dx=18.0,
                dy=0,
                dz=4.1,
                length=2.0,
                width=0.3,
                height=1.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
        ],
    ),
    # ══════════════════════════════════════════════
    # Vehicles (8 OBST)
    # ══════════════════════════════════════════════
    "VEHICLE_CAR": SpecializedComponent(
        key="VEHICLE_CAR",
        name="小汽车",
        category="garage",
        size_class="small",
        total_length=4.5,
        total_width=1.8,
        total_height=1.5,
        hrrpua=400,
        ignition_temp=300,
        parts=[
            # 1. 底盘
            ComponentPart(
                dx=0,
                dy=0,
                dz=0.3,
                length=4.5,
                width=1.8,
                height=0.3,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 2. 引擎盖
            ComponentPart(
                dx=0,
                dy=0.1,
                dz=0.6,
                length=1.2,
                width=1.6,
                height=0.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 3. 车顶
            ComponentPart(
                dx=1.2,
                dy=0.1,
                dz=0.6,
                length=2.0,
                width=1.6,
                height=0.9,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 4. 后备箱
            ComponentPart(
                dx=3.2,
                dy=0.1,
                dz=0.6,
                length=1.3,
                width=1.6,
                height=0.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 5. 左前轮
            ComponentPart(
                dx=0.3,
                dy=-0.05,
                dz=0,
                length=0.5,
                width=0.25,
                height=0.5,
                material_key="GASOLINE",
                surf_id="GASOLINE_SURF",
            ),
            # 6. 右前轮
            ComponentPart(
                dx=0.3,
                dy=1.6,
                dz=0,
                length=0.5,
                width=0.25,
                height=0.5,
                material_key="GASOLINE",
                surf_id="GASOLINE_SURF",
            ),
            # 7. 左后轮
            ComponentPart(
                dx=3.5,
                dy=-0.05,
                dz=0,
                length=0.5,
                width=0.25,
                height=0.5,
                material_key="GASOLINE",
                surf_id="GASOLINE_SURF",
            ),
            # 8. 右后轮
            ComponentPart(
                dx=3.5,
                dy=1.6,
                dz=0,
                length=0.5,
                width=0.25,
                height=0.5,
                material_key="GASOLINE",
                surf_id="GASOLINE_SURF",
            ),
        ],
    ),
    "VEHICLE_TRUCK": SpecializedComponent(
        key="VEHICLE_TRUCK",
        name="货车",
        category="garage",
        size_class="medium",
        total_length=8.0,
        total_width=2.4,
        total_height=3.0,
        hrrpua=500,
        ignition_temp=300,
        parts=[
            # 1. 驾驶室
            ComponentPart(
                dx=0,
                dy=0,
                dz=0.5,
                length=2.5,
                width=2.4,
                height=2.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 2. 驾驶室挡风玻璃
            ComponentPart(
                dx=0,
                dy=0.3,
                dz=2.0,
                length=0.3,
                width=1.8,
                height=0.8,
                material_key="GLASS",
                surf_id="GLASS_SURF",
            ),
            # 3. 货厢底板
            ComponentPart(
                dx=2.5,
                dy=0,
                dz=0.5,
                length=5.5,
                width=2.4,
                height=0.2,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 4. 货厢左侧板
            ComponentPart(
                dx=2.5,
                dy=0,
                dz=0.7,
                length=5.5,
                width=0.1,
                height=2.3,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 5. 货厢右侧板
            ComponentPart(
                dx=2.5,
                dy=2.3,
                dz=0.7,
                length=5.5,
                width=0.1,
                height=2.3,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 6. 货厢后板
            ComponentPart(
                dx=7.9,
                dy=0,
                dz=0.7,
                length=0.1,
                width=2.4,
                height=2.3,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 7. 前轴轮组
            ComponentPart(
                dx=0.5,
                dy=-0.1,
                dz=0,
                length=0.6,
                width=2.6,
                height=0.5,
                material_key="GASOLINE",
                surf_id="GASOLINE_SURF",
            ),
            # 8. 后轴轮组
            ComponentPart(
                dx=6.0,
                dy=-0.1,
                dz=0,
                length=0.8,
                width=2.6,
                height=0.5,
                material_key="GASOLINE",
                surf_id="GASOLINE_SURF",
            ),
        ],
    ),
    # ══════════════════════════════════════════════
    # Electrolysis cells (10 OBST)
    # ══════════════════════════════════════════════
    "ELECTROLYSIS_CELL": SpecializedComponent(
        key="ELECTROLYSIS_CELL",
        name="电解槽生产线",
        category="electrolysis",
        size_class="large",
        total_length=15.0,
        total_width=3.0,
        total_height=2.5,
        hrrpua=200,
        ignition_temp=500,
        parts=[
            # 1. 槽体底座
            ComponentPart(
                dx=0,
                dy=0,
                dz=0,
                length=15.0,
                width=3.0,
                height=0.5,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 2. 槽体左壁
            ComponentPart(
                dx=0,
                dy=0,
                dz=0.5,
                length=15.0,
                width=0.15,
                height=1.5,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 3. 槽体右壁
            ComponentPart(
                dx=0,
                dy=2.85,
                dz=0.5,
                length=15.0,
                width=0.15,
                height=1.5,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 4. 电解质层
            ComponentPart(
                dx=0.1,
                dy=0.15,
                dz=0.5,
                length=14.8,
                width=2.7,
                height=1.0,
                material_key="ELECTROLYTE",
                surf_id="ELECTROLYTE_SURF",
            ),
            # 5. 阳极块 #1
            ComponentPart(
                dx=1.0,
                dy=0.6,
                dz=1.5,
                length=2.5,
                width=0.5,
                height=0.6,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 6. 阳极块 #2
            ComponentPart(
                dx=4.5,
                dy=0.6,
                dz=1.5,
                length=2.5,
                width=0.5,
                height=0.6,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 7. 阳极块 #3
            ComponentPart(
                dx=8.0,
                dy=0.6,
                dz=1.5,
                length=2.5,
                width=0.5,
                height=0.6,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 8. 阳极块 #4
            ComponentPart(
                dx=11.5,
                dy=0.6,
                dz=1.5,
                length=2.5,
                width=0.5,
                height=0.6,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 9. 导电排（上方横梁）
            ComponentPart(
                dx=0,
                dy=0.5,
                dz=2.1,
                length=15.0,
                width=2.0,
                height=0.2,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 10. 连接管道
            ComponentPart(
                dx=0.5,
                dy=1.2,
                dz=2.3,
                length=14.0,
                width=0.6,
                height=0.2,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "ELECTROLYSIS_CELL_MEDIUM": SpecializedComponent(
        key="ELECTROLYSIS_CELL_MEDIUM",
        name="中型电解槽",
        category="electrolysis",
        size_class="medium",
        total_length=8.0,
        total_width=2.0,
        total_height=2.0,
        hrrpua=200,
        ignition_temp=500,
        parts=[
            # 1. 槽体底座
            ComponentPart(
                dx=0,
                dy=0,
                dz=0,
                length=8.0,
                width=2.0,
                height=0.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 2. 槽体左壁
            ComponentPart(
                dx=0,
                dy=0,
                dz=0.4,
                length=8.0,
                width=0.1,
                height=1.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 3. 槽体右壁
            ComponentPart(
                dx=0,
                dy=1.9,
                dz=0.4,
                length=8.0,
                width=0.1,
                height=1.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 4. 电解质
            ComponentPart(
                dx=0.1,
                dy=0.1,
                dz=0.4,
                length=7.8,
                width=1.8,
                height=0.7,
                material_key="ELECTROLYTE",
                surf_id="ELECTROLYTE_SURF",
            ),
            # 5. 阳极块 #1
            ComponentPart(
                dx=1.0,
                dy=0.4,
                dz=1.1,
                length=2.0,
                width=0.4,
                height=0.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 6. 阳极块 #2
            ComponentPart(
                dx=5.0,
                dy=0.4,
                dz=1.1,
                length=2.0,
                width=0.4,
                height=0.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 7. 导电排
            ComponentPart(
                dx=0,
                dy=0.3,
                dz=1.6,
                length=8.0,
                width=1.4,
                height=0.15,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 8. 连接管道
            ComponentPart(
                dx=0.5,
                dy=0.8,
                dz=1.75,
                length=7.0,
                width=0.4,
                height=0.15,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    # ══════════════════════════════════════════════
    # Metallurgical long equipment
    # ══════════════════════════════════════════════
    "POT_TENDING_MACHINE": SpecializedComponent(
        key="POT_TENDING_MACHINE",
        name="电解槽多功能天车",
        category="electrolysis",
        size_class="large",
        total_length=36.0,
        total_width=5.2,
        total_height=5.5,
        hrrpua=250,
        ignition_temp=450,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.0, dz=4.1,
                length=36.0, width=0.6, height=0.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=4.6, dz=4.1,
                length=36.0, width=0.6, height=0.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=0.6, dz=4.7,
                length=36.0, width=4.0, height=0.45,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=14.5, dy=1.2, dz=2.8,
                length=6.0, width=2.8, height=1.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=16.7, dy=2.0, dz=0.4,
                length=1.6, width=1.2, height=2.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=25.0, dy=0.5, dz=1.9,
                length=3.4, width=1.8, height=2.2,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=2.0, dy=0.2, dz=0.0,
                length=0.8, width=0.8, height=4.1,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=33.2, dy=4.2, dz=0.0,
                length=0.8, width=0.8, height=4.1,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "ANODE_SERVICE_CRANE": SpecializedComponent(
        key="ANODE_SERVICE_CRANE",
        name="阳极更换检修吊车",
        category="electrolysis",
        size_class="large",
        total_length=24.0,
        total_width=4.0,
        total_height=4.8,
        hrrpua=220,
        ignition_temp=450,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.2, dz=3.4,
                length=24.0, width=3.6, height=0.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=10.0, dy=1.0, dz=2.0,
                length=4.0, width=2.0, height=1.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=11.5, dy=1.6, dz=0.2,
                length=1.0, width=0.8, height=1.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=1.0, dy=0.0, dz=0.0,
                length=0.6, width=0.6, height=3.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=22.4, dy=3.4, dz=0.0,
                length=0.6, width=0.6, height=3.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "BUSBAR_DUCT_LONG": SpecializedComponent(
        key="BUSBAR_DUCT_LONG",
        name="长条母线槽/导电排",
        category="electrolysis",
        size_class="large",
        total_length=28.0,
        total_width=1.6,
        total_height=2.6,
        hrrpua=180,
        ignition_temp=500,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.2, dz=1.6,
                length=28.0, width=1.2, height=0.45,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=0.5, dz=2.1,
                length=28.0, width=0.6, height=0.25,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=0.0, dz=0.0,
                length=28.0, width=1.6, height=0.25,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=6.0, dy=0.6, dz=0.25,
                length=0.3, width=0.4, height=1.35,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=20.0, dy=0.6, dz=0.25,
                length=0.3, width=0.4, height=1.35,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "REFINING_FURNACE_BANK": SpecializedComponent(
        key="REFINING_FURNACE_BANK",
        name="精炼炉组",
        category="metallurgy",
        size_class="large",
        total_length=18.0,
        total_width=6.0,
        total_height=5.0,
        hrrpua=450,
        ignition_temp=520,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.0, dz=0.0,
                length=18.0, width=6.0, height=0.5,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=1.0, dy=0.5, dz=0.5,
                length=4.0, width=5.0, height=3.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=7.0, dy=0.5, dz=0.5,
                length=4.0, width=5.0, height=3.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=13.0, dy=0.5, dz=0.5,
                length=4.0, width=5.0, height=3.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.5, dy=2.5, dz=4.0,
                length=17.0, width=1.0, height=0.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "CONTINUOUS_CASTING_LINE": SpecializedComponent(
        key="CONTINUOUS_CASTING_LINE",
        name="连续铸造线",
        category="metallurgy",
        size_class="large",
        total_length=32.0,
        total_width=4.5,
        total_height=3.5,
        hrrpua=350,
        ignition_temp=480,
        parts=[
            ComponentPart(
                dx=0.0, dy=1.2, dz=0.6,
                length=32.0, width=2.0, height=0.7,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=2.0, dy=0.4, dz=1.3,
                length=4.0, width=3.6, height=1.2,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=10.0, dy=0.8, dz=1.3,
                length=5.0, width=2.8, height=0.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=19.0, dy=0.8, dz=1.3,
                length=5.0, width=2.8, height=0.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=27.0, dy=0.4, dz=0.0,
                length=4.5, width=3.6, height=1.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "ROLLING_MILL_LINE": SpecializedComponent(
        key="ROLLING_MILL_LINE",
        name="轧钢机列",
        category="metallurgy",
        size_class="large",
        total_length=30.0,
        total_width=5.0,
        total_height=4.0,
        hrrpua=320,
        ignition_temp=470,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.5, dz=0.0,
                length=30.0, width=4.0, height=0.5,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=2.0, dy=0.8, dz=0.5,
                length=3.5, width=3.4, height=2.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=8.0, dy=0.8, dz=0.5,
                length=3.5, width=3.4, height=2.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=14.0, dy=0.8, dz=0.5,
                length=3.5, width=3.4, height=2.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=20.0, dy=0.8, dz=0.5,
                length=3.5, width=3.4, height=2.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=2.2, dz=3.1,
                length=30.0, width=0.6, height=0.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    # ══════════════════════════════════════════════
    # Rocket vehicles (10 OBST)
    # ══════════════════════════════════════════════
    "ROCKET_VEHICLE_LARGE": SpecializedComponent(
        key="ROCKET_VEHICLE_LARGE",
        name="大型运载火箭",
        category="rocket",
        size_class="large",
        total_length=5.0,
        total_width=5.0,
        total_height=32.0,
        hrrpua=2000,
        ignition_temp=250,
        parts=[
            ComponentPart(
                dx=0.35, dy=0.35, dz=0,
                length=4.3, width=4.3, height=18.0,
                material_key="SOLID_PROPELLANT",
                surf_id="SOLID_PROPELLANT_SURF",
            ),
            ComponentPart(
                dx=0.55, dy=0.55, dz=18.0,
                length=3.9, width=3.9, height=0.6,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.75, dy=0.75, dz=18.6,
                length=3.5, width=3.5, height=7.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.95, dy=0.95, dz=25.6,
                length=3.1, width=3.1, height=0.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=1.1, dy=1.1, dz=26.1,
                length=2.8, width=2.8, height=5.9,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=0.2, dz=0,
                length=1.1, width=1.1, height=16.0,
                material_key="SOLID_PROPELLANT",
                surf_id="SOLID_PROPELLANT_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=3.7, dz=0,
                length=1.1, width=1.1, height=16.0,
                material_key="SOLID_PROPELLANT",
                surf_id="SOLID_PROPELLANT_SURF",
            ),
            ComponentPart(
                dx=3.9, dy=0.2, dz=0,
                length=1.1, width=1.1, height=16.0,
                material_key="SOLID_PROPELLANT",
                surf_id="SOLID_PROPELLANT_SURF",
            ),
            ComponentPart(
                dx=3.9, dy=3.7, dz=0,
                length=1.1, width=1.1, height=16.0,
                material_key="SOLID_PROPELLANT",
                surf_id="SOLID_PROPELLANT_SURF",
            ),
            ComponentPart(
                dx=1.25, dy=1.25, dz=0,
                length=2.5, width=2.5, height=0.45,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "ROCKET_VEHICLE_MEDIUM": SpecializedComponent(
        key="ROCKET_VEHICLE_MEDIUM",
        name="中型火箭",
        category="rocket",
        size_class="medium",
        total_length=3.8,
        total_width=3.8,
        total_height=24.0,
        hrrpua=1800,
        ignition_temp=250,
        parts=[
            ComponentPart(
                dx=0.25, dy=0.25, dz=0,
                length=3.3, width=3.3, height=13.5,
                material_key="SOLID_PROPELLANT",
                surf_id="SOLID_PROPELLANT_SURF",
            ),
            ComponentPart(
                dx=0.45, dy=0.45, dz=13.5,
                length=2.9, width=2.9, height=0.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.65, dy=0.65, dz=14.0,
                length=2.5, width=2.5, height=5.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.9, dy=0.9, dz=19.5,
                length=2.0, width=2.0, height=4.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=0.95, dz=0,
                length=0.9, width=0.9, height=11.5,
                material_key="SOLID_PROPELLANT",
                surf_id="SOLID_PROPELLANT_SURF",
            ),
            ComponentPart(
                dx=2.9, dy=1.95, dz=0,
                length=0.9, width=0.9, height=11.5,
                material_key="SOLID_PROPELLANT",
                surf_id="SOLID_PROPELLANT_SURF",
            ),
            ComponentPart(
                dx=1.05, dy=1.05, dz=0,
                length=1.7, width=1.7, height=0.35,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "ROCKET_VEHICLE_SMALL": SpecializedComponent(
        key="ROCKET_VEHICLE_SMALL",
        name="小型火箭/导弹",
        category="rocket",
        size_class="small",
        total_length=1.8,
        total_width=1.8,
        total_height=12.0,
        hrrpua=1500,
        ignition_temp=250,
        parts=[
            ComponentPart(
                dx=0.18, dy=0.18, dz=0,
                length=1.44, width=1.44, height=6.6,
                material_key="SOLID_PROPELLANT",
                surf_id="SOLID_PROPELLANT_SURF",
            ),
            ComponentPart(
                dx=0.25, dy=0.25, dz=6.6,
                length=1.3, width=1.3, height=3.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.35, dy=0.35, dz=9.6,
                length=1.1, width=1.1, height=2.4,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=0.65, dz=0,
                length=0.4, width=0.4, height=3.2,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=1.4, dy=0.65, dz=0,
                length=0.4, width=0.4, height=3.2,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.5, dy=0.5, dz=0,
                length=0.8, width=0.8, height=0.3,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "AEROSPACE_AVIONICS_RACK": SpecializedComponent(
        key="AEROSPACE_AVIONICS_RACK",
        name="航天测控与航电柜列",
        category="aerospace",
        size_class="medium",
        total_length=7.0,
        total_width=1.2,
        total_height=2.3,
        hrrpua=300,
        ignition_temp=330,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.0, dz=0.0,
                length=7.0, width=0.8, height=2.1,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.2, dy=0.8, dz=0.2,
                length=6.6, width=0.25, height=0.4,
                material_key="CABLE_BUNDLE",
                surf_id="CABLE_BUNDLE_SURF",
            ),
            ComponentPart(
                dx=0.3, dy=0.05, dz=2.1,
                length=6.4, width=1.1, height=0.15,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
        ],
    ),
    "ROCKET_TRANSPORT_CRADLE": SpecializedComponent(
        key="ROCKET_TRANSPORT_CRADLE",
        name="火箭水平转运托架",
        category="aerospace",
        size_class="large",
        total_length=22.0,
        total_width=4.0,
        total_height=2.0,
        hrrpua=220,
        ignition_temp=420,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.4, dz=0.0,
                length=22.0, width=0.35, height=0.45,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=3.25, dz=0.0,
                length=22.0, width=0.35, height=0.45,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=3.0, dy=0.8, dz=0.45,
                length=2.5, width=2.4, height=0.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=10.0, dy=0.8, dz=0.45,
                length=2.5, width=2.4, height=0.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=17.0, dy=0.8, dz=0.45,
                length=2.5, width=2.4, height=0.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "SATELLITE_PAYLOAD": SpecializedComponent(
        key="SATELLITE_PAYLOAD",
        name="卫星有效载荷",
        category="satellite",
        size_class="medium",
        total_length=5.0,
        total_width=8.0,
        total_height=4.5,
        hrrpua=260,
        ignition_temp=420,
        parts=[
            ComponentPart(
                dx=1.2, dy=2.8, dz=0.0,
                length=2.6, width=2.4, height=2.8,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=1.6, dy=3.2, dz=2.8,
                length=1.8, width=1.6, height=1.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=0.0, dz=1.2,
                length=5.0, width=2.5, height=0.12,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=5.5, dz=1.2,
                length=5.0, width=2.5, height=0.12,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=2.0, dy=3.7, dz=3.8,
                length=1.0, width=0.6, height=0.7,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
        ],
    ),
    "PAYLOAD_FAIRING_HALF": SpecializedComponent(
        key="PAYLOAD_FAIRING_HALF",
        name="卫星整流罩半罩",
        category="satellite",
        size_class="large",
        total_length=11.0,
        total_width=4.0,
        total_height=4.0,
        hrrpua=240,
        ignition_temp=420,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.0, dz=0.0,
                length=11.0, width=4.0, height=0.25,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=0.0, dz=0.25,
                length=11.0, width=0.35, height=3.2,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=3.65, dz=0.25,
                length=11.0, width=0.35, height=3.2,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.8, dy=0.35, dz=3.45,
                length=9.4, width=3.3, height=0.35,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=1.7, dz=0.6,
                length=11.0, width=0.6, height=0.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
        ],
    ),
    "LAUNCH_SERVICE_TOWER": SpecializedComponent(
        key="LAUNCH_SERVICE_TOWER",
        name="发射服务塔",
        category="launch_support",
        size_class="large",
        total_length=7.0,
        total_width=7.0,
        total_height=24.0,
        hrrpua=220,
        ignition_temp=450,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.0, dz=0.0,
                length=0.45, width=0.45, height=24.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=6.55, dy=0.0, dz=0.0,
                length=0.45, width=0.45, height=24.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=6.55, dz=0.0,
                length=0.45, width=0.45, height=24.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=6.55, dy=6.55, dz=0.0,
                length=0.45, width=0.45, height=24.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.2, dy=0.2, dz=6.0,
                length=6.6, width=6.6, height=0.35,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.2, dy=0.2, dz=12.0,
                length=6.6, width=6.6, height=0.35,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.2, dy=0.2, dz=18.0,
                length=6.6, width=6.6, height=0.35,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=1.0, dy=6.0, dz=13.0,
                length=5.0, width=0.45, height=0.45,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "MISSION_CONTROL_CONSOLE_BANK": SpecializedComponent(
        key="MISSION_CONTROL_CONSOLE_BANK",
        name="任务控制台阵列",
        category="aerospace_control",
        size_class="medium",
        total_length=8.0,
        total_width=3.0,
        total_height=2.4,
        hrrpua=260,
        ignition_temp=360,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.0, dz=0.0,
                length=8.0, width=1.2, height=0.9,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=1.4, dz=0.0,
                length=8.0, width=0.6, height=2.1,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.2, dy=1.0, dz=1.1,
                length=7.6, width=0.25, height=0.9,
                material_key="GLASS",
                surf_id="GLASS_SURF",
            ),
            ComponentPart(
                dx=1.0, dy=2.0, dz=1.6,
                length=6.0, width=0.3, height=0.7,
                material_key="GLASS",
                surf_id="GLASS_SURF",
            ),
        ],
    ),
    "MACHINING_CENTER_LINE": SpecializedComponent(
        key="MACHINING_CENTER_LINE",
        name="数控加工中心列",
        category="machinery",
        size_class="large",
        total_length=24.0,
        total_width=6.0,
        total_height=4.0,
        hrrpua=280,
        ignition_temp=430,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.0, dz=0.0,
                length=24.0, width=5.4, height=0.55,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=1.0, dy=0.5, dz=0.55,
                length=4.2, width=4.4, height=2.9,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=7.2, dy=0.5, dz=0.55,
                length=4.2, width=4.4, height=2.9,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=13.4, dy=0.5, dz=0.55,
                length=4.2, width=4.4, height=2.9,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=19.6, dy=0.5, dz=0.55,
                length=3.4, width=4.4, height=2.9,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.5, dy=5.4, dz=0.7,
                length=23.0, width=0.35, height=0.45,
                material_key="LUBE_OIL_DRUM",
                surf_id="LUBE_OIL_DRUM_SURF",
            ),
            ComponentPart(
                dx=1.5, dy=0.2, dz=3.45,
                length=21.0, width=0.35, height=0.35,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=2.0, dy=4.9, dz=1.0,
                length=1.2, width=0.5, height=1.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=20.0, dy=4.9, dz=1.0,
                length=1.2, width=0.5, height=1.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "ASSEMBLY_JIG_LINE": SpecializedComponent(
        key="ASSEMBLY_JIG_LINE",
        name="大型总装夹具线",
        category="machinery",
        size_class="large",
        total_length=28.0,
        total_width=7.0,
        total_height=4.2,
        hrrpua=220,
        ignition_temp=420,
        parts=[
            ComponentPart(
                dx=0.0, dy=0.5, dz=0.0,
                length=28.0, width=0.55, height=0.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.0, dy=5.95, dz=0.0,
                length=28.0, width=0.55, height=0.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=3.0, dy=1.1, dz=0.6,
                length=3.0, width=4.8, height=2.1,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=12.5, dy=1.1, dz=0.6,
                length=3.0, width=4.8, height=2.1,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=22.0, dy=1.1, dz=0.6,
                length=3.0, width=4.8, height=2.1,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=0.5, dy=3.2, dz=3.2,
                length=27.0, width=0.6, height=0.5,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=4.0, dy=0.6, dz=0.6,
                length=0.7, width=5.8, height=3.1,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=23.3, dy=0.6, dz=0.6,
                length=0.7, width=5.8, height=3.1,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "COAL_HANDLING_SYSTEM": SpecializedComponent(
        key="COAL_HANDLING_SYSTEM",
        name="输煤系统",
        category="power_plant",
        size_class="large",
        total_length=10.0,
        total_width=8.0,
        total_height=12.0,
        hrrpua=350,
        ignition_temp=400,
        parts=[
            # 1. 原煤仓主体
            ComponentPart(
                dx=0,
                dy=0,
                dz=6.0,
                length=5.0,
                width=5.0,
                height=12.0,
                material_key="COAL_STACK",
                surf_id="COAL_STACK_SURF",
            ),
            # 2. 煤粉仓
            ComponentPart(
                dx=5.0,
                dy=0,
                dz=10.0,
                length=4.0,
                width=4.0,
                height=8.0,
                material_key="COAL_DUST_HOPPER",
                surf_id="COAL_DUST_HOPPER_SURF",
            ),
            # 3. 给煤机皮带
            ComponentPart(
                dx=0,
                dy=5.0,
                dz=8.0,
                length=8.0,
                width=0.8,
                height=0.012,
                material_key="CONVEYOR_BELT",
                surf_id="CONVEYOR_BELT_SURF",
            ),
            # 4. 皮带支撑结构
            ComponentPart(
                dx=0,
                dy=4.9,
                dz=7.9,
                length=8.0,
                width=0.1,
                height=0.1,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "TURBINE_UNIT": SpecializedComponent(
        key="TURBINE_UNIT",
        name="汽轮机组",
        category="power_plant",
        size_class="large",
        total_length=12.0,
        total_width=6.0,
        total_height=4.0,
        hrrpua=900,
        ignition_temp=330,
        parts=[
            # 1. 主油箱
            ComponentPart(
                dx=0,
                dy=0,
                dz=0,
                length=6.0,
                width=2.5,
                height=2.0,
                material_key="LUBE_OIL_TANK",
                surf_id="LUBE_OIL_TANK_SURF",
            ),
            # 2. 液压油箱
            ComponentPart(
                dx=6.0,
                dy=0,
                dz=0,
                length=2.0,
                width=1.2,
                height=1.5,
                material_key="HYDRAULIC_OIL_TANK",
                surf_id="HYDRAULIC_OIL_TANK_SURF",
            ),
            # 3. 密封油箱
            ComponentPart(
                dx=8.0,
                dy=0,
                dz=0,
                length=1.5,
                width=1.0,
                height=1.2,
                material_key="SEAL_OIL_TANK",
                surf_id="SEAL_OIL_TANK_SURF",
            ),
            # 4. 油管路系统
            ComponentPart(
                dx=0,
                dy=2.5,
                dz=1.0,
                length=10.0,
                width=0.2,
                height=0.2,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "TRANSFORMER_STATION": SpecializedComponent(
        key="TRANSFORMER_STATION",
        name="变压器站",
        category="power_plant",
        size_class="medium",
        total_length=15.0,
        total_width=10.0,
        total_height=3.0,
        hrrpua=1000,
        ignition_temp=330,
        parts=[
            # 1. 主变压器
            ComponentPart(
                dx=0,
                dy=0,
                dz=0,
                length=3.0,
                width=2.0,
                height=2.5,
                material_key="OIL_TRANSFORMER",
                surf_id="OIL_TRANSFORMER_SURF",
            ),
            # 2. 开关柜1
            ComponentPart(
                dx=3.0,
                dy=0,
                dz=0,
                length=0.8,
                width=1.2,
                height=2.2,
                material_key="SWITCH_CABINET",
                surf_id="SWITCH_CABINET_SURF",
            ),
            # 3. 开关柜2
            ComponentPart(
                dx=3.8,
                dy=0,
                dz=0,
                length=0.8,
                width=1.2,
                height=2.2,
                material_key="SWITCH_CABINET",
                surf_id="SWITCH_CABINET_SURF",
            ),
            # 4. 油浸断路器
            ComponentPart(
                dx=4.6,
                dy=0,
                dz=0,
                length=1.2,
                width=0.8,
                height=2.2,
                material_key="OIL_CIRCUIT_BREAKER",
                surf_id="OIL_CIRCUIT_BREAKER_SURF",
            ),
            # 5. 电缆桥架
            ComponentPart(
                dx=0,
                dy=2.0,
                dz=1.5,
                length=10.0,
                width=0.8,
                height=0.2,
                material_key="CABLE_BUNDLE",
                surf_id="CABLE_BUNDLE_SURF",
            ),
        ],
    ),
    "BOILER_IGNITION_SYSTEM": SpecializedComponent(
        key="BOILER_IGNITION_SYSTEM",
        name="锅炉点火油系统",
        category="power_plant",
        size_class="medium",
        total_length=5.0,
        total_width=3.0,
        total_height=3.0,
        hrrpua=1200,
        ignition_temp=260,
        parts=[
            # 1. 点火油装置
            ComponentPart(
                dx=0,
                dy=0,
                dz=0,
                length=3.0,
                width=1.5,
                height=1.8,
                material_key="IGNITION_OIL_DEVICE",
                surf_id="IGNITION_OIL_DEVICE_SURF",
            ),
            # 2. 日用油箱
            ComponentPart(
                dx=3.0,
                dy=0,
                dz=0,
                length=1.5,
                width=1.0,
                height=1.2,
                material_key="DAILY_OIL_TANK",
                surf_id="DAILY_OIL_TANK_SURF",
            ),
            # 3. 供油管路
            ComponentPart(
                dx=0,
                dy=1.5,
                dz=0.5,
                length=4.0,
                width=0.15,
                height=0.15,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    # ══════════════════════════════════════════════
    # Electronics (2 OBST)
    # ══════════════════════════════════════════════
    "ELECTRONICS_CONSOLE": SpecializedComponent(
        key="ELECTRONICS_CONSOLE",
        name="电子控制台",
        category="electronics",
        size_class="medium",
        total_length=3.0,
        total_width=1.5,
        total_height=2.0,
        hrrpua=200,
        ignition_temp=350,
        parts=[
            # 1. 主体柜体
            ComponentPart(
                dx=0,
                dy=0,
                dz=0,
                length=3.0,
                width=1.5,
                height=1.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 2. 显示屏
            ComponentPart(
                dx=0.1,
                dy=0.1,
                dz=1.8,
                length=2.8,
                width=1.3,
                height=0.15,
                material_key="GLASS",
                surf_id="GLASS_SURF",
            ),
        ],
    ),
    "CABLE_BUNDLE": SpecializedComponent(
        key="CABLE_BUNDLE",
        name="电缆束",
        category="electronics",
        size_class="medium",
        total_length=4.0,
        total_width=0.5,
        total_height=0.3,
        hrrpua=500,
        ignition_temp=300,
        parts=[
            # 1. 电缆束主体
            ComponentPart(
                dx=0,
                dy=0,
                dz=0,
                length=2.0,
                width=0.3,
                height=0.15,
                material_key="CABLE_BUNDLE",
                surf_id="CABLE_BUNDLE_SURF",
            ),
        ],
    ),
    # ══════════════════════════════════════════════
    # Long, prominent industrial features (4 units)
    # ══════════════════════════════════════════════
    "LONG_RAIL_TANK": SpecializedComponent(
        key="LONG_RAIL_TANK",
        name="长条形卧式储罐/管道列阵",
        category="industrial_long",
        size_class="large",
        total_length=14.0,   # very elongated
        total_width=2.0,
        total_height=1.8,
        hrrpua=600,
        ignition_temp=300,
        parts=[
            # 主罐身（长条卧式大圆筒造型）
            ComponentPart(
                dx=0,
                dy=0.2,
                dz=0,
                length=14.0,
                width=1.6,
                height=1.8,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 顶部走道/检修平台
            ComponentPart(
                dx=0.5,
                dy=0.0,
                dz=1.8,
                length=13.0,
                width=2.0,
                height=0.15,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 两端封头（半球凸出）
            ComponentPart(
                dx=-0.7,
                dy=0.6,
                dz=0,
                length=0.7,
                width=0.8,
                height=1.8,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            ComponentPart(
                dx=14.0,
                dy=0.6,
                dz=0,
                length=0.7,
                width=0.8,
                height=1.8,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
        ],
    ),
    "INDUSTRIAL_FURNACE_LONG": SpecializedComponent(
        key="INDUSTRIAL_FURNACE_LONG",
        name="长条形工业炉/热处理炉",
        category="industrial_long",
        size_class="large",
        total_length=10.0,    # very elongated
        total_width=2.5,
        total_height=2.8,
        hrrpua=400,
        ignition_temp=420,
        parts=[
            # 外壳主体（长筒形）
            ComponentPart(
                dx=0,
                dy=0.5,
                dz=0,
                length=10.0,
                width=1.5,
                height=2.0,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 顶部拱形炉盖（半圆顶）
            ComponentPart(
                dx=0.3,
                dy=0.3,
                dz=2.0,
                length=9.4,
                width=1.9,
                height=0.8,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 进料端密封门（凸出）
            ComponentPart(
                dx=-0.4,
                dy=0.5,
                dz=0.4,
                length=0.4,
                width=1.5,
                height=1.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 出料端密封门（凸出）
            ComponentPart(
                dx=10.0,
                dy=0.5,
                dz=0.4,
                length=0.4,
                width=1.5,
                height=1.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 底部支撑底座
            ComponentPart(
                dx=0,
                dy=0,
                dz=0,
                length=10.0,
                width=2.5,
                height=0.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "CIRCUIT_BOARD_RACK_LARGE": SpecializedComponent(
        key="CIRCUIT_BOARD_RACK_LARGE",
        name="长条大型电气控制柜列阵",
        category="industrial_long",
        size_class="large",
        total_length=8.0,     # elongated
        total_width=1.2,      # narrows
        total_height=2.5,
        hrrpua=350,
        ignition_temp=380,
        parts=[
            # 主体机柜列阵
            ComponentPart(
                dx=0,
                dy=0,
                dz=0,
                length=8.0,
                width=0.8,
                height=2.2,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 顶部通风罩（网格风帽）
            ComponentPart(
                dx=0.2,
                dy=0.0,
                dz=2.2,
                length=7.6,
                width=1.2,
                height=0.15,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 底部电缆通道
            ComponentPart(
                dx=0,
                dy=0.8,
                dz=0,
                length=8.0,
                width=0.4,
                height=0.6,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
    "INDUSTRIAL_PIPELINE": SpecializedComponent(
        key="INDUSTRIAL_PIPELINE",
        name="横穿式工业管道系统",
        category="industrial_long",
        size_class="large",
        total_length=12.0,    # spans most of a room
        total_width=0.4,
        total_height=2.0,
        hrrpua=200,
        ignition_temp=400,
        parts=[
            # 主管道（横贯长条）
            ComponentPart(
                dx=0,
                dy=0.0,
                dz=1.4,
                length=12.0,
                width=0.4,
                height=0.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 支管 #1
            ComponentPart(
                dx=2.0,
                dy=0.1,
                dz=0,
                length=0.3,
                width=0.3,
                height=1.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 支管 #2
            ComponentPart(
                dx=5.5,
                dy=0.1,
                dz=0,
                length=0.3,
                width=0.3,
                height=1.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 支管 #3
            ComponentPart(
                dx=9.0,
                dy=0.1,
                dz=0,
                length=0.3,
                width=0.3,
                height=1.4,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            # 法兰端帽
            ComponentPart(
                dx=-0.3,
                dy=0.05,
                dz=1.4,
                length=0.3,
                width=0.3,
                height=0.5,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
            ComponentPart(
                dx=12.0,
                dy=0.05,
                dz=1.4,
                length=0.3,
                width=0.3,
                height=0.5,
                material_key="STEEL",
                surf_id="STEEL_SURF",
            ),
        ],
    ),
}


# ============================================================
# 特异性组件主材质统一 (single-material simplification)
# ============================================================
# 为方便后续计算，所有特异性组件统一为一种主要金属材质（按类别区分）：
#   航空器 / 火箭 / 卫星 -> 铝 (ALUMINUM)
#   车辆 / 工业 / 电力等其余 -> 钢 (STEEL)
# 统一后组件视为惰性金属目标（不再热解燃烧），仅用于测量入射辐射热流。
# 这里在定义后统一回填每个 part 的 material_key / surf_id 并清除 ignition_temp，
# 避免逐一改动庞大的字面量，同时便于核对。
_COMPONENT_METAL_BY_CATEGORY = {
    "hangar": "ALUMINUM",
    "rocket": "ALUMINUM",
    "satellite": "ALUMINUM",
}
_DEFAULT_COMPONENT_METAL = "STEEL"


def _unify_component_materials() -> None:
    for comp in SPECIALIZED_COMPONENTS.values():
        metal = _COMPONENT_METAL_BY_CATEGORY.get(
            comp.category, _DEFAULT_COMPONENT_METAL
        )
        for part in comp.parts:
            part.material_key = metal
            part.surf_id = f"{metal}_SURF"
            part.ignition_temp = 0.0


_unify_component_materials()


# ── 可燃物模板库 ──────────────────────────────────────────────


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
    hrrpua: float = 300.0  # kW/m²
    ignition_temp: float = 350  # °C
    color: str = "BROWN"
    matl: dict = field(default_factory=dict)
    compartment_id: str = ""  # fire compartment this combustible belongs to
    component_key: str = (
        ""  # key into SPECIALIZED_COMPONENTS if this is a component part
    )
    material_key: str = ""  # material for component parts (e.g., ALUMINUM, STEEL)
    rotation: int = 0  # 0 or 90 degrees

    def __post_init__(self):
        if not self.id:
            self.id = f"CB_{uuid.uuid4().hex[:6]}"

    @classmethod
    def from_preset(cls, key: str, x=0, y=0, z=0) -> "Combustible":
        p = COMBUSTIBLE_LIBRARY.get(key)
        if not p:
            raise ValueError(f"Unknown combustible preset: {key}")
        return cls(
            preset_key=key,
            name=p["name"],
            x=x,
            y=y,
            z=z,
            length=p["length"],
            width=p["width"],
            height=p["height"],
            hrrpua=p["hrrpua"],
            ignition_temp=p["ignition_temp"],
            color=p["color"],
            matl=dict(p["matl"]),
        )

    @property
    def bounds(self) -> Tuple[float, float, float, float, float, float]:
        return (
            self.x,
            self.x + self.length,
            self.y,
            self.y + self.width,
            self.z,
            self.z + self.height,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Combustible":
        rotation = d.get("rotation", 0)
        if rotation != 90:
            rotation = 0

        cb = cls(
            id=d.get("id", ""),
            preset_key=d.get("preset_key", d.get("key", "WOOD_TABLE")),
            name=d.get("name", ""),
            x=d.get("x", 0.0),
            y=d.get("y", 0.0),
            z=d.get("z", 0.0),
            length=d.get("length", 1.2),
            width=d.get("width", 0.8),
            height=d.get("height", 0.75),
            hrrpua=d.get("hrrpua", 300.0),
            ignition_temp=d.get("ignition_temp", 350),
            color=d.get("color", "BROWN"),
            matl=d.get("matl", {}),
            compartment_id=d.get("compartment_id", ""),
            component_key=d.get("component_key", ""),
            material_key=d.get("material_key", ""),
            rotation=rotation,
        )

        if rotation == 90:
            cb.length, cb.width = cb.width, cb.length

        return cb


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
    def generate(
        self,
        preset_key: str,
        count: int,
        method: DistributionMethod,
        room_length: float,
        room_width: float,
        wall_thickness: float = 0.5,
        margin: float = 0.3,
        seed: Optional[int] = None,
        **kwargs,
    ) -> List[Combustible]:
        if seed is not None:
            random.seed(seed)

        p = COMBUSTIBLE_LIBRARY.get(preset_key)
        if not p:
            raise ValueError(f"Unknown combustible preset: {preset_key}")
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
            DistributionMethod.RANDOM: self._random,
            DistributionMethod.ALONG_WALLS: self._along_walls,
            DistributionMethod.CLUSTERED: self._clustered,
            DistributionMethod.DIAGONAL: self._diagonal,
            DistributionMethod.RING: self._ring,
        }[method](
            count,
            x_min,
            x_max,
            y_min,
            y_max,
            obj_l,
            obj_w,
            # 沿墙分布需要内部边界
            interior_x_min=interior_x_min,
            interior_x_max=interior_x_max,
            interior_y_min=interior_y_min,
            interior_y_max=interior_y_max,
            **kwargs,
        )

        new_items = []
        for x, y in positions[:count]:
            # 最终裁剪，确保不超出内部空间
            x = max(interior_x_min, min(x, interior_x_max - obj_l))
            y = max(interior_y_min, min(y, interior_y_max - obj_w))
            cb = Combustible.from_preset(preset_key, x=round(x, 2), y=round(y, 2), z=0)
            self.items.append(cb)
            new_items.append(cb)
        return new_items

    # ── 分布算法 ─────────────────────────────────────────
    @staticmethod
    def _grid(count, x_min, x_max, y_min, y_max, ol, ow, **kw):
        cols = max(
            1, int(math.ceil(math.sqrt(count * (x_max - x_min) / (y_max - y_min))))
        )
        rows = max(1, int(math.ceil(count / cols)))
        dx = (x_max - x_min) / max(cols, 1)
        dy = (y_max - y_min) / max(rows, 1)
        pts = []
        for r in range(rows):
            for c in range(cols):
                if len(pts) >= count:
                    break
                pts.append(
                    (x_min + c * dx + dx / 2 - ol / 2, y_min + r * dy + dy / 2 - ow / 2)
                )
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
            ok = all(abs(x - px) > ol * 0.8 or abs(y - py) > ow * 0.8 for px, py in pts)
            if ok:
                pts.append((x, y))
        return pts

    @staticmethod
    def _along_walls(
        count,
        x_min,
        x_max,
        y_min,
        y_max,
        ol,
        ow,
        interior_x_min=0,
        interior_x_max=0,
        interior_y_min=0,
        interior_y_max=0,
        **kw,
    ):
        """沿墙分布：物体紧贴内墙面"""
        pts = []
        gap = 0.1  # 离墙面间隙

        # 四面墙的可放置段
        segments = []

        # 南墙 (y_min侧)：物体y紧贴南墙内面
        wall_y = interior_y_min + gap
        x = interior_x_min + gap
        while x + ol <= interior_x_max - gap:
            segments.append((x, wall_y, "south"))
            x += ol + 0.3

        # 北墙 (y_max侧)
        wall_y = interior_y_max - gap - ow
        x = interior_x_min + gap
        while x + ol <= interior_x_max - gap:
            segments.append((x, wall_y, "north"))
            x += ol + 0.3

        # 西墙 (x_min侧)
        wall_x = interior_x_min + gap
        y = interior_y_min + gap + ow  # 跳过角落
        while y + ow <= interior_y_max - gap - ow:
            segments.append((wall_x, y, "west"))
            y += ow + 0.3

        # 东墙 (x_max侧)
        wall_x = interior_x_max - gap - ol
        y = interior_y_min + gap + ow
        while y + ow <= interior_y_max - gap - ow:
            segments.append((wall_x, y, "east"))
            y += ow + 0.3

        # 均匀选取
        if len(segments) > count:
            step = len(segments) / count
            selected = [segments[int(i * step)] for i in range(count)]
        else:
            selected = segments

        return [(x, y) for x, y, _ in selected]

    @staticmethod
    def _clustered(
        count, x_min, x_max, y_min, y_max, ol, ow, clusters=3, spread=1.5, **kw
    ):
        pts = []
        centers = [
            (random.uniform(x_min + 1, x_max - 1), random.uniform(y_min + 1, y_max - 1))
            for _ in range(min(clusters, count))
        ]
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
            pts.append((x_min + t * (x_max - x_min), y_min + t * (y_max - y_min)))
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
            pts.append((cx + rx * math.cos(a) - ol / 2, cy + ry * math.sin(a) - ow / 2))
        return pts

    # ── 碰撞检测 ─────────────────────────────────────────
    def check_overlaps(self) -> List[Tuple[str, str]]:
        """返回所有重叠的可燃物id对"""
        overlaps = []
        for i, a in enumerate(self.items):
            for b in self.items[i + 1 :]:
                if (
                    a.x < b.x + b.length
                    and a.x + a.length > b.x
                    and a.y < b.y + b.width
                    and a.y + a.width > b.y
                ):
                    overlaps.append((a.id, b.id))
        return overlaps
