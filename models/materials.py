#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : materials.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : Defining materials and configurations in applications
'''
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
        "COLOR": "#808080"
    },
    "STEEL": {
        "DENSITY": 7850,
        "CONDUCTIVITY": 45.8,
        "SPECIFIC_HEAT": 0.46,
        "THICKNESS": 0.01,
        "DESCRIPTION": "钢结构",
        "COLOR": "#4a5568"
    },
    "INSULATION": {
        "DENSITY": 30,
        "CONDUCTIVITY": 0.04,
        "SPECIFIC_HEAT": 1.2,
        "THICKNESS": 0.1,
        "DESCRIPTION": "保温层",
        "COLOR": "#fbbf24"
    },
    "BRICK": {
        "DENSITY": 1800,
        "CONDUCTIVITY": 0.7,
        "SPECIFIC_HEAT": 0.84,
        "THICKNESS": 0.24,
        "DESCRIPTION": "砖",
        "COLOR": "#dc2626"
    },
    "WOOD": {
        "DENSITY": 500,
        "CONDUCTIVITY": 0.14,
        "SPECIFIC_HEAT": 2.85,
        "THICKNESS": 0.02,
        "DESCRIPTION": "木材",
        "COLOR": "#92400e"
    },
    "GYPSUM": {
        "DENSITY": 800,
        "CONDUCTIVITY": 0.17,
        "SPECIFIC_HEAT": 1.09,
        "THICKNESS": 0.025,
        "DESCRIPTION": "石膏板",
        "COLOR": "#f5f5f4"
    },
    "GLASS": {
        "DENSITY": 2500,
        "CONDUCTIVITY": 1.0,
        "SPECIFIC_HEAT": 0.84,
        "THICKNESS": 0.006,
        "DESCRIPTION": "玻璃",
        "COLOR": "#38bdf8"
    }
}
