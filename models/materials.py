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


COMBUSTIBLE_LIBRARY = {
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
    "INDUSTRIAL_OIL_DRUM": {
        "name": "工业油品(桶装)",
        "length": 0.6, "width": 0.6, "height": 0.9,
        "hrrpua": 900, "ignition_temp": 330, "color": "GREEN",
        "matl": {
            "DENSITY": 880, "CONDUCTIVITY": 0.13,
            "SPECIFIC_HEAT": 2.00, "HEAT_OF_COMBUSTION": 43000,
            "REFERENCE_TEMPERATURE": 330,
        },
    },
    "LIQUID_FUEL_DRUM": {
        "name": "液体燃料(柴油/燃料油)",
        "length": 0.6, "width": 0.6, "height": 0.9,
        "hrrpua": 1200, "ignition_temp": 260, "color": "BROWN",
        "matl": {
            "DENSITY": 830, "CONDUCTIVITY": 0.13,
            "SPECIFIC_HEAT": 2.10, "HEAT_OF_COMBUSTION": 43000,
            "REFERENCE_TEMPERATURE": 260,
        },
    },
    "ORGANIC_SOLVENT_DRUM": {
        "name": "有机溶剂/清洗剂",
        "length": 0.6, "width": 0.6, "height": 0.9,
        "hrrpua": 1500, "ignition_temp": 220, "color": "PURPLE",
        "matl": {
            "DENSITY": 790, "CONDUCTIVITY": 0.16,
            "SPECIFIC_HEAT": 2.20, "HEAT_OF_COMBUSTION": 30000,
            "REFERENCE_TEMPERATURE": 220,
        },
    },
    "COATING_AGENT_DRUM": {
        "name": "涂料/稀释剂/表面处理介质",
        "length": 0.6, "width": 0.6, "height": 0.9,
        "hrrpua": 950, "ignition_temp": 260, "color": "ORANGE",
        "matl": {
            "DENSITY": 950, "CONDUCTIVITY": 0.18,
            "SPECIFIC_HEAT": 1.70, "HEAT_OF_COMBUSTION": 27000,
            "REFERENCE_TEMPERATURE": 260,
        },
    },
    # 简化占位；实际燃气更建议按泄漏/喷射火单独建模
    "COMBUSTIBLE_GAS_CYLINDER": {
        "name": "可燃气体(钢瓶/供气点)",
        "length": 0.3, "width": 0.3, "height": 1.2,
        "hrrpua": 2000, "ignition_temp": 540, "color": "BLUE",
        "matl": {
            "DENSITY": 1.0, "CONDUCTIVITY": 0.03,
            "SPECIFIC_HEAT": 2.20, "HEAT_OF_COMBUSTION": 50000,
            "REFERENCE_TEMPERATURE": 540,
        },
    },
    "WOOD_PALLET": {
        "name": "木托盘",
        "length": 1.2, "width": 1.0, "height": 0.15,
        "hrrpua": 250, "ignition_temp": 350, "color": "BROWN",
        "matl": {
            "DENSITY": 500, "CONDUCTIVITY": 0.14,
            "SPECIFIC_HEAT": 2.85, "HEAT_OF_COMBUSTION": 18000,
            "REFERENCE_TEMPERATURE": 350,
        },
    },
    "PAPER_STACK": {
        "name": "纸张堆",
        "length": 0.8, "width": 0.6, "height": 0.5,
        "hrrpua": 300, "ignition_temp": 240, "color": "KHAKI",
        "matl": {
            "DENSITY": 300, "CONDUCTIVITY": 0.08,
            "SPECIFIC_HEAT": 1.34, "HEAT_OF_COMBUSTION": 16000,
            "REFERENCE_TEMPERATURE": 240,
        },
    },
    "PLASTIC_PACKAGING": {
        "name": "塑料包装/器具",
        "length": 0.8, "width": 0.6, "height": 0.6,
        "hrrpua": 800, "ignition_temp": 360, "color": "CYAN",
        "matl": {
            "DENSITY": 920, "CONDUCTIVITY": 0.22,
            "SPECIFIC_HEAT": 1.90, "HEAT_OF_COMBUSTION": 43000,
            "REFERENCE_TEMPERATURE": 360,
        },
    },
    "ELECTRICAL_PLASTIC": {
        "name": "电气塑料部件",
        "length": 0.6, "width": 0.4, "height": 0.4,
        "hrrpua": 650, "ignition_temp": 420, "color": "GRAY",
        "matl": {
            "DENSITY": 1100, "CONDUCTIVITY": 0.19,
            "SPECIFIC_HEAT": 1.30, "HEAT_OF_COMBUSTION": 26000,
            "REFERENCE_TEMPERATURE": 420,
        },
    },
    "POLYMER_MATERIAL": {
        "name": "高分子材料",
        "length": 1.0, "width": 0.8, "height": 0.6,
        "hrrpua": 700, "ignition_temp": 360, "color": "BLUE",
        "matl": {
            "DENSITY": 950, "CONDUCTIVITY": 0.22,
            "SPECIFIC_HEAT": 1.80, "HEAT_OF_COMBUSTION": 35000,
            "REFERENCE_TEMPERATURE": 360,
        },
    },
    "RUBBER_POLYMER_PARTS": {
        "name": "橡胶/聚合物部件",
        "length": 0.8, "width": 0.6, "height": 0.5,
        "hrrpua": 700, "ignition_temp": 370, "color": "BLACK",
        "matl": {
            "DENSITY": 1100, "CONDUCTIVITY": 0.20,
            "SPECIFIC_HEAT": 1.90, "HEAT_OF_COMBUSTION": 35000,
            "REFERENCE_TEMPERATURE": 370,
        },
    },
    "FOAM_PACKAGING": {
        "name": "泡沫缓冲材料",
        "length": 1.2, "width": 0.8, "height": 0.6,
        "hrrpua": 1200, "ignition_temp": 330, "color": "YELLOW",
        "matl": {
            "DENSITY": 30, "CONDUCTIVITY": 0.04,
            "SPECIFIC_HEAT": 1.40, "HEAT_OF_COMBUSTION": 26000,
            "REFERENCE_TEMPERATURE": 330,
        },
    },
    "TEXTILE_ROLL": {
        "name": "织物卷/织物堆",
        "length": 0.5, "width": 0.5, "height": 1.5,
        "hrrpua": 450, "ignition_temp": 260, "color": "MAGENTA",
        "matl": {
            "DENSITY": 180, "CONDUCTIVITY": 0.05,
            "SPECIFIC_HEAT": 1.40, "HEAT_OF_COMBUSTION": 17000,
            "REFERENCE_TEMPERATURE": 260,
        },
    },
    "OILY_WASTE_BIN": {
        "name": "含油抹布/过滤材料",
        "length": 0.5, "width": 0.5, "height": 0.7,
        "hrrpua": 650, "ignition_temp": 220, "color": "RED",
        "matl": {
            "DENSITY": 200, "CONDUCTIVITY": 0.08,
            "SPECIFIC_HEAT": 1.60, "HEAT_OF_COMBUSTION": 28000,
            "REFERENCE_TEMPERATURE": 220,
        },
    },
    "PROCESS_CHEMICAL_CONTAINER": {
        "name": "工艺特有化学品",
        "length": 0.6, "width": 0.6, "height": 0.9,
        "hrrpua": 700, "ignition_temp": 300, "color": "PURPLE",
        "matl": {
            "DENSITY": 1050, "CONDUCTIVITY": 0.20,
            "SPECIFIC_HEAT": 1.50, "HEAT_OF_COMBUSTION": 25000,
            "REFERENCE_TEMPERATURE": 300,
        },
    },
    "OILY_SLUDGE_CONTAINER": {
        "name": "油泥/污泥/残渣",
        "length": 0.6, "width": 0.6, "height": 0.8,
        "hrrpua": 400, "ignition_temp": 300, "color": "GRAY",
        "matl": {
            "DENSITY": 1100, "CONDUCTIVITY": 0.20,
            "SPECIFIC_HEAT": 1.80, "HEAT_OF_COMBUSTION": 20000,
            "REFERENCE_TEMPERATURE": 300,
        },
    },
    "CARBON_MATERIAL_STACK": {
        "name": "炭素材料",
        "length": 1.0, "width": 0.8, "height": 0.6,
        "hrrpua": 250, "ignition_temp": 500, "color": "BLACK",
        "matl": {
            "DENSITY": 1600, "CONDUCTIVITY": 1.00,
            "SPECIFIC_HEAT": 0.90, "HEAT_OF_COMBUSTION": 30000,
            "REFERENCE_TEMPERATURE": 500,
        },
    },
    "COAL_STACK": {
        "name": "煤炭堆",
        "length": 1.2, "width": 1.0, "height": 0.8,
        "hrrpua": 350, "ignition_temp": 400, "color": "BLACK",
        "matl": {
            "DENSITY": 1350, "CONDUCTIVITY": 0.26,
            "SPECIFIC_HEAT": 1.25, "HEAT_OF_COMBUSTION": 29000,
            "REFERENCE_TEMPERATURE": 400,
        },
    },
    # 简化占位；实际粉尘危险性应单独按粉尘火/爆炸处理
    "COAL_DUST_HOPPER": {
        "name": "煤粉/碳粉料斗",
        "length": 0.8, "width": 0.8, "height": 1.2,
        "hrrpua": 800, "ignition_temp": 380, "color": "GRAY",
        "matl": {
            "DENSITY": 600, "CONDUCTIVITY": 0.10,
            "SPECIFIC_HEAT": 1.25, "HEAT_OF_COMBUSTION": 29000,
            "REFERENCE_TEMPERATURE": 380,
        },
    },
    # 简化占位；铝粉/钽粉/贵金属粉尘等实际应按金属粉尘专门评估
    "METAL_DUST_COLLECTOR": {
        "name": "金属粉尘/含粉介质",
        "length": 0.8, "width": 0.8, "height": 1.5,
        "hrrpua": 1000, "ignition_temp": 600, "color": "GRAY",
        "matl": {
            "DENSITY": 1200, "CONDUCTIVITY": 0.50,
            "SPECIFIC_HEAT": 0.90, "HEAT_OF_COMBUSTION": 15000,
            "REFERENCE_TEMPERATURE": 600,
        },
    },
    "POLISHING_PASTE_BIN": {
        "name": "抛光膏/糊状可燃物",
        "length": 0.6, "width": 0.4, "height": 0.4,
        "hrrpua": 500, "ignition_temp": 300, "color": "YELLOW",
        "matl": {
            "DENSITY": 1100, "CONDUCTIVITY": 0.21,
            "SPECIFIC_HEAT": 1.60, "HEAT_OF_COMBUSTION": 18000,
            "REFERENCE_TEMPERATURE": 300,
        },
    },
    "WOOD_FURNITURE": {
        "name": "木质家具",
        "length": 1.2, "width": 0.6, "height": 1.0,
        "hrrpua": 280, "ignition_temp": 350, "color": "BROWN",
        "matl": {
            "DENSITY": 550, "CONDUCTIVITY": 0.14,
            "SPECIFIC_HEAT": 2.85, "HEAT_OF_COMBUSTION": 18000,
            "REFERENCE_TEMPERATURE": 350,
        },
    },
    "OFFICE_COMPOSITE_FURNITURE": {
        "name": "木塑复合办公家具",
        "length": 1.4, "width": 0.7, "height": 0.8,
        "hrrpua": 320, "ignition_temp": 320, "color": "BROWN",
        "matl": {
            "DENSITY": 520, "CONDUCTIVITY": 0.16,
            "SPECIFIC_HEAT": 2.10, "HEAT_OF_COMBUSTION": 19000,
            "REFERENCE_TEMPERATURE": 320,
        },
    },
    "UPHOLSTERED_SEAT": {
        "name": "软包座椅",
        "length": 0.6, "width": 0.6, "height": 0.9,
        "hrrpua": 550, "ignition_temp": 280, "color": "RED",
        "matl": {
            "DENSITY": 70, "CONDUCTIVITY": 0.10,
            "SPECIFIC_HEAT": 1.40, "HEAT_OF_COMBUSTION": 25000,
            "REFERENCE_TEMPERATURE": 280,
        },
    },
    "ELECTRONICS_CONSOLE": {
        "name": "电子设备/控制台",
        "length": 1.2, "width": 0.6, "height": 1.8,
        "hrrpua": 500, "ignition_temp": 390, "color": "GRAY",
        "matl": {
            "DENSITY": 1050, "CONDUCTIVITY": 0.20,
            "SPECIFIC_HEAT": 1.35, "HEAT_OF_COMBUSTION": 23000,
            "REFERENCE_TEMPERATURE": 390,
        },
    },
    "CABLE_BUNDLE": {
        "name": "电缆线束",
        "length": 1.0, "width": 0.3, "height": 0.3,
        "hrrpua": 550, "ignition_temp": 360, "color": "BLACK",
        "matl": {
            "DENSITY": 1380, "CONDUCTIVITY": 0.22,
            "SPECIFIC_HEAT": 1.20, "HEAT_OF_COMBUSTION": 20000,
            "REFERENCE_TEMPERATURE": 360,
        },
    },
    "CARPET_FINISH": {
        "name": "地毯/软质饰面",
        "length": 2.0, "width": 1.0, "height": 0.02,
        "hrrpua": 400, "ignition_temp": 300, "color": "MAGENTA",
        "matl": {
            "DENSITY": 220, "CONDUCTIVITY": 0.06,
            "SPECIFIC_HEAT": 1.40, "HEAT_OF_COMBUSTION": 22000,
            "REFERENCE_TEMPERATURE": 300,
        },
    },
    "ACOUSTIC_PANEL": {
        "name": "声学吸音板/软包饰面",
        "length": 1.2, "width": 0.6, "height": 0.05,
        "hrrpua": 250, "ignition_temp": 280, "color": "IVORY",
        "matl": {
            "DENSITY": 120, "CONDUCTIVITY": 0.05,
            "SPECIFIC_HEAT": 1.30, "HEAT_OF_COMBUSTION": 15000,
            "REFERENCE_TEMPERATURE": 280,
        },
    },
    "LIGHTWEIGHT_PARTITION": {
        "name": "轻质隔断/复合墙板/活动地板",
        "length": 1.2, "width": 0.1, "height": 2.4,
        "hrrpua": 180, "ignition_temp": 320, "color": "KHAKI",
        "matl": {
            "DENSITY": 280, "CONDUCTIVITY": 0.12,
            "SPECIFIC_HEAT": 1.10, "HEAT_OF_COMBUSTION": 8000,
            "REFERENCE_TEMPERATURE": 320,
        },
    },
    "DISPLAY_PROP_MODEL": {
        "name": "展示模型/沙盘/宣传板",
        "length": 1.2, "width": 0.8, "height": 1.2,
        "hrrpua": 450, "ignition_temp": 300, "color": "YELLOW",
        "matl": {
            "DENSITY": 250, "CONDUCTIVITY": 0.09,
            "SPECIFIC_HEAT": 1.40, "HEAT_OF_COMBUSTION": 18000,
            "REFERENCE_TEMPERATURE": 300,
        },
    },
    "SURFACE_COATING_LAYER": {
        "name": "固化涂层/密封胶表层",
        "length": 1.0, "width": 1.0, "height": 0.005,
        "hrrpua": 180, "ignition_temp": 380, "color": "GRAY",
        "matl": {
            "DENSITY": 1150, "CONDUCTIVITY": 0.20,
            "SPECIFIC_HEAT": 1.30, "HEAT_OF_COMBUSTION": 10000,
            "REFERENCE_TEMPERATURE": 380,
        },
    },
    "BITUMEN_MEMBRANE": {
        "name": "沥青/高分子防水层",
        "length": 1.0, "width": 1.0, "height": 0.01,
        "hrrpua": 650, "ignition_temp": 330, "color": "BLACK",
        "matl": {
            "DENSITY": 1200, "CONDUCTIVITY": 0.17,
            "SPECIFIC_HEAT": 1.40, "HEAT_OF_COMBUSTION": 40000,
            "REFERENCE_TEMPERATURE": 330,
        },
    },
    "FIBER_INSULATION_LAYER": {
        "name": "纤维/纸质保温层",
        "length": 1.2, "width": 0.6, "height": 0.1,
        "hrrpua": 120, "ignition_temp": 420, "color": "IVORY",
        "matl": {
            "DENSITY": 60, "CONDUCTIVITY": 0.04,
            "SPECIFIC_HEAT": 1.00, "HEAT_OF_COMBUSTION": 6000,
            "REFERENCE_TEMPERATURE": 420,
        },
    },
    "TEMP_TIMBER_WORKS": {
        "name": "临时木构件/脚手板/模板",
        "length": 1.2, "width": 0.8, "height": 0.5,
        "hrrpua": 250, "ignition_temp": 350, "color": "BROWN",
        "matl": {
            "DENSITY": 500, "CONDUCTIVITY": 0.14,
            "SPECIFIC_HEAT": 2.85, "HEAT_OF_COMBUSTION": 18000,
            "REFERENCE_TEMPERATURE": 350,
        },
    },
    "FRP_RUBBER_PANEL": {
        "name": "FRP格栅/橡胶防滑板",
        "length": 1.0, "width": 1.0, "height": 0.05,
        "hrrpua": 500, "ignition_temp": 360, "color": "BLUE",
        "matl": {
            "DENSITY": 1450, "CONDUCTIVITY": 0.25,
            "SPECIFIC_HEAT": 1.20, "HEAT_OF_COMBUSTION": 20000,
            "REFERENCE_TEMPERATURE": 360,
        },
    },
    "AEROSPACE_COMPOSITE_PART": {
        "name": "航天复合材料部件",
        "length": 1.0, "width": 0.8, "height": 0.3,
        "hrrpua": 380, "ignition_temp": 420, "color": "CYAN",
        "matl": {
            "DENSITY": 1550, "CONDUCTIVITY": 0.35,
            "SPECIFIC_HEAT": 1.10, "HEAT_OF_COMBUSTION": 18000,
            "REFERENCE_TEMPERATURE": 420,
        },
    },
    "ESD_PACKAGING_MATERIAL": {
        "name": "防静电包装/静电屏蔽材料",
        "length": 0.8, "width": 0.6, "height": 0.4,
        "hrrpua": 800, "ignition_temp": 340, "color": "PURPLE",
        "matl": {
            "DENSITY": 120, "CONDUCTIVITY": 0.20,
            "SPECIFIC_HEAT": 1.90, "HEAT_OF_COMBUSTION": 35000,
            "REFERENCE_TEMPERATURE": 340,
        },
    },
    "ADHESIVE_SEALANT_SET": {
        "name": "胶带/密封胶/环氧粘结剂",
        "length": 0.6, "width": 0.4, "height": 0.4,
        "hrrpua": 600, "ignition_temp": 280, "color": "ORANGE",
        "matl": {
            "DENSITY": 1100, "CONDUCTIVITY": 0.21,
            "SPECIFIC_HEAT": 1.50, "HEAT_OF_COMBUSTION": 25000,
            "REFERENCE_TEMPERATURE": 280,
        },
    },
    "PREPREG_MATERIAL": {
        "name": "预浸料/热缩套管",
        "length": 1.0, "width": 0.3, "height": 0.3,
        "hrrpua": 550, "ignition_temp": 300, "color": "GREEN",
        "matl": {
            "DENSITY": 1300, "CONDUCTIVITY": 0.25,
            "SPECIFIC_HEAT": 1.20, "HEAT_OF_COMBUSTION": 22000,
            "REFERENCE_TEMPERATURE": 300,
        },
    },
    "JET_FUEL_RESIDUE": {
        "name": "航空煤油残留",
        "length": 0.6, "width": 0.6, "height": 0.2,
        "hrrpua": 1400, "ignition_temp": 210, "color": "BROWN",
        "matl": {
            "DENSITY": 800, "CONDUCTIVITY": 0.13,
            "SPECIFIC_HEAT": 2.10, "HEAT_OF_COMBUSTION": 43000,
            "REFERENCE_TEMPERATURE": 210,
        },
    },
    "GLYCOL_DEICING_FLUID": {
        "name": "除冰液(乙二醇类)",
        "length": 0.6, "width": 0.6, "height": 0.9,
        "hrrpua": 350, "ignition_temp": 370, "color": "GREEN",
        "matl": {
            "DENSITY": 1080, "CONDUCTIVITY": 0.25,
            "SPECIFIC_HEAT": 2.40, "HEAT_OF_COMBUSTION": 16000,
            "REFERENCE_TEMPERATURE": 370,
        },
    },
    "RUBBER_HOSE_ASSEMBLY": {
        "name": "橡胶/塑料软管组件",
        "length": 1.0, "width": 0.2, "height": 0.2,
        "hrrpua": 650, "ignition_temp": 370, "color": "BLACK",
        "matl": {
            "DENSITY": 1050, "CONDUCTIVITY": 0.20,
            "SPECIFIC_HEAT": 1.80, "HEAT_OF_COMBUSTION": 32000,
            "REFERENCE_TEMPERATURE": 370,
        },
    },
    "AIRCRAFT_INTERIOR_TRIM": {
        "name": "机舱内饰/软装组件",
        "length": 1.0, "width": 0.8, "height": 0.4,
        "hrrpua": 500, "ignition_temp": 320, "color": "MAGENTA",
        "matl": {
            "DENSITY": 90, "CONDUCTIVITY": 0.08,
            "SPECIFIC_HEAT": 1.40, "HEAT_OF_COMBUSTION": 22000,
            "REFERENCE_TEMPERATURE": 320,
        },
    },
}