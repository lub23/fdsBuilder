#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : blueprint_ocr.py
@Author: Bo Lu
@Date  : 2026-01-28
@Version : 1.0
@Desc  : Building drawing OCR recognition module,
         used to extract building structure information from PDF drawings
'''

import os
import json
import base64
import requests
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional


OPENROUTER_API_KEY = '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'

# PDF转图片
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False


@dataclass
class WallData:
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float = 0.24
    height: float = 3.0


@dataclass 
class OpeningData:
    wall_index: int
    type: str  # door/window
    position: float  # 0-1沿墙位置
    width: float
    height: float
    z_bottom: float = 0.0


@dataclass
class BuildingData:
    length: float = 10.0
    width: float = 8.0
    height: float = 3.0
    walls: List[WallData] = field(default_factory=list)
    openings: List[OpeningData] = field(default_factory=list)
    rooms: List[dict] = field(default_factory=list)


PROMPT = """分析给定的建筑平面图，提取建筑外轮廓、所有主要内外墙体及门窗开口，忽略家具、设备与工艺布置，仅关注墙体几何与空间围护关系。
任何形成房间边界或功能分区的墙体均不得遗漏。
请按以下 JSON 结构返回结果，仅返回 JSON，不要输出说明文字：
```json
{
  "length": 外墙X方向总长度(米),
  "width": 外墙Y方向总宽度(米),
  "height": 层高(米，默认3.0),
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
      "wall_index": 所属墙体索引(从0开始),
      "type": "door" 或 "window",
      "position": 沿墙位置比例(0~1),
      "width": 开口宽度(米),
      "height": 开口高度(米),
      "z_bottom": 底部离地高度(米)
    }
  ]
}
```
约束要求：
坐标原点为建筑左下角 (0,0)，单位米
外墙必须为4 条封闭矩形墙体，顺序固定为 south → east → north → west
内墙必须逐一列出所有“围合或分隔空间”的墙体，禁止用“一整条长墙”替代多段实际存在的分隔墙；如墙体在拐点或门洞处中断，应拆分为多段墙体
在输出前请进行一次自检：确认每一个封闭房间的四周墙体均已在 walls 中出现
门窗需给出所属墙体、位置与尺寸；无明确标注时按常规建筑尺度合理估算"""


class BlueprintRecognizer:
    """图纸识别器"""
    
    def __init__(self, model: str = "bytedance-seed/seedream-4.5"):
        self.api_key = OPENROUTER_API_KEY
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.last_result: Optional[BuildingData] = None
    
    def image_to_base64(self, image_path: str) -> str:
        """图片转base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    
    def pdf_to_image(self, pdf_path: str, page: int = 0, dpi: int = 150) -> str:
        """PDF转图片，返回临时文件路径"""
        if not HAS_FITZ:
            raise ImportError("需要安装pymupdf: pip install pymupdf")
        
        doc = fitz.open(pdf_path)
        pix = doc[page].get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        temp_path = Path(pdf_path).stem + "_temp.png"
        pix.save(temp_path)
        doc.close()
        return temp_path
    
    def recognize(self, file_path: str) -> Optional[BuildingData]:
        """识别图纸"""
        if not self.api_key:
            raise ValueError("未设置OPENROUTER_API_KEY")
        
        # 处理PDF
        temp_file = None
        if file_path.lower().endswith('.pdf'):
            temp_file = self.pdf_to_image(file_path)
            image_path = temp_file
        else:
            image_path = file_path
        
        # 获取图片类型
        ext = Path(image_path).suffix.lower()
        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}
        mime_type = mime_map.get(ext, 'image/png')
        
        # 调用API
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
                timeout=60
            )
            
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # 提取JSON
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            data = json.loads(content)
            self.last_result = self._parse_result(data)
            return self.last_result
            
        finally:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
    
    def _parse_result(self, data: dict) -> BuildingData:
        """解析API返回结果"""
        building = BuildingData(
            length=data.get("length", 10.0),
            width=data.get("width", 8.0),
            height=data.get("height", 3.0)
        )
        
        for w in data.get("walls", []):
            building.walls.append(WallData(
                x1=w.get("x1", 0), y1=w.get("y1", 0),
                x2=w.get("x2", 0), y2=w.get("y2", 0),
                thickness=w.get("thickness", 0.24),
                height=building.height
            ))
        
        for o in data.get("openings", []):
            building.openings.append(OpeningData(
                wall_index=o.get("wall_index", 0),
                type=o.get("type", "door"),
                position=o.get("position", 0.5),
                width=o.get("width", 1.0),
                height=o.get("height", 2.0),
                z_bottom=o.get("z_bottom", 0)
            ))
        
        building.rooms = data.get("rooms", [])
        return building
    
    def to_model_dict(self) -> dict:
        """转换为主程序模型格式"""
        if not self.last_result:
            return {}
        
        b = self.last_result
        return {
            "length": b.length,
            "width": b.width,
            "height": b.height,
            "internal_walls": [asdict(w) for w in b.walls],
            "openings": [asdict(o) for o in b.openings],
            "rooms": b.rooms
        }


# 测试
if __name__ == "__main__":
    import sys
    
    api_key = OPENROUTER_API_KEY
    if not api_key:
        print("请设置环境变量 OPENROUTER_API_KEY")
        sys.exit(1)
    
    recognizer = BlueprintRecognizer(api_key)
    
    # 测试图片
    if len(sys.argv) > 1:
        result = recognizer.recognize(sys.argv[1])
        if result:
            print(json.dumps(recognizer.to_model_dict(), indent=2, ensure_ascii=False))
    else:
        print("用法: python blueprint_ocr.py <图纸文件>")