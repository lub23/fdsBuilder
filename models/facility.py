#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : facility.py
@Author: Lubber
@Date  : 2026-03-09
@Version : 1.0
@Desc  : Preset facility data management and equivalent model generation
'''

import json, os
from typing import List, Tuple, Dict, Any

from models.building import BuildingModel, Story, FloorSlab
from models.combustibles import (
    CombustibleManager, DistributionMethod
)
from models.materials import COMBUSTIBLE_LIBRARY

WALL_NAMES = ["南墙", "北墙", "东墙", "西墙", "均匀分布"]


class FacilityManager:

    def __init__(self):
        path = os.path.join(os.path.dirname(__file__), "industrial.json")
        with open(path, "r", encoding="utf-8") as f:
            self._data: Dict[str, Any] = json.load(f)

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
            ("length", b["length"]), ("width", b["width"]),
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

        return dict(
            cat_key=cat, sub_key=sub,
            cat_name=self._data[cat]["cn_name"],
            name=f.get("cn_name", sub),
            description=f.get("description", ""),
            facility_combustibles=f.get("combustibles", []),
            length=_r(b["length"]), width=_r(b["width"]),
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
            window_sill=0.9,
            stairwell_count=0,
            stairwell_length=4.0,
            stairwell_width=3.0,
            combustible_selections={},
            combustible_method=0,
            combustible_floor=-1,
            ranges=rng,
        )

    # ══════════════════════════════════════════════
    #  模型生成
    # ══════════════════════════════════════════════

    def generate_model(self, p: dict) -> BuildingModel:
        n_st = max(1, p["stories"])
        st_h = round(p["height"] / n_st, 2)
        L, W, t = p["length"], p["width"], p["wall_thickness"]

        model = BuildingModel()
        model.chid = f'{p.get("cat_key", "fac")}-{p.get("sub_key", "unit")}'
        model.length, model.width, model.wall_thickness = L, W, t
        model.stories = [
            Story(name=f"{i+1}F", height=st_h, walls=[], openings=[],
                  combustibles=CombustibleManager(), floor_slab=FloorSlab())
            for i in range(n_st)
        ]
        model.update_z_offsets()
        model.update_external_walls()

        # 门窗
        self._place_openings(model, p, "door")
        self._place_openings(model, p, "window")
        self._resolve_overlaps(model)

        # 楼梯口
        sw_pos = self._calc_stairwell_positions(
            L, W, t,
            p.get("stairwell_count", 0),
            p.get("stairwell_length", 4.0),
            p.get("stairwell_width", 3.0),
        )
        self._apply_stairwells(model, sw_pos, p)

        # 可燃物
        self._place_combustibles(model, p, sw_pos)
        return model

    # ── 门窗放置 ──────────────────────────────────

    @staticmethod
    def _place_openings(model, p, kind):
        cnt = p.get(f"{kind}_count", 0)
        if cnt <= 0:
            return
        ow, oh = p[f"{kind}_width"], p[f"{kind}_height"]
        wall_mode = p.get(f"{kind}_wall", 4)
        sill_ratio = p.get("window_sill", 0.3)
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
                FacilityManager._add_to_wall(story, wall_mode, nf, ow, h, zb, kind, L, W)
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
                            story, wi, counts[wi], ow, h, zb, kind, L, W)

    @staticmethod
    def _add_to_wall(story, wi, count, ow, oh, z_bot, kind, L, W):
        wall_len = L if wi <= 1 else W
        max_fit = max(1, int(wall_len / (ow + 0.3)))
        count = min(count, max_fit)
        w = min(ow, wall_len * 0.8 / max(count, 1))
        for j in range(count):
            story.openings.append(dict(
                wall_index=wi, type=kind,
                position=round((j + 1) / (count + 1), 4),
                width=round(w, 2), height=round(oh, 2),
                z_bottom=round(z_bot, 2),
            ))

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
                continue          # 1F 无楼板开洞
            for idx, (x, y) in enumerate(positions):
                story.floor_slab.openings.append(
                    dict(x=x, y=y, length=sw_l, width=sw_w,
                         name=f"楼梯间{idx + 1}"))

    # ── 可燃物 ────────────────────────────────────

    @staticmethod
    def _place_combustibles(model, p, sw_positions):
        selections = p.get("combustible_selections", {})
        if not selections:
            return
        method_idx = p.get("combustible_method", 0)
        method = list(DistributionMethod)[method_idx]
        target = p.get("combustible_floor", -1)      # -1 = 全部

        L, W, t = model.length, model.width, model.wall_thickness
        sw_l = p.get("stairwell_length", 4.0)
        sw_w = p.get("stairwell_width", 3.0)
        holes = [dict(x=x, y=y, length=sw_l, width=sw_w) for x, y in sw_positions]

        for si, story in enumerate(model.stories):
            if target >= 0 and si != target:
                continue
            for key, count in selections.items():
                if count <= 0 or key not in COMBUSTIBLE_LIBRARY:
                    continue
                request = count + len(holes) * 3 + 5 if holes else count
                new_items = story.combustibles.generate(
                    preset_key=key, count=request, method=method,
                    room_length=L, room_width=W, wall_thickness=t)

                # 过滤楼梯口区域
                keep, drop = [], []
                for cb in new_items:
                    (drop if FacilityManager._overlaps_hole(
                        cb.x, cb.y, cb.length, cb.width, holes)
                     else keep).append(cb)
                for cb in drop:
                    story.combustibles.items.remove(cb)
                # 裁剪到目标数量
                for cb in keep[count:]:
                    story.combustibles.items.remove(cb)

    @staticmethod
    def _overlaps_hole(x, y, ol, ow, holes, margin=0.3):
        for h in holes:
            if not (x + ol <= h["x"] - margin or x >= h["x"] + h["length"] + margin or
                    y + ow <= h["y"] - margin or y >= h["y"] + h["width"] + margin):
                return True
        return False