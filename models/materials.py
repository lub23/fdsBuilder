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
    "STEEL": {
        "DENSITY": 7850,
        "CONDUCTIVITY": 45.8,
        "SPECIFIC_HEAT": 0.46,
        "THICKNESS": 0.01,
        "DESCRIPTION": "钢结构",
        "COLOR": "#4a5568",
    },
    "INSULATION": {
        "DENSITY": 30,
        "CONDUCTIVITY": 0.04,
        "SPECIFIC_HEAT": 1.2,
        "THICKNESS": 0.1,
        "DESCRIPTION": "保温层",
        "COLOR": "#fbbf24",
    },
    "BRICK": {
        "DENSITY": 1800,
        "CONDUCTIVITY": 0.7,
        "SPECIFIC_HEAT": 0.84,
        "THICKNESS": 0.24,
        "DESCRIPTION": "砖",
        "COLOR": "#dc2626",
    },
    "WOOD": {
        "DENSITY": 500,
        "CONDUCTIVITY": 0.14,
        "SPECIFIC_HEAT": 2.85,
        "THICKNESS": 0.02,
        "DESCRIPTION": "木材",
        "COLOR": "#92400e",
    },
    "GYPSUM": {
        "DENSITY": 800,
        "CONDUCTIVITY": 0.17,
        "SPECIFIC_HEAT": 1.09,
        "THICKNESS": 0.025,
        "DESCRIPTION": "石膏板",
        "COLOR": "#f5f5f4",
    },
    "GLASS": {
        "DENSITY": 2500,
        "CONDUCTIVITY": 1.0,
        "SPECIFIC_HEAT": 0.84,
        "THICKNESS": 0.006,
        "DESCRIPTION": "玻璃",
        "COLOR": "#38bdf8",
    },
    "ALUMINUM": {
        "DENSITY": 2700,
        "CONDUCTIVITY": 237,
        "SPECIFIC_HEAT": 0.90,
        "THICKNESS": 0.003,
        "DESCRIPTION": "铝合金",
        "COLOR": "#c0c0c0",
    },
    "JET_FUEL": {
        "DENSITY": 800,
        "CONDUCTIVITY": 0.13,
        "SPECIFIC_HEAT": 2.10,
        "THICKNESS": 0.01,
        "DESCRIPTION": "航空煤油",
        "COLOR": "#b45309",
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
    # 5. 金属制品/零件：不可燃目标，仅作辐射热流测量对象
    "METAL_PARTS": {
        "name": "金属制品/零件(不可燃)",
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
