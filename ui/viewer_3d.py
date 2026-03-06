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
        self.visible_stories = None  # None = 全部显示
        self.max_dim = 10
        self.cx = self.cy = self.cz = 0
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if HAS_PYVISTA:
            self.plotter = QtInteractor(self)
            self.plotter.set_background('#1e1e2e')
            self.plotter.add_axes()
            layout.addWidget(self.plotter.interactor)
        else:
            label = QLabel("3D预览需要安装PyVista\npip install pyvista pyvistaqt")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-size: 16px; color: #a6adc8;")
            layout.addWidget(label)

    def update_model(self, model: BuildingModel):
        self.model = model
        self.wall_actors.clear()
        self.opening_actors.clear()

        if not HAS_PYVISTA or model is None:
            return

        self.plotter.clear()

        L, W = model.length, model.width
        t = model.wall_thickness

        wall_color = MATERIAL_LIBRARY.get(
            model.materials["walls"], {}).get("COLOR", "#808080")
        floor_color = MATERIAL_LIBRARY.get(
            model.materials["floor"], {}).get("COLOR", "#808080")
        roof_color = MATERIAL_LIBRARY.get(
            model.materials["roof"], {}).get("COLOR", "#808080")

        for si, story in enumerate(model.stories):
            # 层可见性
            if self.visible_stories is not None and si not in self.visible_stories:
                continue

            z0 = story.z_bottom
            h = story.height
            slab_t = story.floor_slab.thickness

            # ── 楼板 ──
            floor_mesh = pv.Box(bounds=(
                -L/2 - t/2, L/2 + t/2,
                -W/2 - t/2, W/2 + t/2,
                z0 - slab_t, z0))

            for hole in story.floor_slab.openings:
                hx = hole["x"] - L/2
                hy = hole["y"] - W/2
                hole_box = pv.Box(bounds=(
                    hx, hx + hole["length"],
                    hy, hy + hole["width"],
                    z0 - slab_t - 0.01, z0 + 0.01))
                try:
                    floor_mesh = floor_mesh.boolean_difference(hole_box)
                except:
                    pass

            self.plotter.add_mesh(
                floor_mesh, color=floor_color, opacity=0.9,
                show_edges=True, edge_color='#45475a')

            # ── 墙体 ──
            for wall in story.walls:
                x1, y1 = wall["x1"] - L/2, wall["y1"] - W/2
                x2, y2 = wall["x2"] - L/2, wall["y2"] - W/2
                thick = wall.get("thickness", t)
                is_ext = wall.get("is_external", False)
                color = wall_color if is_ext else '#6b7280'

                if abs(y2 - y1) < abs(x2 - x1):  # 水平墙
                    box = pv.Box(bounds=(
                        min(x1, x2) - thick/2, max(x1, x2) + thick/2,
                        min(y1, y2) - thick/2, min(y1, y2) + thick/2,
                        z0, z0 + h))
                else:  # 垂直墙
                    box = pv.Box(bounds=(
                        min(x1, x2) - thick/2, min(x1, x2) + thick/2,
                        min(y1, y2) + thick/2, max(y1, y2) - thick/2,
                        z0, z0 + h))

                actor = self.plotter.add_mesh(
                    box, color=color, opacity=0.8,
                    show_edges=True, edge_color='#45475a')
                self.wall_actors.append((si, actor))

            # ── 开口 ──
            for opening in story.openings:
                actor = self._add_opening(opening, story, L, W, t, z0)
                if actor:
                    self.opening_actors.append((si, actor))

            # ── 可燃物 ──
            self.draw_combustibles(story.combustibles, z0, L, W)

        # ── 屋顶 ──
        total_h = model.total_height
        roof_t = model.roof.get("thickness", 0.2)
        roof = pv.Box(bounds=(
            -L/2 - t/2, L/2 + t/2,
            -W/2 - t/2, W/2 + t/2,
            total_h, total_h + roof_t))
        self.plotter.add_mesh(
            roof, color=roof_color, opacity=0.7,
            show_edges=True, edge_color='#45475a')

        # ── 热源 ──
        if model.heat_source.get("enabled", False):
            self._add_heat_source(model, L, W, total_h)

        # ── 原点 + 相机 ──
        self.draw_origin_marker()
        self.max_dim = max(L, W, total_h)
        self.cx, self.cy, self.cz = 0, 0, total_h / 2
        self.plotter.reset_camera()
        self.setup_camera()

    def _add_opening(self, opening, story, L, W, t, z0):
        """添加开口显示（多层适配）"""
        wall_index = opening.get("wall_index", 0)
        if wall_index >= len(story.walls):
            return None

        wall = story.walls[wall_index]
        wx1, wy1 = wall["x1"] - L/2, wall["y1"] - W/2
        wx2, wy2 = wall["x2"] - L/2, wall["y2"] - W/2
        thick = wall.get("thickness", t)

        pos = opening.get("position", 0.5)
        o_width = opening["width"]
        o_height = opening["height"]
        z_bottom = z0 + opening.get("z_bottom", 0)  # 加层偏移
        o_type = opening.get("type", "door")

        color = "#38bdf8" if o_type == "window" else "#a6e3a1"

        cx = wx1 + (wx2 - wx1) * pos
        cy = wy1 + (wy2 - wy1) * pos
        is_horizontal = abs(wy2 - wy1) < abs(wx2 - wx1)

        if is_horizontal:
            box = pv.Box(bounds=(
                cx - o_width/2, cx + o_width/2,
                cy - thick/2 - 0.01, cy + thick/2 + 0.01,
                z_bottom, z_bottom + o_height))
        else:
            box = pv.Box(bounds=(
                cx - thick/2 - 0.01, cx + thick/2 + 0.01,
                cy - o_width/2, cy + o_width/2,
                z_bottom, z_bottom + o_height))

        return self.plotter.add_mesh(box, color=color, opacity=0.6)

    def draw_combustibles(self, manager, z_offset=0, L=0, W=0):
        if not manager.items:
            return
        colors = {
            "BROWN": "#8B4513", "RED": "#CD5C5C", "SALMON": "#FA8072",
            "GRAY": "#808080", "KHAKI": "#BDB76B", "IVORY": "#FFFFF0",
            "MAGENTA": "#FF00FF", "ORANGE": "#FFA500",
        }
        for cb in manager.items:
            box = pv.Box(bounds=(
                cb.x - L/2, cb.x + cb.length - L/2,
                cb.y - W/2, cb.y + cb.width - W/2,
                cb.z + z_offset, cb.z + cb.height + z_offset))
            self.plotter.add_mesh(
                box, color=colors.get(cb.color, "#CD853F"), opacity=0.8)

    def draw_origin_marker(self):
        a = max(self.model.length, self.model.width) * 0.1
        ox, oy = -self.model.length/2, -self.model.width/2
        self.plotter.add_mesh(
            pv.Line((ox, oy, 0), (ox + a, oy, 0)), color='red', line_width=4)
        self.plotter.add_mesh(
            pv.Line((ox, oy, 0), (ox, oy + a, 0)), color='green', line_width=4)
        self.plotter.add_mesh(
            pv.Line((ox, oy, 0), (ox, oy, a)), color='blue', line_width=4)
        self.plotter.add_mesh(
            pv.Sphere(radius=a * 0.05, center=(ox, oy, 0)), color='white')

    def setup_camera(self):
        d = self.max_dim * 2.5
        self.plotter.camera_position = [
            (0, -d, d * 0.6),
            (0, 0, self.cz),
            (0, 0, 1),
        ]

    def highlight_wall(self, index: int):
        if not HAS_PYVISTA:
            return
        for i, (si, actor) in enumerate(self.wall_actors):
            if actor is None:
                continue
            # 找对应层的墙
            story = self.model.stories[si]
            wall_in_story = i - sum(
                1 for s, _ in self.wall_actors[:i] if s == si and False
            )
            is_ext = True  # 默认
            color = MATERIAL_LIBRARY.get(
                self.model.materials["walls"], {}).get("COLOR", "#808080")
            actor.prop.color = color
            actor.prop.opacity = 0.8

        if 0 <= index < len(self.wall_actors):
            _, actor = self.wall_actors[index]
            if actor:
                actor.prop.color = '#f97316'
                actor.prop.opacity = 1.0

        self.selected_wall = index
        self.plotter.render()

    def highlight_opening(self, index: int):
        if not HAS_PYVISTA:
            return
        for _, actor in self.opening_actors:
            if actor:
                actor.prop.color = '#a6e3a1'
                actor.prop.opacity = 0.6

        if 0 <= index < len(self.opening_actors):
            _, actor = self.opening_actors[index]
            if actor:
                actor.prop.color = '#f97316'
                actor.prop.opacity = 1.0

        self.selected_opening = index
        self.plotter.render()

    def _add_heat_source(self, model, L, W, H):
        hs = model.heat_source
        loc = hs.get("location", "north")
        dist = hs.get("distance", 3.0)
        wr = hs.get("width_ratio", 1.5)
        hr = hs.get("height_ratio", 1.0)

        if loc == "north":
            sw, sh = L * wr, H * hr
            b = (-sw/2, sw/2, W/2+dist, W/2+dist+0.1, 0, sh)
        elif loc == "south":
            sw, sh = L * wr, H * hr
            b = (-sw/2, sw/2, -W/2-dist-0.1, -W/2-dist, 0, sh)
        elif loc == "east":
            sw, sh = W * wr, H * hr
            b = (L/2+dist, L/2+dist+0.1, -sw/2, sw/2, 0, sh)
        else:
            sw, sh = W * wr, H * hr
            b = (-L/2-dist-0.1, -L/2-dist, -sw/2, sw/2, 0, sh)

        self.plotter.add_mesh(pv.Box(bounds=b), color='#f97316', opacity=0.5)

    def close(self):
        if HAS_PYVISTA:
            self.plotter.close()
        super().close()