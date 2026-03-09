#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : facility.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : Preset facility data management and equivalent model generation
'''

import json, os
from typing import List, Tuple, Dict, Any

from models.building import BuildingModel, Story, FloorSlab
from models.combustibles import CombustibleManager


class FacilityManager:

    def __init__(self):
        path = os.path.join(os.path.dirname(__file__), "industrial.json")
        with open(path, "r", encoding="utf-8") as f:
            self._data: Dict[str, Any] = json.load(f)

    # ── 查询 ─────────────────────────────────────

    def categories(self) -> List[Tuple[str, str]]:
        return [(k, v["cn_name"]) for k, v in self._data.items()]

    def sub_types(self, cat: str) -> List[Tuple[str, str]]:
        subs = self._data.get(cat, {}).get("sub_types", {})
        return [(k, v["cn_name"]) for k, v in subs.items()]

    def facility(self, cat: str, sub: str) -> dict:
        return self._data[cat]["sub_types"][sub]

    # ── 默认值解析 ────────────────────────────────

    @staticmethod
    def _rv(p) -> float:
        """median>0 → median，否则 (min+max)/2"""
        if not isinstance(p, dict):
            return float(p)
        med = p.get("median", -1)
        if med is not None and med > 0:
            return float(med)
        return round((p.get("min", 0) + p.get("max", 0)) / 2, 2)

    def default_params(self, cat: str, sub: str) -> dict:
        f = self.facility(cat, sub)
        b = f["building"]
        d = f.get("doors", {})
        w = f.get("windows", {})
        _r = self._rv
        return dict(
            name=f.get("cn_name", sub),
            length=_r(b["length"]),
            width=_r(b["width"]),
            height=_r(b["height"]),
            stories=max(1, int(_r(b.get("stories", {"min": 1, "max": 1})))),
            wall_thickness=f.get("wall_thickness", 0.24),
            door_width=_r(d.get("width", {"min": 1.2, "max": 1.5})),
            door_height=_r(d.get("height", {"min": 2.1, "max": 2.4})),
            door_count=max(0, int(_r(d.get("count", {"min": 0, "max": 0})))),
            window_width=_r(w.get("width", {"min": 1.5, "max": 2})),
            window_height=_r(w.get("height", {"min": 1.5, "max": 2})),
            window_count=max(0, int(_r(w.get("count", {"min": 0, "max": 0})))),
        )

    # ── 模型生成 ──────────────────────────────────

    def generate_model(self, p: dict) -> BuildingModel:
        n_st = max(1, p["stories"])
        st_h = round(p["height"] / n_st, 2)
        L, W, t = p["length"], p["width"], p["wall_thickness"]

        model = BuildingModel()
        model.chid = "facility"
        model.length, model.width, model.wall_thickness = L, W, t
        model.stories = [
            Story(
                name=f"{i + 1}F", height=st_h,
                walls=[], openings=[],
                combustibles=CombustibleManager(),
                floor_slab=FloorSlab(),
            )
            for i in range(n_st)
        ]
        model.update_z_offsets()
        model.update_external_walls()

        self._place_doors(model, p)
        self._place_windows(model, p)
        return model

    # ── 门（首层南墙均匀分布）──

    @staticmethod
    def _place_doors(model: BuildingModel, p: dict):
        cnt = p["door_count"]
        if cnt <= 0:
            return
        story = model.stories[0]
        dw = min(p["door_width"], model.length * 0.8 / max(cnt, 1))
        dh = min(p["door_height"], story.height - 0.01)
        if dh <= 0:
            return
        for i in range(cnt):
            story.openings.append(dict(
                wall_index=0, type="door",
                position=round((i + 1) / (cnt + 1), 4),
                width=round(dw, 2), height=round(dh, 2),
                z_bottom=0.0,
            ))

    # ── 窗（各层按周长比例分配到 4 面外墙）──

    @staticmethod
    def _place_windows(model: BuildingModel, p: dict):
        total = p["window_count"]
        if total <= 0:
            return
        L, W = model.length, model.width
        ww_raw, wh_raw = p["window_width"], p["window_height"]
        n_fl = len(model.stories)
        base, extra = divmod(total, n_fl)

        for si, story in enumerate(model.stories):
            nf = base + (1 if si < extra else 0)  # 本层窗总数
            if nf <= 0:
                continue

            wh = min(wh_raw, story.height - 0.3)
            if wh < 0.3:
                continue
            z_bot = max(0.9, (story.height - wh) / 2)
            z_bot = min(z_bot, story.height - wh - 0.05)
            z_bot = max(0.05, z_bot)

            # 按墙长比例分配：S(0) N(1) E(2) W(3)
            wall_lens = [L, L, W, W]
            perim = sum(wall_lens)
            raw = [nf * wl / perim for wl in wall_lens]
            counts = [int(r) for r in raw]
            rem = nf - sum(counts)
            order = sorted(range(4), key=lambda i: raw[i] - counts[i], reverse=True)
            for k in range(rem):
                counts[order[k]] += 1

            for wi in range(4):
                nw = counts[wi]
                if nw <= 0:
                    continue
                wl = wall_lens[wi]
                max_fit = max(1, int(wl / (ww_raw + 0.5)))
                nw = min(nw, max_fit)
                ww = min(ww_raw, wl * 0.4)
                for j in range(nw):
                    story.openings.append(dict(
                        wall_index=wi, type="window",
                        position=round((j + 1) / (nw + 1), 4),
                        width=round(ww, 2), height=round(wh, 2),
                        z_bottom=round(z_bot, 2),
                    ))