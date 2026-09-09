#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File  : materials.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.1
@Desc  : Defining materials and configurations in applications

Version 1.1 — fire-spread tuning (2026-06-17):
  + Combustible dimensions are scaled up so each package spans >= 1.5
    cells at the "small" mesh size (0.5 m).  This keeps ignition stable
    and gives combustion enough material to drive radiative spread
    between packages.  Heights in particular were raised to >= 0.6 m
    so they don't fall through THICKEN=.TRUE. arbitrarily-thin sliver
    treatment at the largest mesh size (2.0 m).
  + Each combustible entry now carries a comment with the recommended
    *minimum* mesh size (in m) at which the item still occupies
    >= 1 cell per dimension.  This drives the grid size choice in
    SimulationControlPanel and keeps RFC-style fire-spread assumptions
    intact.
"""

# ============================================================
# 材料库
# ============================================================
MATERIAL_LIBRARY = {
    "CONCRETE": {
        "DENSITY": 2200,
        "CONDUCTIVITY": 1.4,
        "SPECIFIC_HEAT": 0.84,
        "THICKNESS": 0.25,
        "DESCRIPTION": "混凝土",
        "COLOR": "#808080",
    },
    "CEMENT": {
        "DENSITY": 2280,
        "CONDUCTIVITY": 1.8,
        "SPECIFIC_HEAT": 1.04,
        "DESCRIPTION": "水泥",
        "COLOR": "#9ca3af",
    },
    "STEEL": {
        "DENSITY": 7850,
        "CONDUCTIVITY": 45.8,
        "SPECIFIC_HEAT": 0.46,
        "EMISSIVITY": 0.95,
        "ABSORPTION": 50000,
        "THICKNESS": 0.01,
        "DESCRIPTION": "钢材",
        "COLOR": "#4a5568",
    },
    "INSULATION": {
        "DENSITY": 80,
        "CONDUCTIVITY": 0.04,
        "SPECIFIC_HEAT": 0.85,
        "EMISSIVITY": 0.9,
        "ABSORPTION": 50000,
        "THICKNESS": 0.1,
        "DESCRIPTION": "岩棉隔热材料",
        "COLOR": "#fbbf24",
    },
    "WOOD": {
        "DENSITY": 640,
        "CONDUCTIVITY": 0.14,
        "SPECIFIC_HEAT": 2.85,
        "EMISSIVITY": 0.9,
        "HEAT_OF_COMBUSTION": 12800,
        "HRR": 300,
        "IGNITION_TEMPERATURE": 330,
        "BURN_TIME": 546,
        "THICKNESS": 0.02,
        "DESCRIPTION": "黄木",
        "COLOR": "#92400e",
    },
    "GLASS": {
        "DENSITY": 2500,
        "CONDUCTIVITY": 1.0,
        "SPECIFIC_HEAT": 0.75,
        "EMISSIVITY": 0.9,
        "ABSORPTION": 50000,
        "THICKNESS": 0.006,
        "DESCRIPTION": "玻璃",
        "COLOR": "#38bdf8",
    },
    "FIRE_PROTECTION_COATING": {
        "DENSITY": 1200,
        "CONDUCTIVITY": 0.2,
        "SPECIFIC_HEAT": 1.0,
        "EMISSIVITY": 0.95,
        "ABSORPTION": 50000,
        "DESCRIPTION": "防火涂层",
        "COLOR": "#e5e7eb",
    },
    "ALUMINUM": {
        "DENSITY": 2700,
        "CONDUCTIVITY": 167,
        "SPECIFIC_HEAT": 0.84,
        "EMISSIVITY": 0.84,
        "ABSORPTION": 50000,
        "THICKNESS": 0.003,
        "DESCRIPTION": "铝合金",
        "COLOR": "#c0c0c0",
    },
    "PVC_CABLE_INSULATION": {
        "DENSITY": 1380,
        "CONDUCTIVITY": 0.192,
        "SPECIFIC_HEAT": 1.289,
        "EMISSIVITY": 0.9,
        "ABSORPTION": 50000,
        "HEAT_OF_COMBUSTION": 20900,
        "HRR": 250,
        "IGNITION_TEMPERATURE": 325,
        "THICKNESS": 0.005,
        "BURN_TIME": 577,
        "DESCRIPTION": "PVC电缆绝缘",
        "COLOR": "#a78bfa",
    },
    "EPDM": {
        "DENSITY": 1200,
        "CONDUCTIVITY": 0.133,
        "SPECIFIC_HEAT": 1.403,
        "EMISSIVITY": 0.9,
        "ABSORPTION": 50000,
        "HEAT_OF_COMBUSTION": 34000,
        "HRR": 600,
        "IGNITION_TEMPERATURE": 213,
        "THICKNESS": 0.005,
        "BURN_TIME": 340,
        "DESCRIPTION": "三元乙丙橡胶EPDM",
        "COLOR": "#60a5fa",
    },
    "PU_FOAM": {
        "DENSITY": 31.7,
        "CONDUCTIVITY": 0.038,
        "SPECIFIC_HEAT": 1.5,
        "EMISSIVITY": 0.9,
        "ABSORPTION": 50000,
        "HEAT_OF_COMBUSTION": 25420,
        "HRR": 1000,
        "IGNITION_TEMPERATURE": 252,
        "THICKNESS": 0.05,
        "BURN_TIME": 40,
        "DESCRIPTION": "聚氨酯泡沫保温材料",
        "COLOR": "#f472b6",
    },
    "ABS_PLASTIC": {
        "DENSITY": 1060,
        "CONDUCTIVITY": 0.218,
        "SPECIFIC_HEAT": 1.96,
        "EMISSIVITY": 0.9,
        "ABSORPTION": 50000,
        "HEAT_OF_COMBUSTION": 36770,
        "HRR": 1500,
        "IGNITION_TEMPERATURE": 363,
        "THICKNESS": 0.005,
        "BURN_TIME": 130,
        "DESCRIPTION": "电子设备塑料ABS",
        "COLOR": "#94a3b8",
    },
    "TEXTILE": {
        "DENSITY": 555.8,
        "CONDUCTIVITY": 0.023,
        "SPECIFIC_HEAT": 1.314,
        "HEAT_OF_COMBUSTION": 13250,
        "HRR": 200,
        "IGNITION_TEMPERATURE": 292,
        "THICKNESS": 0.003,
        "BURN_TIME": 111,
        "DESCRIPTION": "纺织品",
        "COLOR": "#8b5cf6",
    },
    "PP_PLASTIC": {
        "DENSITY": 886,
        "CONDUCTIVITY": 0.137,
        "SPECIFIC_HEAT": 1.764,
        "HEAT_OF_COMBUSTION": 28000,
        "HRR": 2500,
        "IGNITION_TEMPERATURE": 408,
        "THICKNESS": 0.005,
        "BURN_TIME": 50,
        "DESCRIPTION": "黑色塑料PP",
        "COLOR": "#334155",
    },
    "CORRUGATED_CARDBOARD": {
        "DENSITY": 320,
        "CONDUCTIVITY": 0.06,
        "SPECIFIC_HEAT": 1.4,
        "HEAT_OF_COMBUSTION": 14030,
        "HRR": 300,
        "IGNITION_TEMPERATURE": 251,
        "THICKNESS": 0.086,
        "BURN_TIME": 1287,
        "DESCRIPTION": "瓦楞纸板",
        "COLOR": "#d6d3d1",
    },
    "PAPER": {
        "DENSITY": 930,
        "CONDUCTIVITY": 0.18,
        "SPECIFIC_HEAT": 1.34,
        "HEAT_OF_COMBUSTION": 16000,
        "HRR": 200,
        "IGNITION_TEMPERATURE": 250,
        "THICKNESS": 0.028,
        "BURN_TIME": 2083,
        "DESCRIPTION": "纸张",
        "COLOR": "#f8fafc",
    },
    "INDUSTRIAL_OIL": {
        "DENSITY": 900,
        "CONDUCTIVITY": 0.13,
        "SPECIFIC_HEAT": 1.8,
        "EMISSIVITY": 0.95,
        "HEAT_OF_COMBUSTION": 43000,
        "HRR": 800,
        "IGNITION_TEMPERATURE": 300,
        "THICKNESS": 0.05,
        "BURN_TIME": 2419,
        "DESCRIPTION": "工业油品",
        "COLOR": "#b45309",
    },
    "JET_FUEL": {
        "DENSITY": 820,
        "CONDUCTIVITY": 0.13,
        "SPECIFIC_HEAT": 2.10,
        "HEAT_OF_COMBUSTION": 43000,
        "HRR": 1700,
        "IGNITION_TEMPERATURE": 210,
        "BURN_TIME": 1038,
        "THICKNESS": 0.01,
        "DESCRIPTION": "航天油品Kerosene",
        "COLOR": "#b45309",
    },
    "IPA": {
        "DENSITY": 785,
        "CONDUCTIVITY": 0.135,
        "SPECIFIC_HEAT": 2.53,
        "EMISSIVITY": 0.95,
        "HEAT_OF_COMBUSTION": 30150,
        "HRR": 900,
        "IGNITION_TEMPERATURE": 399,
        "THICKNESS": 0.01,
        "BURN_TIME": 263,
        "DESCRIPTION": "异丙醇清洗剂IPA",
        "COLOR": "#22d3ee",
    },
    "EPOXY_RESIN": {
        "DENSITY": 1410,
        "CONDUCTIVITY": 0.2,
        "SPECIFIC_HEAT": 1.2,
        "EMISSIVITY": 0.95,
        "HEAT_OF_COMBUSTION": 16400,
        "HRR": 1015,
        "IGNITION_TEMPERATURE": 350,
        "THICKNESS": 0.02,
        "BURN_TIME": 600,
        "DESCRIPTION": "环氧树脂",
        "COLOR": "#fbbf24",
    },
    "SOLID_PROPELLANT": {
        "DENSITY": 1700,
        "CONDUCTIVITY": 0.50,
        "SPECIFIC_HEAT": 1.20,
        "THICKNESS": 0.05,
        "DESCRIPTION": "固体推进剂",
        "COLOR": "#dc2626",
    },
    "GASOLINE": {
        "DENSITY": 750,
        "CONDUCTIVITY": 0.12,
        "SPECIFIC_HEAT": 2.22,
        "THICKNESS": 0.01,
        "DESCRIPTION": "汽油",
        "COLOR": "#f59e0b",
    },
    "ELECTROLYTE": {
        "DENSITY": 1200,
        "CONDUCTIVITY": 0.60,
        "SPECIFIC_HEAT": 1.50,
        "THICKNESS": 0.02,
        "DESCRIPTION": "电解质",
        "COLOR": "#06b6d4",
    },
}


# ============================================================
# 可燃物核心集 (Core combustible set)
# ============================================================
# Version 2.0 — variety reduction (2026-06-17):
#   The library was collapsed to a small CORE set so generated scenes carry
#   only a handful of distinct combustible types.  Every legacy key is folded
#   into one of the five core keys via ``COMBUSTIBLE_REMAP`` (used by
#   ``scripts/refine_combustibles.py`` to rewrite facility JSONs).
#
#   ``burnable`` distinguishes pyrolysing fuels (thermocouple probe on top,
#   measuring surface temperature vs. ignition) from inert metal targets
#   (radiative-heat-flux probe).  Non-burnable items get no pyrolysis MATL.
#
#   Linear dimensions are kept >= 1.2 m (height >= 1.0 m) so every package
#   spans multiple cells at the coarse industrial mesh sizes and never gets
#   snapped away by THICKEN handling.
COMBUSTIBLE_LIBRARY = {
    "_meta": {
        "version": 3,
        "min_grid_default": 0.5,
    },
    # 1. 纤维质堆料：木制品 / 纸张 / 织物 / 木质家具
    "WOODEN_PALLET": {
        "name": "纤维质堆料",
        "length": 3.0,
        "width": 2.0,
        "height": 1.5,
        "hrrpua": 280,
        "ignition_temp": 350,
        "color": "BROWN",
        "burnable": True,
        "matl": {
            "DENSITY": 500,
            "CONDUCTIVITY": 0.14,
            "SPECIFIC_HEAT": 2.85,
            "HEAT_OF_COMBUSTION": 18000,
            "REFERENCE_TEMPERATURE": 350,
        },
    },
    # 2. 高分子材料：塑料 / 橡胶 / 电缆 / 电气设备 / 复合材料
    "CABLE_BUNDLE": {
        "name": "高分子线缆装置",
        "length": 2.0,
        "width": 1.5,
        "height": 1.5,
        "hrrpua": 600,
        "ignition_temp": 360,
        "color": "BLACK",
        "burnable": True,
        "matl": {
            "DENSITY": 1200,
            "CONDUCTIVITY": 0.20,
            "SPECIFIC_HEAT": 1.50,
            "HEAT_OF_COMBUSTION": 30000,
            "REFERENCE_TEMPERATURE": 360,
        },
    },
    # 3. 易燃液体桶罐：润滑油 / 溶剂 / 化学品 / 液压油 / 变压器油 / 煤油
    "LUBE_OIL_DRUM": {
        "name": "易燃液体桶罐",
        "length": 2.0,
        "width": 2.0,
        "height": 2.0,
        "hrrpua": 1000,
        "ignition_temp": 300,
        "color": "GREEN",
        "burnable": True,
        "matl": {
            "DENSITY": 850,
            "CONDUCTIVITY": 0.14,
            "SPECIFIC_HEAT": 2.10,
            "HEAT_OF_COMBUSTION": 42000,
            "REFERENCE_TEMPERATURE": 300,
        },
    },
    # 4. 炭素固体：炭素/煤 / 预焙阳极 / 阴极碳块 / 金属粉尘
    "CARBON_MATERIAL_STACK": {
        "name": "炭素/煤炭材料堆",
        "length": 2.0,
        "width": 1.5,
        "height": 1.0,
        "hrrpua": 250,
        "ignition_temp": 500,
        "color": "GRAY",
        "burnable": True,
        "matl": {
            "DENSITY": 1600,
            "CONDUCTIVITY": 1.00,
            "SPECIFIC_HEAT": 0.90,
            "HEAT_OF_COMBUSTION": 30000,
            "REFERENCE_TEMPERATURE": 500,
        },
    },
    # 5. 金属制品/零件：辐射热流测量对象
    "METAL_PARTS": {
        "name": "金属制品/零件",
        "length": 1.5,
        "width": 1.0,
        "height": 1.0,
        "hrrpua": 0,
        "ignition_temp": 0,
        "color": "SILVER",
        "burnable": False,
        "matl": {
            "DENSITY": 7850,
            "CONDUCTIVITY": 45.8,
            "SPECIFIC_HEAT": 0.46,
        },
    },
}


# ============================================================
# 可燃物归并表 (legacy key -> core key)
# ============================================================
# Consumed by ``scripts/refine_combustibles.py`` to rewrite facility JSONs.
# Core keys map to themselves; every other historical key folds into a core
# key by physical/burning character.
COMBUSTIBLE_REMAP = {
    # core -> self
    "WOODEN_PALLET": "WOODEN_PALLET",
    "CABLE_BUNDLE": "CABLE_BUNDLE",
    "LUBE_OIL_DRUM": "LUBE_OIL_DRUM",
    "CARBON_MATERIAL_STACK": "CARBON_MATERIAL_STACK",
    "METAL_PARTS": "METAL_PARTS",
    # 纤维质 -> WOODEN_PALLET
    "PAPER_STACK": "WOODEN_PALLET",
    "TEXTILE_ROLL": "WOODEN_PALLET",
    "WOODEN_FURNITURE": "WOODEN_PALLET",
    # 高分子/复合 -> CABLE_BUNDLE
    "PLASTIC_PACKAGING": "CABLE_BUNDLE",
    "RUBBER_MATERIAL": "CABLE_BUNDLE",
    "ELECTRICAL_EQUIPMENT": "CABLE_BUNDLE",
    "AEROSPACE_COMPOSITE_PART": "CABLE_BUNDLE",
    # 易燃液体 -> LUBE_OIL_DRUM
    "ORGANIC_SOLVENT_DRUM": "LUBE_OIL_DRUM",
    "HYDRAULIC_TANK": "LUBE_OIL_DRUM",
    "OIL_TRANSFORMER": "LUBE_OIL_DRUM",
    "CHEMICAL_DRUM": "LUBE_OIL_DRUM",
    "JET_FUEL_RESIDUE": "LUBE_OIL_DRUM",
    "GLYCOL_DEICING_FLUID": "LUBE_OIL_DRUM",
    # 炭素 -> CARBON_MATERIAL_STACK
    "PREBAKED_ANODE_BLOCK": "CARBON_MATERIAL_STACK",
    "CATHODE_CARBON_BLOCK": "CARBON_MATERIAL_STACK",
    "METAL_DUST_COLLECTOR": "CARBON_MATERIAL_STACK",
    "COAL_STACK": "CARBON_MATERIAL_STACK",
}

MATERIAL_DISPLAY_NAMES = {
    "ABS": "电子设备塑料ABS",
    "ABS_PLASTIC": "电子设备塑料ABS",
    "Aluminum alloy": "铝合金",
    "CALCIUM SILICATE": "硅酸钙",
    "CERAMIC FIBER": "陶瓷纤维",
    "CONCRETE": "混凝土",
    "EPDM": "三元乙丙橡胶EPDM",
    "FIRE_PROTECTION_COATING": "防火涂层",
    "FOAM": "聚氨酯泡沫保温材料",
    "FOAM01": "聚氨酯泡沫保温材料",
    "INDUSTRIAL_OIL": "工业油品",
    "INSULATION": "岩棉隔热材料",
    "IPA": "异丙醇清洗剂IPA",
    "IPA_CLEANER": "异丙醇清洗剂IPA",
    "JET_FUEL": "航天油品Kerosene",
    "MATL_仓库纸箱托盘": "瓦楞纸板",
    "MATL_办公电子塑料": "电子设备塑料ABS",
    "MATL_档案纸张文件": "纸张",
    "MATL_纺织品蓝灰": "纺织品",
    "MATL_航空涂层": "防火涂层",
    "MATL_黑色塑料": "黑色塑料PP",
    "PAPER": "纸张",
    "PP_PLASTIC": "黑色塑料PP",
    "PVC": "PVC电缆绝缘",
    "PVC_CABLE": "PVC电缆绝缘",
    "PVC_CABLE_INSULATION": "PVC电缆绝缘",
    "PVC_CABLE_EQ": "PVC电缆绝缘（等效）",
    "ROCK_WOOL": "岩棉隔热材料",
    "STEEL": "钢材",
    "TEXTILE_FABRIC": "纺织品",
    "YELLOW PINE": "黄木",
    "YELLOW_WOOD": "黄木",
    "fuel": "工业油品",
    "fuel01": "航天油品Kerosene",
    "rubber": "三元乙丙橡胶EPDM",
    "异丙醇": "异丙醇清洗剂IPA",
    "涂层": "防火涂层",
    "Aircraft": "飞机机体材料",
    "CARD_EQ": "瓦楞纸板（等效）",
    "Cleaning_Agent_Drum_Fire": "清洗剂桶燃烧面",
    "concrete": "混凝土",
    "DEFAULT_FLOOR": "默认楼板",
    "DEFAULT_ROOF": "默认屋顶",
    "DEFAULT_WALL": "默认墙体",
    "Default Wall": "默认墙体",
    "Default Wall01": "默认墙体",
    "EPOXY_EQ": "环氧树脂（等效）",
    "foam": "聚氨酯泡沫保温材料",
    "gypsum": "石膏板",
    "GYPSUM": "石膏板",
    "grass": "植被",
    "IfcBuildingElementProxy": "建筑构件",
    "IfcBuildingElementProxy01": "建筑构件",
    "IfcDoor": "门",
    "IfcRailing": "栏杆",
    "INDUSTRIAL_OIL_EQ": "工业油品（等效）",
    "IPA_CLEANER_EQ": "异丙醇清洗剂IPA（等效）",
    "Lubricant_Drum_Fire": "润滑油桶燃烧面",
    "Mac-Body": "飞机机体材料",
    "Mac-Screen Inner": "飞机驾驶舱内饰",
    "Mesh": "计算网格边界",
    "OFFICE_FURNITURE_EQ": "办公家具（等效）",
    "Oil_Product_Drum_Fire": "油品桶燃烧面",
    "Plastic": "塑料制品",
    "RADIATION": "热辐射边界",
    "radiation": "热辐射边界",
    "radiation01": "热辐射边界",
    "radiation02": "热辐射边界",
    "radiationz": "热辐射边界",
    "RADIATIONZ": "热辐射边界",
    "Steel": "钢材",
    "steel": "钢材",
    "SURF_STEEL_DEFAULT": "默认钢表面",
    "SURF_WOOD_YELLOW_PINE": "黄木表面",
    "textile": "纺织品",
    "wall": "墙体",
    "wood": "黄木",
    "wood01": "木质材料",
    "不锈钢": "不锈钢",
    "实木": "实木",
    "塑料 - 黑色": "黑色塑料制品",
    "橡胶，黑色": "黑色橡胶",
    "胶合板，面层": "胶合板面层",
}


def material_display_name(material_id: str | None) -> str:
    """Return a Chinese display name for an FDS material identifier."""
    if not material_id:
        return ""
    return MATERIAL_DISPLAY_NAMES.get(
        material_id,
        MATERIAL_LIBRARY.get(material_id, {}).get("DESCRIPTION", material_id),
    )
