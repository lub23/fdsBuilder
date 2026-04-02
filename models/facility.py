#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File  : facility.py
@Author: Lubber
@Date  : 2026-03-09
@Version : 1.0
@Desc  : Preset facility data management and equivalent model generation
"""

import json, os
from typing import List, Tuple, Dict, Any

from models.building import (
    BuildingModel,
    Building,
    BuildingGroup,
    Story,
    FloorSlab,
    FireCompartment,
    LayoutMode,
    compute_layout,
)
from models.combustibles import (
    CombustibleManager,
    Combustible,
    DistributionMethod,
    SPECIALIZED_COMPONENTS,
    ComponentPart,
)
from models.materials import COMBUSTIBLE_LIBRARY
from models.overlap import (
    OBSTEntry,
    resolve_overlaps,
    PRIORITY_WALL,
    PRIORITY_STAIRWELL,
    PRIORITY_COMPONENT,
    PRIORITY_COMBUSTIBLE,
)

WALL_NAMES = ["南墙", "北墙", "东墙", "西墙", "均匀分布"]


class FacilityManager:
    def __init__(self):
        import os

        self._data: Dict[str, Any] = {}
        facilities_dir = os.path.join(
            os.path.dirname(__file__), "..", "data", "facilities"
        )
        for filename in os.listdir(facilities_dir):
            if filename.endswith(".json") and filename != "__init__.py":
                with open(
                    os.path.join(facilities_dir, filename), "r", encoding="utf-8"
                ) as f:
                    category_data = json.load(f)
                    category_key = filename[:-5]
                    self._data[category_key] = category_data

    # ── 查询 ──────────────────────────────────────

    def categories(self) -> List[Tuple[str, str]]:
        return [(k, v["cn_name"]) for k, v in self._data.items()]

    def sub_types(self, cat: str) -> List[Tuple[str, str]]:
        subs = self._data.get(cat, {}).get("sub_types", {})
        return [(k, v["cn_name"]) for k, v in subs.items()]

    def facility(self, cat: str, sub: str) -> dict:
        return self._data[cat]["sub_types"][sub]

    # ── 值解析 ────────────────────────────────────

    @staticmethod
    def _rv(p) -> float:
        if not isinstance(p, dict):
            return float(p)
        med = p.get("median", -1)
        if med is not None and med > 0:
            return float(med)
        return round((p.get("min", 0) + p.get("max", 0)) / 2, 2)

    @staticmethod
    def _rng(p) -> Tuple[float, float]:
        if not isinstance(p, dict):
            v = float(p)
            return (v, v)
        return (float(p.get("min", 0)), float(p.get("max", 0)))

    # ── 默认参数 ──────────────────────────────────

    def default_params(self, cat: str, sub: str) -> dict:
        f = self.facility(cat, sub)
        b = f["building"]
        d = f.get("doors", {})
        w = f.get("windows", {})
        _r = self._rv

        rng = {}
        for key, src in [
            ("length", b["length"]),
            ("width", b["width"]),
            ("height", b["height"]),
            ("stories", b.get("stories", {"min": 1, "max": 1})),
            ("door_width", d.get("width", {"min": 1.2, "max": 1.5})),
            ("door_height", d.get("height", {"min": 2.1, "max": 2.4})),
            ("door_count", d.get("count", {"min": 0, "max": 0})),
            ("window_width", w.get("width", {"min": 1.5, "max": 2})),
            ("window_height", w.get("height", {"min": 1.5, "max": 2})),
            ("window_count", w.get("count", {"min": 0, "max": 0})),
        ]:
            lo, hi = self._rng(src)
            if key in ("stories", "door_count", "window_count"):
                lo, hi = int(lo), int(hi)
            rng[key] = (lo, hi)
        # Collect all combustible keys from fire_compartments
        fc_defs = f.get("fire_compartments", [])
        all_comb_keys = []
        for fc in fc_defs:
            for item in fc.get("combustibles", []):
                if item["key"] not in all_comb_keys:
                    all_comb_keys.append(item["key"])

        return dict(
            cat_key=cat,
            sub_key=sub,
            cat_name=self._data[cat]["cn_name"],
            name=f.get("cn_name", sub),
            description=f.get("description", ""),
            facility_combustibles=all_comb_keys,
            fire_compartments=fc_defs,
            length=_r(b["length"]),
            width=_r(b["width"]),
            height=_r(b["height"]),
            stories=max(1, int(_r(b.get("stories", {"min": 1, "max": 1})))),
            wall_thickness=f.get("wall_thickness", 0.24),
            door_width=_r(d.get("width", {"min": 1.2, "max": 1.5})),
            door_height=_r(d.get("height", {"min": 2.1, "max": 2.4})),
            door_count=max(0, int(_r(d.get("count", {"min": 0, "max": 0})))),
            door_wall=4,
            window_width=_r(w.get("width", {"min": 1.5, "max": 2})),
            window_height=_r(w.get("height", {"min": 1.5, "max": 2})),
            window_count=max(0, int(_r(w.get("count", {"min": 0, "max": 0})))),
            window_wall=4,
            window_sill=0.6,
            offset={
                "x": f.get("offset", {}).get("x", 0),
                "y": f.get("offset", {}).get("y", 0),
            },
            rotation=f.get("rotation", 0),
            stairwell_config=f.get("stairwell", None),
            stairwell_count=0,
            stairwell_length=4.0,
            stairwell_width=3.0,
            combustible_selections={},
            combustible_method=0,
            combustible_floor=-1,
            ranges=rng,
            specialized_components=f.get("specialized_components", []),
            fire_separation=self._data[cat].get("fire_separation", 10.0),
        )

    # ══════════════════════════════════════════════
    #  分类级别生成（多建筑群）
    # ══════════════════════════════════════════════

    def generate_group(
        self, cat_key: str, building_params: list = None, fire_separation: float = 10.0
    ) -> BuildingModel:
        """Generate a BuildingGroup with all sub_types under a category.

        building_params: list of dicts with keys (sub_key, x_offset, y_offset, ...)
                         if None, auto-arrange using enclosure layout.
        """
        subs = self.sub_types(cat_key)
        if not subs:
            return BuildingModel()

        model = BuildingModel()
        model.chid = cat_key
        model.building_group.buildings.clear()
        model.building_group.fire_separation = fire_separation

        if building_params is None:
            # Build temporary buildings to compute layout
            temp_buildings = []
            temp_params = []
            for sub_key, sub_name in subs:
                p = self.default_params(cat_key, sub_key)
                b = Building(
                    name=p.get("name", sub_name), length=p["length"], width=p["width"]
                )
                # Set story heights for fire separation calculation
                n_st = max(1, p.get("stories", 1))
                st_h = round(p["height"] / n_st, 2)
                b.stories = [Story(name=f"{i + 1}F", height=st_h) for i in range(n_st)]
                b.update_z_offsets()
                temp_buildings.append(b)
                temp_params.append(p)

            # Auto fire separation from max building height
            if temp_buildings:
                max_h = max(b.total_height for b in temp_buildings)
                fire_separation = max(max_h * 1.2, fire_separation, 10.0)

            mode = LayoutMode.ENCLOSURE
            offsets = compute_layout(temp_buildings, mode, fire_separation)

            building_params = []
            for i, (p, (xo, yo)) in enumerate(zip(temp_params, offsets)):
                # Use custom offset from sub_type if explicitly set (not None)
                custom_offset = p.get("offset")
                if custom_offset is not None:
                    xo, yo = custom_offset["x"], custom_offset["y"]
                building_params.append(
                    {
                        "params": p,
                        "x_offset": xo,
                        "y_offset": yo,
                    }
                )

        for bp in building_params:
            p = bp.get("params") or self.default_params(cat_key, bp["sub_key"])
            sub_model = self.generate_model(p)
            building = sub_model.building_group.buildings[0]
            # Use custom offset from params if explicitly set
            custom_offset = p.get("offset")
            if custom_offset is not None:
                building.x_offset = custom_offset["x"]
                building.y_offset = custom_offset["y"]
            else:
                building.x_offset = bp.get("x_offset", 0.0)
                building.y_offset = bp.get("y_offset", 0.0)
            model.building_group.add_building(building)

        # Sync compat attributes from first building
        if model.building_group.buildings:
            b0 = model.building_group.buildings[0]
            model.length = b0.length
            model.width = b0.width
            model.wall_thickness = b0.wall_thickness
            model.stories = b0.stories
            model.roof = b0.roof
            model.materials = b0.materials

        return model

    # ══════════════════════════════════════════════
    #  模型生成
    # ══════════════════════════════════════════════

    def generate_model(self, p: dict) -> BuildingModel:
        n_st = max(1, p["stories"])
        st_h = round(p["height"] / n_st, 2)
        L, W, t = p["length"], p["width"], p["wall_thickness"]

        model = BuildingModel()
        model.chid = f"{p.get('cat_key', 'fac')}-{p.get('sub_key', 'unit')}"

        building = model.building_group.buildings[0]
        building.name = p.get("name", "建筑1")
        building.length = L
        building.width = W
        building.wall_thickness = t
        building.rotation = p.get("rotation", 0)
        building.stories = [
            Story(
                name=f"{i + 1}F",
                height=st_h,
                walls=[],
                openings=[],
                combustibles=CombustibleManager(),
                floor_slab=FloorSlab(),
            )
            for i in range(n_st)
        ]
        model.length = L
        model.width = W
        model.wall_thickness = t
        model.stories = building.stories
        model.roof = building.roof
        model.materials = building.materials
        model.update_z_offsets()
        model.update_external_walls()

        # 门窗
        self._place_openings(model, p, "door")
        self._place_openings(model, p, "window")
        self._resolve_overlaps(model)

        # 自动楼梯口（2F+每层一个）
        if n_st > 1:
            stairwell_config = p.get("stairwell_config")
            if stairwell_config:
                sw_l = stairwell_config.get("length", min(4.0, L * 0.3))
                sw_w = stairwell_config.get("width", min(3.0, W * 0.3))
                position = stairwell_config.get("position", "右下角")
                # 根据位置计算坐标
                margin = t + 0.3
                if position == "右下角":
                    sw_x = L - sw_l - margin
                    sw_y = W - sw_w - margin
                elif position == "左下角":
                    sw_x = margin
                    sw_y = W - sw_w - margin
                elif position == "左上角":
                    sw_x = margin
                    sw_y = margin
                else:  # 右上角 或 默认
                    sw_x = L - sw_l - margin
                    sw_y = margin
            else:
                # 默认西南角
                sw_l = min(4.0, L * 0.3)
                sw_w = min(3.0, W * 0.3)
                sw_x = t + 0.5
                sw_y = t + 0.5

            for si in range(1, n_st):
                building.stories[si].floor_slab.openings.append(
                    dict(x=sw_x, y=sw_y, length=sw_l, width=sw_w, name="自动楼梯口")
                )

        # 防火分区预置（含分区级可燃物和专属组件）
        fc_defs = p.get("fire_compartments", [])
        if fc_defs:
            self._apply_preset_compartments(building, fc_defs, L, W, t)
        else:
            # 无预设分区时，使用手动可燃物选择
            self._place_combustibles_manual(model, p)
            # 专属组件
            sc_list = p.get("specialized_components", [])
            if sc_list:
                building.specialized_components = list(sc_list)
                self._place_specialized_components(building.stories[0], sc_list, t)

        # OBST 重叠检测与自动调整
        self._resolve_all_overlaps(building)
        return model

    # ── 防火分区预置加载 ──────────────────────────

    @staticmethod
    def _apply_preset_compartments(building, fc_defs, L, W, t):
        """Apply preset fire compartments from industrial.json definitions.

        For each compartment definition:
        1. Convert ratio → absolute coordinates → FireCompartment
        2. Generate partition walls at compartment boundaries
        3. Generate openings on partition walls
        4. Place combustibles within compartment bounds
        5. Place specialized components within compartment bounds
        """
        story = building.stories[0]  # compartments apply to first story

        # Step 1: Create FireCompartment objects
        compartments = []
        for i, fc_def in enumerate(fc_defs):
            x_ratio = fc_def.get("x_ratio", [0, 1])
            y_ratio = fc_def.get("y_ratio", [0, 1])
            fc = FireCompartment(
                id=f"FC_{i}",
                name=fc_def.get("name", f"防火分区{i + 1}"),
                x_min=round(x_ratio[0] * L, 2),
                x_max=round(x_ratio[1] * L, 2),
                y_min=round(y_ratio[0] * W, 2),
                y_max=round(y_ratio[1] * W, 2),
                firewall_thickness=fc_def.get("wall_thickness", t),
                firewall_material=fc_def.get("wall_material", "CONCRETE"),
            )
            compartments.append(fc)
        story.fire_compartments = compartments

        # Step 2: Generate partition walls (deduplicated by position)
        wall_positions = set()  # (x1, y1, x2, y2) rounded
        for fc in compartments:
            # Vertical walls at x_min and x_max (if not at building edge)
            if fc.x_min > 0.01:
                key = (
                    round(fc.x_min, 2),
                    round(fc.y_min, 2),
                    round(fc.x_min, 2),
                    round(fc.y_max, 2),
                )
                if key not in wall_positions:
                    wall_positions.add(key)
                    story.walls.append(
                        {
                            "name": f"{fc.name}_分区墙",
                            "x1": fc.x_min,
                            "y1": fc.y_min,
                            "x2": fc.x_min,
                            "y2": fc.y_max,
                            "thickness": fc.firewall_thickness,
                            "height": story.height,
                            "is_external": False,
                            "is_fire_partition": True,
                            "material": fc.firewall_material,
                        }
                    )
            if fc.x_max < L - 0.01:
                key = (
                    round(fc.x_max, 2),
                    round(fc.y_min, 2),
                    round(fc.x_max, 2),
                    round(fc.y_max, 2),
                )
                if key not in wall_positions:
                    wall_positions.add(key)
                    story.walls.append(
                        {
                            "name": f"{fc.name}_分区墙",
                            "x1": fc.x_max,
                            "y1": fc.y_min,
                            "x2": fc.x_max,
                            "y2": fc.y_max,
                            "thickness": fc.firewall_thickness,
                            "height": story.height,
                            "is_external": False,
                            "is_fire_partition": True,
                            "material": fc.firewall_material,
                        }
                    )
            # Horizontal walls at y_min and y_max
            if fc.y_min > 0.01:
                key = (
                    round(fc.x_min, 2),
                    round(fc.y_min, 2),
                    round(fc.x_max, 2),
                    round(fc.y_min, 2),
                )
                if key not in wall_positions:
                    wall_positions.add(key)
                    story.walls.append(
                        {
                            "name": f"{fc.name}_分区墙",
                            "x1": fc.x_min,
                            "y1": fc.y_min,
                            "x2": fc.x_max,
                            "y2": fc.y_min,
                            "thickness": fc.firewall_thickness,
                            "height": story.height,
                            "is_external": False,
                            "is_fire_partition": True,
                            "material": fc.firewall_material,
                        }
                    )
            if fc.y_max < W - 0.01:
                key = (
                    round(fc.x_min, 2),
                    round(fc.y_max, 2),
                    round(fc.x_max, 2),
                    round(fc.y_max, 2),
                )
                if key not in wall_positions:
                    wall_positions.add(key)
                    story.walls.append(
                        {
                            "name": f"{fc.name}_分区墙",
                            "x1": fc.x_min,
                            "y1": fc.y_max,
                            "x2": fc.x_max,
                            "y2": fc.y_max,
                            "thickness": fc.firewall_thickness,
                            "height": story.height,
                            "is_external": False,
                            "is_fire_partition": True,
                            "material": fc.firewall_material,
                        }
                    )

        # Step 3: Generate openings on partition walls
        for i, fc_def in enumerate(fc_defs):
            fc = compartments[i]
            for opening_def in fc_def.get("openings", []):
                wall_side = opening_def.get("wall", "")
                # Find the matching partition wall
                target_wall_idx = FacilityManager._find_partition_wall(
                    story.walls, fc, wall_side
                )
                if target_wall_idx < 0:
                    continue
                wall = story.walls[target_wall_idx]
                wall_len = (
                    (wall["x2"] - wall["x1"]) ** 2 + (wall["y2"] - wall["y1"]) ** 2
                ) ** 0.5
                if wall_len < 0.1:
                    continue
                story.openings.append(
                    dict(
                        wall_index=target_wall_idx,
                        type=opening_def.get("type", "door"),
                        position=opening_def.get("position", 0.5),
                        width=min(opening_def.get("width", 2.0), wall_len * 0.8),
                        height=min(opening_def.get("height", 2.5), story.height - 0.1),
                        z_bottom=opening_def.get("z_bottom", 0),
                    )
                )

        # Step 4: Place combustibles per compartment
        for i, fc_def in enumerate(fc_defs):
            fc = compartments[i]
            fc_L = fc.x_max - fc.x_min
            fc_W = fc.y_max - fc.y_min
            fc_t = fc.firewall_thickness

            for item in fc_def.get("combustibles", []):
                key = item.get("key", "")
                count = item.get("count", 0)
                if count <= 0 or key not in COMBUSTIBLE_LIBRARY:
                    continue
                new_items = story.combustibles.generate(
                    preset_key=key,
                    count=count,
                    method=DistributionMethod.UNIFORM_GRID,
                    room_length=fc_L,
                    room_width=fc_W,
                    wall_thickness=fc_t,
                )
                # Offset positions from compartment-local to building coords
                for cb in new_items:
                    cb.x = round(cb.x + fc.x_min, 2)
                    cb.y = round(cb.y + fc.y_min, 2)
                    cb.compartment_id = fc.id

        # Step 5: Place specialized components per compartment
        for i, fc_def in enumerate(fc_defs):
            fc = compartments[i]
            sc_list = fc_def.get("specialized_components", [])
            if not sc_list:
                continue
            FacilityManager._place_specialized_in_compartment(story, sc_list, fc, t)

    @staticmethod
    def _find_partition_wall(walls, fc, wall_side):
        """Find wall index matching a compartment boundary side."""
        for wi, w in enumerate(walls):
            if not w.get("is_fire_partition") and not w.get("is_external"):
                continue
            wx1, wy1 = round(w["x1"], 2), round(w["y1"], 2)
            wx2, wy2 = round(w["x2"], 2), round(w["y2"], 2)
            if wall_side == "x_min":
                if (
                    abs(wx1 - round(fc.x_min, 2)) < 0.05
                    and abs(wx2 - round(fc.x_min, 2)) < 0.05
                ):
                    return wi
            elif wall_side == "x_max":
                if (
                    abs(wx1 - round(fc.x_max, 2)) < 0.05
                    and abs(wx2 - round(fc.x_max, 2)) < 0.05
                ):
                    return wi
            elif wall_side == "y_min":
                if (
                    abs(wy1 - round(fc.y_min, 2)) < 0.05
                    and abs(wy2 - round(fc.y_min, 2)) < 0.05
                ):
                    return wi
            elif wall_side == "y_max":
                if (
                    abs(wy1 - round(fc.y_max, 2)) < 0.05
                    and abs(wy2 - round(fc.y_max, 2)) < 0.05
                ):
                    return wi
        return -1

    @staticmethod
    def _place_specialized_in_compartment(story, sc_list, fc, wall_t):
        """Place specialized components centered within a compartment."""
        fc_L = fc.x_max - fc.x_min
        fc_W = fc.y_max - fc.y_min
        margin = wall_t + 1.0

        for sc_info in sc_list:
            key = sc_info.get("key", "")
            comp = SPECIALIZED_COMPONENTS.get(key)
            if not comp:
                continue
            count = sc_info.get("count", 1)
            # Arrange components in a row along X within compartment
            total_needed = count * comp.total_length + (count - 1) * 2.0
            if total_needed > fc_L - 2 * margin:
                # Shrink spacing
                spacing = max(
                    0.5,
                    (fc_L - 2 * margin - count * comp.total_length) / max(count - 1, 1),
                )
            else:
                spacing = 2.0
            start_x = fc.x_min + margin
            center_y = fc.y_min + (fc_W - comp.total_width) / 2

            for ci in range(count):
                inst_x = start_x + ci * (comp.total_length + spacing)
                for pi, part in enumerate(comp.parts):
                    cb = Combustible(
                        name=f"{comp.name}#{ci + 1}_p{pi}",
                        preset_key=part.material_key,
                        x=round(inst_x + part.dx, 2),
                        y=round(center_y + part.dy, 2),
                        z=round(part.dz, 2),
                        length=part.length,
                        width=part.width,
                        height=part.height,
                        hrrpua=comp.hrrpua,
                        ignition_temp=comp.ignition_temp,
                        color="GRAY",
                        component_key=key,
                        material_key=part.material_key,
                        compartment_id=fc.id,
                    )
                    story.combustibles.add(cb)

    @staticmethod
    def _place_specialized_components(story, sc_list, wall_t):
        """Place specialized components in story (no compartment context)."""
        for sc_info in sc_list:
            key = sc_info.get("key", "")
            comp = SPECIALIZED_COMPONENTS.get(key)
            if not comp:
                continue
            count = sc_info.get("count", 1)
            base_x = wall_t + 2.0
            base_y = wall_t + 2.0
            for ci in range(count):
                inst_x = base_x + ci * (comp.total_length + 2.0)
                for pi, part in enumerate(comp.parts):
                    cb = Combustible(
                        name=f"{comp.name}#{ci + 1}_p{pi}",
                        preset_key=part.material_key,
                        x=round(inst_x + part.dx, 2),
                        y=round(base_y + part.dy, 2),
                        z=round(part.dz, 2),
                        length=part.length,
                        width=part.width,
                        height=part.height,
                        hrrpua=comp.hrrpua,
                        ignition_temp=comp.ignition_temp,
                        color="GRAY",
                        component_key=key,
                        material_key=part.material_key,
                    )
                    story.combustibles.add(cb)

    # ── OBST重叠检测 ──────────────────────────────

    @staticmethod
    def _resolve_all_overlaps(building):
        """Collect all OBSTs in building and resolve overlaps by priority."""
        L, W, t = building.length, building.width, building.wall_thickness

        for story in building.stories:
            entries = []

            # Walls → priority 0
            for wi, w in enumerate(story.walls):
                wx1, wy1 = w["x1"], w["y1"]
                wx2, wy2 = w["x2"], w["y2"]
                wt = w.get("thickness", t) / 2
                # Expand wall line into a box
                if abs(wx2 - wx1) < 0.01:  # vertical wall
                    entries.append(
                        OBSTEntry(
                            x1=wx1 - wt,
                            x2=wx1 + wt,
                            y1=min(wy1, wy2),
                            y2=max(wy1, wy2),
                            z1=story.z_bottom,
                            z2=story.z_bottom + w.get("height", story.height),
                            priority=PRIORITY_WALL,
                            source_id=f"wall_{wi}",
                            source_type="wall",
                        )
                    )
                else:  # horizontal wall
                    entries.append(
                        OBSTEntry(
                            x1=min(wx1, wx2),
                            x2=max(wx1, wx2),
                            y1=wy1 - wt,
                            y2=wy1 + wt,
                            z1=story.z_bottom,
                            z2=story.z_bottom + w.get("height", story.height),
                            priority=PRIORITY_WALL,
                            source_id=f"wall_{wi}",
                            source_type="wall",
                        )
                    )

            # Stairwells → priority 1
            for hi, hole in enumerate(story.floor_slab.openings):
                entries.append(
                    OBSTEntry(
                        x1=hole["x"],
                        x2=hole["x"] + hole["length"],
                        y1=hole["y"],
                        y2=hole["y"] + hole["width"],
                        z1=story.z_bottom,
                        z2=story.z_bottom + story.height,
                        priority=PRIORITY_STAIRWELL,
                        source_id=f"stairwell_{hi}",
                        source_type="stairwell",
                    )
                )

            # Combustibles/components → priority 2 or 3
            for cb in story.combustibles.items:
                prio = PRIORITY_COMPONENT if cb.component_key else PRIORITY_COMBUSTIBLE
                entries.append(
                    OBSTEntry(
                        x1=cb.x,
                        x2=cb.x + cb.length,
                        y1=cb.y,
                        y2=cb.y + cb.width,
                        z1=cb.z,
                        z2=cb.z + cb.height,
                        priority=prio,
                        source_id=cb.id,
                        source_type="component" if cb.component_key else "combustible",
                    )
                )

            # Resolve
            kept = resolve_overlaps(entries, t, L - t, t, W - t)
            kept_ids = {e.source_id for e in kept}

            # Update combustible positions from adjusted entries
            adj_map = {
                e.source_id: e
                for e in kept
                if e.source_type in ("component", "combustible")
            }
            new_items = []
            for cb in story.combustibles.items:
                if cb.id not in kept_ids:
                    continue
                adj = adj_map.get(cb.id)
                if adj:
                    cb.x = round(adj.x1, 2)
                    cb.y = round(adj.y1, 2)
                new_items.append(cb)
            story.combustibles.items = new_items

    # ── 门窗放置 ──────────────────────────────────

    @staticmethod
    def _place_openings(model, p, kind):
        cnt = p.get(f"{kind}_count", 0)
        if cnt <= 0:
            return
        ow, oh = p[f"{kind}_width"], p[f"{kind}_height"]
        wall_mode = p.get(f"{kind}_wall", 4)
        sill_ratio = p.get("window_sill", 0.2)
        L, W = model.length, model.width

        targets = [model.stories[0]] if kind == "door" else list(model.stories)
        base, extra = divmod(cnt, len(targets))

        for si, story in enumerate(targets):
            nf = base + (1 if si < extra else 0)
            if nf <= 0:
                continue
            h = min(oh, story.height - 0.1)
            if h < 0.2:
                continue
            if kind == "door":
                zb = 0.0
            else:
                zb = round(story.height * sill_ratio, 2)
                zb = max(0.3, min(zb, story.height - h - 0.05))

            if wall_mode <= 3:
                FacilityManager._add_to_wall(
                    story, wall_mode, nf, ow, h, zb, kind, L, W
                )
            else:
                wlens = [L, L, W, W]
                perim = sum(wlens)
                raw = [nf * wl / perim for wl in wlens]
                counts = [int(r) for r in raw]
                rem = nf - sum(counts)
                order = sorted(range(4), key=lambda i: raw[i] - counts[i], reverse=True)
                for k in range(rem):
                    counts[order[k]] += 1
                for wi in range(4):
                    if counts[wi] > 0:
                        FacilityManager._add_to_wall(
                            story, wi, counts[wi], ow, h, zb, kind, L, W
                        )

    @staticmethod
    def _add_to_wall(story, wi, count, ow, oh, z_bot, kind, L, W):
        wall_len = L if wi <= 1 else W
        max_fit = max(1, int(wall_len / (ow + 0.3)))
        count = min(count, max_fit)
        w = min(ow, wall_len * 0.8 / max(count, 1))
        for j in range(count):
            story.openings.append(
                dict(
                    wall_index=wi,
                    type=kind,
                    position=round((j + 1) / (count + 1), 4),
                    width=round(w, 2),
                    height=round(oh, 2),
                    z_bottom=round(z_bot, 2),
                )
            )

    # ── 重叠调整 ──────────────────────────────────

    @staticmethod
    def _resolve_overlaps(model):
        L, W = model.length, model.width
        for story in model.stories:
            by_wall: Dict[int, list] = {}
            for op in story.openings:
                by_wall.setdefault(op["wall_index"], []).append(op)
            for wi, ops in by_wall.items():
                if len(ops) <= 1:
                    continue
                wall_len = L if wi <= 1 else W
                ops.sort(key=lambda o: o["position"])
                overlap = False
                for i in range(len(ops) - 1):
                    c1 = ops[i]["position"] * wall_len
                    c2 = ops[i + 1]["position"] * wall_len
                    if c2 - c1 - (ops[i]["width"] + ops[i + 1]["width"]) / 2 < 0.1:
                        overlap = True
                        break
                if not overlap:
                    continue
                n = len(ops)
                total_w = sum(o["width"] for o in ops)
                usable = wall_len - 0.3 * (n + 1)
                if total_w > usable > 0:
                    scale = usable / total_w
                    for o in ops:
                        o["width"] = round(o["width"] * scale, 2)
                for i, o in enumerate(ops):
                    o["position"] = round((i + 1) / (n + 1), 4)

    # ── 楼梯口 ────────────────────────────────────

    @staticmethod
    def _calc_stairwell_positions(L, W, t, count, sw_l, sw_w):
        """沿建筑内周均匀分布，返回 [(x, y), ...]（模型坐标）。"""
        if count <= 0:
            return []
        margin = t + 0.3
        segs = [
            ("S", max(0, L - 2 * margin - sw_l)),
            ("E", max(0, W - 2 * margin - sw_w)),
            ("N", max(0, L - 2 * margin - sw_l)),
            ("W", max(0, W - 2 * margin - sw_w)),
        ]
        total = sum(s[1] for s in segs)
        if total <= 0:
            return [(margin, margin)] * count

        positions = []
        for i in range(count):
            d = total * (i + 0.5) / count
            acc = 0.0
            for side, seg_len in segs:
                if d <= acc + seg_len:
                    frac = d - acc
                    if side == "S":
                        pos = (margin + frac, margin)
                    elif side == "E":
                        pos = (L - margin - sw_l, margin + frac)
                    elif side == "N":
                        pos = (L - margin - sw_l - frac, W - margin - sw_w)
                    else:
                        pos = (margin, W - margin - sw_w - frac)
                    positions.append((round(pos[0], 2), round(pos[1], 2)))
                    break
                acc += seg_len
            else:
                positions.append((round(margin, 2), round(margin, 2)))
        return positions

    @staticmethod
    def _apply_stairwells(model, positions, p):
        if not positions:
            return
        sw_l, sw_w = p.get("stairwell_length", 4.0), p.get("stairwell_width", 3.0)
        for si, story in enumerate(model.stories):
            if si == 0:
                continue  # 1F 无楼板开洞
            for idx, (x, y) in enumerate(positions):
                story.floor_slab.openings.append(
                    dict(x=x, y=y, length=sw_l, width=sw_w, name=f"楼梯间{idx + 1}")
                )

    # ── 可燃物 ────────────────────────────────────

    @staticmethod
    def _place_combustibles_manual(model, p):
        selections = p.get("combustible_selections", {})
        if not selections:
            return
        method_idx = p.get("combustible_method", 0)
        method = list(DistributionMethod)[method_idx]
        target = p.get("combustible_floor", -1)  # -1 = 全部

        L, W, t = model.length, model.width, model.wall_thickness

        for si, story in enumerate(model.stories):
            if target >= 0 and si != target:
                continue
            for key, count in selections.items():
                if count <= 0 or key not in COMBUSTIBLE_LIBRARY:
                    continue
                story.combustibles.generate(
                    preset_key=key,
                    count=count,
                    method=method,
                    room_length=L,
                    room_width=W,
                    wall_thickness=t,
                )

    @staticmethod
    def _overlaps_hole(x, y, ol, ow, holes, margin=0.3):
        for h in holes:
            if not (
                x + ol <= h["x"] - margin
                or x >= h["x"] + h["length"] + margin
                or y + ow <= h["y"] - margin
                or y >= h["y"] + h["width"] + margin
            ):
                return True
        return False
