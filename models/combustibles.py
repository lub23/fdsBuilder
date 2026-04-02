#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@File  : combustibles.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 2.0
@Desc  : Combustible model class for FDS generation
'''

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
    # Rocket vehicles (10 OBST)
    # ══════════════════════════════════════════════
    "ROCKET_VEHICLE_LARGE": SpecializedComponent(
        key="ROCKET_VEHICLE_LARGE",
        name="大型运载火箭",
        category="rocket",
        size_class="large",
        total_length=6.0,
        total_width=6.0,
        total_height=18.0,
        hrrpua=2000,
        ignition_temp=250,
        parts=[
            # 1. 一级箭体（最宽）
            ComponentPart(
                dx=0.5,
                dy=0.5,
                dz=0,
                length=5.0,
                width=5.0,
                height=8.0,
                material_key="SOLID_PROPELLANT",
                surf_id="PROPELLANT_SURF",
            ),
            # 2. 级间段 #1
            ComponentPart(
                dx=0.8,
                dy=0.8,
                dz=8.0,
                length=4.4,
                width=4.4,
                height=0.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 3. 二级箭体
            ComponentPart(
                dx=1.0,
                dy=1.0,
                dz=8.5,
                length=4.0,
                width=4.0,
                height=5.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 4. 级间段 #2
            ComponentPart(
                dx=1.2,
                dy=1.2,
                dz=13.5,
                length=3.6,
                width=3.6,
                height=0.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 5. 整流罩/载荷
            ComponentPart(
                dx=1.5,
                dy=1.5,
                dz=14.0,
                length=3.0,
                width=3.0,
                height=4.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 6. 助推器 #1 (左前)
            ComponentPart(
                dx=-0.3,
                dy=0,
                dz=0,
                length=1.5,
                width=1.5,
                height=7.0,
                material_key="SOLID_PROPELLANT",
                surf_id="PROPELLANT_SURF",
            ),
            # 7. 助推器 #2 (右前)
            ComponentPart(
                dx=-0.3,
                dy=4.5,
                dz=0,
                length=1.5,
                width=1.5,
                height=7.0,
                material_key="SOLID_PROPELLANT",
                surf_id="PROPELLANT_SURF",
            ),
            # 8. 助推器 #3 (左后)
            ComponentPart(
                dx=4.8,
                dy=0,
                dz=0,
                length=1.5,
                width=1.5,
                height=7.0,
                material_key="SOLID_PROPELLANT",
                surf_id="PROPELLANT_SURF",
            ),
            # 9. 助推器 #4 (右后)
            ComponentPart(
                dx=4.8,
                dy=4.5,
                dz=0,
                length=1.5,
                width=1.5,
                height=7.0,
                material_key="SOLID_PROPELLANT",
                surf_id="PROPELLANT_SURF",
            ),
            # 10. 发动机喷管区
            ComponentPart(
                dx=1.5,
                dy=1.5,
                dz=-0.5,
                length=3.0,
                width=3.0,
                height=0.5,
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
        total_length=4.0,
        total_width=4.0,
        total_height=12.0,
        hrrpua=1800,
        ignition_temp=250,
        parts=[
            # 1. 一级箭体
            ComponentPart(
                dx=0.3,
                dy=0.3,
                dz=0,
                length=3.4,
                width=3.4,
                height=5.5,
                material_key="SOLID_PROPELLANT",
                surf_id="PROPELLANT_SURF",
            ),
            # 2. 级间段
            ComponentPart(
                dx=0.5,
                dy=0.5,
                dz=5.5,
                length=3.0,
                width=3.0,
                height=0.4,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 3. 二级箭体
            ComponentPart(
                dx=0.7,
                dy=0.7,
                dz=5.9,
                length=2.6,
                width=2.6,
                height=3.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 4. 整流罩
            ComponentPart(
                dx=1.0,
                dy=1.0,
                dz=9.4,
                length=2.0,
                width=2.0,
                height=2.6,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 5. 助推器 #1 (左)
            ComponentPart(
                dx=-0.2,
                dy=1.2,
                dz=0,
                length=1.0,
                width=1.0,
                height=4.5,
                material_key="SOLID_PROPELLANT",
                surf_id="PROPELLANT_SURF",
            ),
            # 6. 助推器 #2 (右)
            ComponentPart(
                dx=3.2,
                dy=1.2,
                dz=0,
                length=1.0,
                width=1.0,
                height=4.5,
                material_key="SOLID_PROPELLANT",
                surf_id="PROPELLANT_SURF",
            ),
            # 7. 发动机喷管
            ComponentPart(
                dx=1.0,
                dy=1.0,
                dz=-0.4,
                length=2.0,
                width=2.0,
                height=0.4,
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
        total_length=1.5,
        total_width=1.5,
        total_height=6.0,
        hrrpua=1500,
        ignition_temp=250,
        parts=[
            # 1. 弹体下段（推进段）
            ComponentPart(
                dx=0.1,
                dy=0.1,
                dz=0,
                length=1.3,
                width=1.3,
                height=2.5,
                material_key="SOLID_PROPELLANT",
                surf_id="PROPELLANT_SURF",
            ),
            # 2. 弹体中段（战斗部/载荷）
            ComponentPart(
                dx=0.15,
                dy=0.15,
                dz=2.5,
                length=1.2,
                width=1.2,
                height=2.0,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 3. 弹头/整流罩
            ComponentPart(
                dx=0.25,
                dy=0.25,
                dz=4.5,
                length=1.0,
                width=1.0,
                height=1.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 4. 尾翼 #1
            ComponentPart(
                dx=-0.1,
                dy=0.6,
                dz=0,
                length=0.3,
                width=0.3,
                height=1.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 5. 尾翼 #2
            ComponentPart(
                dx=1.3,
                dy=0.6,
                dz=0,
                length=0.3,
                width=0.3,
                height=1.5,
                material_key="ALUMINUM",
                surf_id="ALUMINUM_SURF",
            ),
            # 6. 喷管
            ComponentPart(
                dx=0.4,
                dy=0.4,
                dz=-0.3,
                length=0.7,
                width=0.7,
                height=0.3,
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
}


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
    hrrpua: float = 300.0       # kW/m²
    ignition_temp: float = 350  # °C
    color: str = "BROWN"
    matl: dict = field(default_factory=dict)
    compartment_id: str = ""  # fire compartment this combustible belongs to
    component_key: str = (
        ""  # key into SPECIALIZED_COMPONENTS if this is a component part
    )
    material_key: str = ""  # material for component parts (e.g., ALUMINUM, STEEL)

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