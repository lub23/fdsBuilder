#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : blueprint_ocr.py
@Author: Lubber
@Date  : 2026-03-05
@Version : 1.0
@Desc  : Building drawing OCR recognition module,
         used to extract building structure information from PDF drawings
'''

import os
import json
import base64
import requests
from pathlib import Path
from typing import Optional, Dict, List

# PDF转图片
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


PROMPT = PROMPT = """分析给定的建筑平面图，提取建筑信息。图纸可能包含多层平面，请逐层识别。
忽略家具、设备与工艺布置，仅关注墙体几何、门窗开口与楼板开洞（如楼梯间）。

请按以下 JSON 结构返回结果，仅返回 JSON，不要输出说明文字：
```json
{
  "length": 外墙X方向总长度(米),
  "width": 外墙Y方向总宽度(米),
  "wall_thickness": 外墙厚度(米,默认0.24),
  "stories": [
    {
      "name": "1F",
      "height": 该层层高(米),
      "walls": [
        {
          "x1": 起点x, "y1": 起点y,
          "x2": 终点x, "y2": 终点y,
          "thickness": 墙厚(默认0.24),
          "is_external": 是否外墙(true/false),
          "name": 墙体名称
        }
      ],
      "openings": [
        {
          "wall_index": 所属墙体索引(从0开始,对应本层walls数组),
          "type": "door" 或 "window",
          "position": 沿墙位置比例(0~1),
          "width": 开口宽度(米),
          "height": 开口高度(米),
          "z_bottom": 底部离地高度(米)
        }
      ],
      "floor_slab": {
        "thickness": 楼板厚度(默认0.2),
        "openings": [
          {
            "x": 左下角x坐标, "y": 左下角y坐标,
            "length": X方向长度, "width": Y方向宽度,
            "name": "楼梯间"
          }
        ]
      }
    }
  ]
}
约束要求：

坐标原点为建筑左下角 (0,0)，单位米
每层的外墙必须为4条封闭矩形墙体(南→北→西→东)，is_external=true
内墙逐一列出所有围合或分隔空间的墙体，is_external=false；如墙体在拐点或门洞处中断，应拆分为多段
若图纸仅有一层，stories数组只含一个元素
若图纸有多层，按从低到高顺序排列(1F, 2F, ...)，每层独立给出walls和openings
楼梯间、电梯井等上下层连通的区域，在对应层的floor_slab.openings中标注
首层(1F)的floor_slab.openings通常为空
门窗的wall_index是相对于本层walls数组的索引
在输出前请自检：确认每个封闭房间的四周墙体均已出现"""

class BlueprintRecognizer:
    """图纸识别器 — 输出与BuildingModel兼容的dict"""

    def __init__(self, api_key: str, model: str = "mistralai/mistral-small-3.1-24b-instruct:free"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.last_raw: Optional[dict] = None

    def image_to_base64(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    def pdf_to_image(self, pdf_path: str, page: int = 0, dpi: int = 150) -> str:
        if not HAS_FITZ:
            raise ImportError("需要安装 pymupdf: pip install pymupdf")
        doc = fitz.open(pdf_path)
        pix = doc[page].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        temp_path = str(Path(pdf_path).with_suffix('.tmp.png'))
        pix.save(temp_path)
        doc.close()
        return temp_path

    def recognize(self, file_path: str) -> Optional[dict]:
        """
        识别图纸，返回BuildingModel兼容的dict：
        {
            "length", "width", "wall_thickness",
            "stories": [{"name":"1F", "height", "walls":[], "openings":[], ...}],
            ...
        }
        """
        if not self.api_key:
            raise ValueError("未设置API Key")

        # 处理PDF
        temp_file = None
        if file_path.lower().endswith('.pdf'):
            temp_file = self.pdf_to_image(file_path)
            image_path = temp_file
        else:
            image_path = file_path

        ext = Path(image_path).suffix.lower()
        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}
        mime_type = mime_map.get(ext, 'image/png')

        try:
            img_b64 = self.image_to_base64(image_path)

            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROMPT},
                            {"type": "image_url", "image_url": {
                                "url": f"data:{mime_type};base64,{img_b64}"
                            }}
                        ]
                    }]
                },
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            print("API原始返回:", result)  # 调试用
            content = result["choices"][0]["message"]["content"]

            # 提取JSON
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            raw = json.loads(content)
            self.last_raw = raw
            return self._to_model_dict(raw)

        finally:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)

    def _to_model_dict(self, raw: dict) -> dict:
        """将API返回的原始dict转换为BuildingModel.from_dict兼容格式"""
        length = raw.get("length", 10.0)
        width = raw.get("width", 8.0)
        wall_thickness = raw.get("wall_thickness", 0.24)

        stories = []
        raw_stories = raw.get("stories", [])

        if not raw_stories:
            # 兼容旧格式：无stories时构建单层
            stories.append(self._build_single_story(raw, length, width, wall_thickness))
        else:
            for rs in raw_stories:
                story = self._parse_story(rs, wall_thickness)
                stories.append(story)

        return {
            "chid": "building",
            "length": length,
            "width": width,
            "wall_thickness": wall_thickness,
            "stories": stories,
            "roof": {"thickness": 0.2, "material": "CONCRETE"},
            "materials": {"walls": "CONCRETE", "floor": "CONCRETE", "roof": "CONCRETE"},
            "heat_source": {"enabled": False},
            "simulation_time": 60,
            "domain": {"padding": 5.0, "mesh_cells": [80, 60, 40]},
            "output": {"slices": True, "devices": True},
        }

    def _parse_story(self, rs: dict, default_thick: float) -> dict:
        """解析单层数据"""
        height = rs.get("height", 3.0)

        # 分离内墙（外墙由模型自动生成）
        internal_walls = []
        for w in rs.get("walls", []):
            if not w.get("is_external", False):
                internal_walls.append({
                    "x1": w.get("x1", 0), "y1": w.get("y1", 0),
                    "x2": w.get("x2", 0), "y2": w.get("y2", 0),
                    "thickness": w.get("thickness", default_thick),
                    "height": height,
                    "is_external": False,
                    "name": w.get("name", ""),
                })

        openings = []
        raw_walls = rs.get("walls", [])
        # 需要重映射wall_index：去掉外墙后索引变了
        ext_indices = {i for i, w in enumerate(raw_walls) if w.get("is_external", False)}
        # 构建旧索引→新索引映射（外墙会被自动生成4面，排在前面）
        # 外墙索引映射到自动生成的0-3，内墙映射到4+
        old_to_new = {}
        ext_order = {"南": 0, "北": 1, "西": 2, "东": 3}
        ext_count = 0
        int_count = 0
        for i, w in enumerate(raw_walls):
            if w.get("is_external", False):
                # 尝试根据名称映射
                name = w.get("name", "")
                mapped = None
                for key, idx in ext_order.items():
                    if key in name:
                        mapped = idx
                        break
                if mapped is None:
                    mapped = ext_count
                old_to_new[i] = min(mapped, 3)
                ext_count += 1
            else:
                old_to_new[i] = 4 + int_count  # 4面外墙之后
                int_count += 1

        for o in rs.get("openings", []):
            old_idx = o.get("wall_index", 0)
            new_idx = old_to_new.get(old_idx, old_idx)
            openings.append({
                "wall_index": new_idx,
                "type": o.get("type", "door"),
                "position": o.get("position", 0.5),
                "width": o.get("width", 1.0),
                "height": o.get("height", 2.0),
                "z_bottom": o.get("z_bottom", 0.0),
            })

        # 楼板
        floor_slab_raw = rs.get("floor_slab", {})
        floor_slab = {
            "thickness": floor_slab_raw.get("thickness", 0.2),
            "material": floor_slab_raw.get("material", "CONCRETE"),
            "openings": floor_slab_raw.get("openings", []),
        }

        return {
            "name": rs.get("name", "1F"),
            "height": height,
            "walls": internal_walls,
            "openings": openings,
            "combustibles": [],
            "floor_slab": floor_slab,
        }

    def _build_single_story(self, raw: dict, length: float, width: float, thick: float) -> dict:
        """兼容旧格式：无stories字段时构建单层"""
        return self._parse_story({
            "name": "1F",
            "height": raw.get("height", 3.0),
            "walls": raw.get("walls", []),
            "openings": raw.get("openings", []),
            "floor_slab": {"thickness": 0.2, "openings": []},
        }, thick)

    def get_summary(self) -> str:
        if not self.last_raw:
            return "无识别结果"
        r = self.last_raw
        n_stories = len(r.get("stories", []))
        total_walls = 0
        total_openings = 0
        total_holes = 0
        for s in r.get("stories", []):
            walls = s.get("walls", [])
            total_walls += sum(1 for w in walls if not w.get("is_external"))
            total_openings += len(s.get("openings", []))
            total_holes += len(s.get("floor_slab", {}).get("openings", []))
        return (f"尺寸: {r.get('length', '?')}×{r.get('width', '?')}m\n"
                f"楼层: {n_stories}层 | 内墙: {total_walls}面\n"
                f"开口: {total_openings}个 | 楼板开洞: {total_holes}个")