#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : viewer_3d.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : 3D viewer component for building model visualization
'''

# 3D可视化
try:
    import pyvista as pv
    from pyvistaqt import QtInteractor
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False
    print("警告: PyVista未安装，3D预览功能将受限")

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from models.building import BuildingModel
from models.materials import MATERIAL_LIBRARY


# ============================================================
# 3D可视化组件
# ============================================================
class Viewer3D(QWidget):
    """3D可视化查看器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.wall_actors = [] 
        self.opening_actors = []
        self.selected_wall = -1
        self.selected_opening = -1
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if HAS_PYVISTA:
            # 使用PyVista进行3D渲染
            self.plotter = QtInteractor(self)
            self.plotter.set_background('#1e1e2e')
            self.plotter.add_axes()
            layout.addWidget(self.plotter.interactor)
        else:
            # 回退到简单的提示
            label = QLabel("3D预览需要安装PyVista\npip install pyvista pyvistaqt")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-size: 16px; color: #a6adc8;")
            layout.addWidget(label)
    
    def update_model(self, model: BuildingModel):
        self.model = model
        self.wall_actors.clear()
        self.opening_actors.clear()
        
        if not HAS_PYVISTA or self.model is None:
            return
        
        self.plotter.clear()
        
        L, W, H = model.length, model.width, model.height
        t = model.wall_thickness
        
        wall_color = MATERIAL_LIBRARY.get(model.materials["walls"], {}).get("COLOR", "#808080")
        floor_color = MATERIAL_LIBRARY.get(model.materials["floor"], {}).get("COLOR", "#808080")
        roof_color = MATERIAL_LIBRARY.get(model.materials["roof"], {}).get("COLOR", "#808080")
        
        # 绘制所有墙体
        for i, wall in enumerate(model.walls):
            x1, y1 = wall["x1"] - L/2, wall["y1"] - W/2
            x2, y2 = wall["x2"] - L/2, wall["y2"] - W/2
            thick = wall.get("thickness", t)
            h = wall.get("height", H)
            is_ext = wall.get("is_external", False)
            color = wall_color if is_ext else '#6b7280'
            
            if abs(y2 - y1) < abs(x2 - x1):  # 水平墙（南北）
                # 水平墙延伸到外边缘
                box = pv.Box(bounds=(
                    min(x1, x2) - thick/2,  # 左端延伸
                    max(x1, x2) + thick/2,  # 右端延伸
                    min(y1, y2) - thick/2,
                    min(y1, y2) + thick/2,
                    0, h))
            else:  # 垂直墙（东西）
                # 垂直墙缩短，夹在水平墙之间
                box = pv.Box(bounds=(
                    min(x1, x2) - thick/2,
                    min(x1, x2) + thick/2,
                    min(y1, y2) + thick/2,  # 上端缩进
                    max(y1, y2) - thick/2,  # 下端缩进
                    0, h))
            
            actor = self.plotter.add_mesh(box, color=color, opacity=0.8, show_edges=True, edge_color='#45475a')
            self.wall_actors.append(actor)
        
        # 绘制开口
        for opening in model.openings:
            actor = self._add_opening(opening, model)
            self.opening_actors.append(actor)
        
        # 地板与屋顶
        floor = pv.Box(bounds=(-L/2 - t/2, L/2 + t/2, -W/2 - t/2, W/2 + t/2, -t, 0))
        self.plotter.add_mesh(floor, color=floor_color, opacity=0.9, show_edges=True, edge_color='#45475a')

        roof = pv.Box(bounds=(-L/2 - t/2, L/2 + t/2, -W/2 - t/2, W/2 + t/2, H, H + t))
        self.plotter.add_mesh(roof, color=roof_color, opacity=0.7, show_edges=True, edge_color='#45475a')
        
        # 热源
        if model.heat_source.get("enabled", False):
            self._add_heat_source(model, L, W, H)
        
        self.draw_combustibles(model.combustible_mgr)
        
        # ── 原点标记 ──
        self.draw_origin_marker()
        
        # ── 相机 ──
        self.cx, self.cy, self.cz = 0, 0, H / 2  # 原点在建筑中心
        self.max_dim = max(L, W, H)
        self.plotter.reset_camera()
        self.setup_camera()

    def draw_origin_marker(self):
        """在原点绘制坐标轴标记"""
        L = max(self.model.length, self.model.width) * 0.1
        # 三色轴线
        self.plotter.add_mesh(pv.Line((-self.model.length/2, -self.model.width/2, 0),
                                    (-self.model.length/2 + L, -self.model.width/2, 0)),
                            color='red', line_width=4)
        self.plotter.add_mesh(pv.Line((-self.model.length/2, -self.model.width/2, 0),
                                    (-self.model.length/2, -self.model.width/2 + L, 0)),
                            color='green', line_width=4)
        self.plotter.add_mesh(pv.Line((-self.model.length/2, -self.model.width/2, 0),
                                    (-self.model.length/2, -self.model.width/2, L)),
                            color='blue', line_width=4)
        # 原点球
        sphere = pv.Sphere(radius=L*0.05, center=(-self.model.length/2, -self.model.width/2, 0))
        self.plotter.add_mesh(sphere, color='white')

    def setup_camera(self):
        """上北下南左西右东"""
        d = self.max_dim * 2.5
        self.plotter.camera_position = [
            (0, -d, d * 0.6),
            (0, 0, self.model.height / 2),
            (0, 0, 1),
        ]
    
    def draw_combustibles(self, manager):
        """绘制可燃物"""
        if not manager.items:
            return
        L, W = self.model.length, self.model.width
        colors = {
            "BROWN": "#8B4513", "RED": "#CD5C5C", "SALMON": "#FA8072",
            "GRAY": "#A9A9A9", "KHAKI": "#BDB76B", "IVORY": "#FFFFF0",
            "MAGENTA": "#FF00FF", "ORANGE": "#FFA500",
        }

        for cb in manager.items:
            # 模型坐标(左下角原点) → 显示坐标(中心原点)
            x1 = cb.x - L/2
            x2 = cb.x + cb.length - L/2
            y1 = cb.y - W/2
            y2 = cb.y + cb.width - W/2
            box = pv.Box(bounds=(x1, x2, y1, y2, cb.z, cb.z + cb.height))
            color = colors.get(cb.color, "#CD853F")
            self.plotter.add_mesh(box, color=color, opacity=0.8)

    def _add_opening(self, opening, model):
        """添加开口显示"""
        wall_index = opening.get("wall_index", 0)
        if wall_index >= len(model.walls):
            return None
        
        wall = model.walls[wall_index]
        L, W, H = model.length, model.width, model.height
        
        wx1, wy1 = wall["x1"] - L/2, wall["y1"] - W/2
        wx2, wy2 = wall["x2"] - L/2, wall["y2"] - W/2
        thick = wall.get("thickness", model.wall_thickness)
        
        pos = opening.get("position", 0.5)
        o_width = opening["width"]
        o_height = opening["height"]
        z_bottom = opening.get("z_bottom", 0)
        o_type = opening.get("type", "door")
        
        color = "#38bdf8" if o_type == "window" else "#a6e3a1"
        
        cx = wx1 + (wx2 - wx1) * pos
        cy = wy1 + (wy2 - wy1) * pos
        
        is_horizontal = abs(wy2 - wy1) < abs(wx2 - wx1)
        
        if is_horizontal:
            box = pv.Box(bounds=(cx-o_width/2, cx+o_width/2, cy-thick/2-0.01, cy+thick/2+0.01, z_bottom, z_bottom+o_height))
        else:
            box = pv.Box(bounds=(cx-thick/2-0.01, cx+thick/2+0.01, cy-o_width/2, cy+o_width/2, z_bottom, z_bottom+o_height))
        
        return self.plotter.add_mesh(box, color=color, opacity=0.6)
    
    def highlight_wall(self, index: int):
        """高亮指定墙体"""
        if not HAS_PYVISTA:
            return
        
        # 重置所有墙体颜色
        for i, actor in enumerate(self.wall_actors):
            if actor is None:
                continue
            wall = self.model.walls[i]
            is_ext = wall.get("is_external", False)
            color = MATERIAL_LIBRARY.get(self.model.materials["walls"], {}).get("COLOR", "#808080") if is_ext else '#6b7280'
            actor.prop.color = color
            actor.prop.opacity = 0.8
        
        # 高亮选中的墙体
        if 0 <= index < len(self.wall_actors) and self.wall_actors[index]:
            self.wall_actors[index].prop.color = '#f97316'  # 橙色高亮
            self.wall_actors[index].prop.opacity = 1.0
        
        self.selected_wall = index
        self.plotter.render()
    
    def highlight_opening(self, index: int):
        """高亮指定开口"""
        if not HAS_PYVISTA:
            return
        
        # 重置所有开口颜色
        for i, actor in enumerate(self.opening_actors):
            if actor is None:
                continue
            o_type = self.model.openings[i].get("type", "door")
            color = "#38bdf8" if o_type == "window" else "#a6e3a1"
            actor.prop.color = color
            actor.prop.opacity = 0.6
        
        # 高亮选中的开口
        if 0 <= index < len(self.opening_actors) and self.opening_actors[index]:
            self.opening_actors[index].prop.color = '#f97316'
            self.opening_actors[index].prop.opacity = 1.0
        
        self.selected_opening = index
        self.plotter.render()


    def _add_heat_source(self, model, L, W, H):
        """添加热源显示"""
        hs = model.heat_source
        location = hs.get("location", "north")
        distance = hs.get("distance", 3.0)
        width_ratio = hs.get("width_ratio", 1.5)
        height_ratio = hs.get("height_ratio", 1.0)
        
        if location == "north":
            source_width = L * width_ratio
            source_height = H * height_ratio
            box = pv.Box(bounds=(-source_width/2, source_width/2, W/2+distance, W/2+distance+0.1, 0, source_height))
        elif location == "south":
            source_width = L * width_ratio
            source_height = H * height_ratio
            box = pv.Box(bounds=(-source_width/2, source_width/2, -W/2-distance-0.1, -W/2-distance, 0, source_height))
        elif location == "east":
            source_width = W * width_ratio
            source_height = H * height_ratio
            box = pv.Box(bounds=(L/2+distance, L/2+distance+0.1, -source_width/2, source_width/2, 0, source_height))
        else:
            source_width = W * width_ratio
            source_height = H * height_ratio
            box = pv.Box(bounds=(-L/2-distance-0.1, -L/2-distance, -source_width/2, source_width/2, 0, source_height))
        
        self.plotter.add_mesh(box, color='#f97316', opacity=0.5)
    
    def close(self):
        """关闭时清理资源"""
        if HAS_PYVISTA:
            self.plotter.close()
        super().close()
