#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : viewer_3d.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : 3D viewer component for building model visualization
'''

import math
# 3D可视化
try:
    import pyvista as pv
    from pyvistaqt import QtInteractor
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False
    print("警告: PyVista未安装，3D预览功能将受限")

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
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
        self.show_roof = True
        self._first_render = True
        self._highlighted_building = -1  # index of highlighted building

        self._actor_registry = {}  # {(category, id): actor}
        self._debounce_timer = None
        self._pending_update = False
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
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._execute_pending_update)

    def _schedule_debounced_update(self):
        """Schedule a debounced update for slider拖拽"""
        if self._debounce_timer.isActive():
            self._debounce_timer.stop()
        self._debounce_timer.start(500)

    def _execute_pending_update(self):
        """Execute the pending update after debounce"""
        if self._pending_update and self.model:
            self._do_full_render()
        self._pending_update = False

    def update_model(self, model: BuildingModel, debounce=False):
        self.model = model

        if not HAS_PYVISTA or model is None:
            return
        if debounce:
            self._pending_update = True
            self._schedule_debounced_update()
        else:
            self._do_full_render()

    def _do_full_render(self):
        """Perform full render (original logic)"""
        self.wall_actors.clear()
        self.opening_actors.clear()
        self.plotter.clear()

        # Render all buildings in the group
        buildings = self.model.building_group.buildings
        global_max_x = global_max_y = global_max_z = -float("inf")
        global_min_x = global_min_y = float("inf")

        for bi, building in enumerate(buildings):
            L, W = building.length, building.width
            t = building.wall_thickness
            total_h = building.total_height
            x_off = building.x_offset
            y_off = building.y_offset
            wall_color = MATERIAL_LIBRARY.get(building.materials["walls"], {}).get(
                "COLOR", "#808080"
            )
            floor_color = MATERIAL_LIBRARY.get(building.materials["floor"], {}).get(
                "COLOR", "#808080"
            )
            roof_color = MATERIAL_LIBRARY.get(building.materials["roof"], {}).get(
                "COLOR", "#808080"
            )
            is_highlighted = bi == self._highlighted_building
            wall_opacity = 1.0 if is_highlighted else 0.8
            edge_color = "#f97316" if is_highlighted else "#45475a"
            edge_width = 3 if is_highlighted else 1
            # Track bounding box
            global_min_x = min(global_min_x, x_off - L / 2 - t / 2)
            global_max_x = max(global_max_x, x_off + L / 2 + t / 2)
            global_min_y = min(global_min_y, y_off - W / 2 - t / 2)
            global_max_y = max(global_max_y, y_off + W / 2 + t / 2)
            global_max_z = max(global_max_z, total_h)
            for si, story in enumerate(building.stories):
                if self.visible_stories is not None and si not in self.visible_stories:
                    continue

                z0 = story.z_bottom
                h = story.height
                slab_t = story.floor_slab.thickness

                # Floor slab
                floor_mesh = pv.Box(
                    bounds=(
                        x_off - L / 2 - t / 2,
                        x_off + L / 2 + t / 2,
                        y_off - W / 2 - t / 2,
                        y_off + W / 2 + t / 2,
                        z0 - slab_t,
                        z0,
                    )
                )
                self.plotter.add_mesh(
                    floor_mesh,
                    color=floor_color,
                    opacity=0.7,
                    show_edges=True,
                    edge_color="#45475a",
                )
                for hole in story.floor_slab.openings:
                    hx = hole["x"] - L / 2 + x_off
                    hy = hole["y"] - W / 2 + y_off
                    hole_box = pv.Box(
                        bounds=(
                            hx,
                            hx + hole["length"],
                            hy,
                            hy + hole["width"],
                            z0 - slab_t + 0.01,
                            z0 - 0.01,
                        )
                    )
                    self.plotter.add_mesh(
                        hole_box,
                        color="#1e1e2e",
                        opacity=0.9,
                        show_edges=True,
                        edge_color="#f38ba8",
                        line_width=2,
                    )

                # Walls
                for wall in story.walls:
                    x1, y1 = wall["x1"] - L / 2 + x_off, wall["y1"] - W / 2 + y_off
                    x2, y2 = wall["x2"] - L / 2 + x_off, wall["y2"] - W / 2 + y_off
                    thick = wall.get("thickness", t)
                    is_ext = wall.get("is_external", False)
                    color = wall_color if is_ext else "#6b7280"
                    if abs(y2 - y1) < abs(x2 - x1):  # horizontal wall
                        box = pv.Box(
                            bounds=(
                                min(x1, x2) - thick / 2,
                                max(x1, x2) + thick / 2,
                                min(y1, y2) - thick / 2,
                                min(y1, y2) + thick / 2,
                                z0,
                                z0 + h,
                            )
                        )
                    else:  # vertical wall
                        box = pv.Box(
                            bounds=(
                                min(x1, x2) - thick / 2,
                                min(x1, x2) + thick / 2,
                                min(y1, y2) + thick / 2,
                                max(y1, y2) - thick / 2,
                                z0,
                                z0 + h,
                            )
                        )
                    actor = self.plotter.add_mesh(
                        box,
                        color=color,
                        opacity=wall_opacity,
                        show_edges=True,
                        edge_color=edge_color,
                        line_width=edge_width,
                    )
                    self.wall_actors.append((si, actor))
                # Openings
                for opening in story.openings:
                    actor = self._add_opening(opening, story, L, W, t, z0, x_off, y_off)
                    if actor:
                        self.opening_actors.append((si, actor))
                # Combustibles
                self._draw_combustibles_offset(
                    story.combustibles, z0, L, W, x_off, y_off
                )

            # Roof
            if self.show_roof:
                roof_t = building.roof.get("thickness", 0.2)
                roof = pv.Box(
                    bounds=(
                        x_off - L / 2 - t / 2,
                        x_off + L / 2 + t / 2,
                        y_off - W / 2 - t / 2,
                        y_off + W / 2 + t / 2,
                        total_h,
                        total_h + roof_t,
                    )
                )
                self.plotter.add_mesh(
                    roof,
                    color=roof_color,
                    opacity=0.7,
                    show_edges=True,
                    edge_color="#45475a",
                )
        # Heat source (uses building group bounding box)
        if self.model.heat_source.get("enabled", False):
            self._add_heat_source(
                self.model,
                global_min_x,
                global_max_x,
                global_min_y,
                global_max_y,
                global_max_z,
            )
        # Slice planes and device points
        self._draw_slices_and_devices(
            self.model,
            buildings,
            global_min_x,
            global_max_x,
            global_min_y,
            global_max_y,
            global_max_z,
        )

        # Origin + camera
        self.draw_origin_marker()
        if global_max_z == -float("inf"):
            global_max_z = self.model.total_height
        if global_min_x == float("inf"):
            global_min_x = -self.model.length / 2
            global_max_x = model.length / 2
            global_min_y = -model.width / 2
            global_max_y = model.width / 2

        bbox_w = global_max_x - global_min_x
        bbox_d = global_max_y - global_min_y
        self.max_dim = max(bbox_w, bbox_d, global_max_z)
        self.cx = (global_min_x + global_max_x) / 2
        self.cy = (global_min_y + global_max_y) / 2
        self.cz = global_max_z / 2
        if self._first_render:
            self.plotter.reset_camera()
            self.setup_camera()
            self._first_render = False
        else:
            self.plotter.reset_camera_clipping_range()

    def _add_opening(self, opening, story, L, W, t, z0, x_off=0, y_off=0):
        """添加开口显示（多层适配）"""
        wall_index = opening.get("wall_index", 0)
        if wall_index >= len(story.walls):
            return None

        wall = story.walls[wall_index]
        wx1, wy1 = wall["x1"] - L / 2 + x_off, wall["y1"] - W / 2 + y_off
        wx2, wy2 = wall["x2"] - L / 2 + x_off, wall["y2"] - W / 2 + y_off
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
            box = pv.Box(
                bounds=(
                    cx - o_width / 2,
                    cx + o_width / 2,
                    cy - thick / 2 - 0.01,
                    cy + thick / 2 + 0.01,
                    z_bottom,
                    z_bottom + o_height,
                )
            )
        else:
            box = pv.Box(
                bounds=(
                    cx - thick / 2 - 0.01,
                    cx + thick / 2 + 0.01,
                    cy - o_width / 2,
                    cy + o_width / 2,
                    z_bottom,
                    z_bottom + o_height,
                )
            )

        return self.plotter.add_mesh(box, color=color, opacity=0.6)

    def draw_combustibles(self, manager, z_offset=0, L=0, W=0, x_off=0, y_off=0):
        if not manager.items:
            return
        colors = {
            "BROWN": "#8B4513", "RED": "#CD5C5C", "SALMON": "#FA8072",
            "GRAY": "#808080", "KHAKI": "#BDB76B", "IVORY": "#FFFFF0",
            "MAGENTA": "#FF00FF", "ORANGE": "#FFA500",
        }
        # Material-based colors for specialized component parts
        material_colors = {
            "ALUMINUM": "#c0c0c0",
            "STEEL": "#4a5568",
            "JET_FUEL": "#b45309",
            "SOLID_PROPELLANT": "#dc2626",
            "GASOLINE": "#f59e0b",
            "ELECTROLYTE": "#06b6d4",
            "WOOD": "#92400e",
        }
        for cb in manager.items:
            # Use material_key color for component parts
            if cb.component_key and cb.material_key:
                color = material_colors.get(cb.material_key, "#CD853F")
            else:
                color = colors.get(cb.color, "#CD853F")
            box = pv.Box(
                bounds=(
                    cb.x - L / 2 + x_off,
                    cb.x + cb.length - L / 2 + x_off,
                    cb.y - W / 2 + y_off,
                    cb.y + cb.width - W / 2 + y_off,
                    cb.z + z_offset,
                    cb.z + cb.height + z_offset,
                )
            )
            self.plotter.add_mesh(box, color=color, opacity=0.8)

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
            (self.cx, self.cy - d, self.cz + d * 0.6),
            (self.cx, self.cy, self.cz),
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

    def _add_heat_source(self, model, g_xmin, g_xmax, g_ymin, g_ymax, g_zmax):
        hs = self.model.heat_source
        dist = hs.get("distance", 3.0)
        azimuth = hs.get("azimuth", 0)
        elevation = hs.get("elevation", 0)
        width_ratio = hs.get("width_ratio", 1.5)
        height_ratio = hs.get("height_ratio", 1.0)

        group_cx = (g_xmin + g_xmax) / 2
        group_cy = (g_ymin + g_ymax) / 2
        group_half_L = (g_xmax - g_xmin) / 2
        group_half_W = (g_ymax - g_ymin) / 2
        H = max(g_zmax, 1.0) * height_ratio

        D = max(group_half_L, group_half_W) + dist
        az_rad = math.radians(azimuth)
        el_rad = math.radians(elevation)

        source_cx = group_cx + D * math.cos(el_rad) * math.sin(az_rad)
        source_cy = group_cy - D * math.cos(el_rad) * math.cos(az_rad)
        source_cz = D * math.sin(el_rad)

        # Perpendicular direction (along source width)
        perp_x = -math.sin(az_rad + math.pi / 2)
        perp_y = math.cos(az_rad + math.pi / 2)

        # Normal direction: from source toward building center
        norm_x = -math.sin(az_rad)
        norm_y = math.cos(az_rad)

        source_W = abs(group_half_L * perp_x) + abs(group_half_W * perp_y)
        if width_ratio > 1.0:
            source_W *= width_ratio
        source_H = H

        n_cols = 1 if azimuth == 0 else max(5, int(source_W / 0.5))
        n_rows = 1 if elevation == 0 else max(5, int(source_H / 0.5))

        strip_w = source_W / n_cols
        dh = source_H / n_rows

        if elevation > 0:
            tan_alpha = math.tan(el_rad)
            cos_alpha = math.cos(el_rad)
            thickness = dh / cos_alpha if cos_alpha > 1e-10 else 0.2
            for row in range(n_rows):
                z_lo = row * dh
                z_hi = (row + 1) * dh
                # Forward offset along normal for this row
                fwd_offset = row * dh / tan_alpha if tan_alpha > 1e-10 else 0
                for col in range(n_cols):
                    perp_pos = -source_W / 2 + (col + 0.5) * strip_w
                    cx = source_cx + perp_x * perp_pos + norm_x * fwd_offset
                    cy = source_cy + perp_y * perp_pos + norm_y * fwd_offset
                    # Strip bounds: width along perp, depth = thickness along normal
                    x1 = cx - perp_x * strip_w / 2 - norm_x * thickness / 2
                    x2 = cx + perp_x * strip_w / 2 + norm_x * thickness / 2
                    y1 = cy - perp_y * strip_w / 2 - norm_y * thickness / 2
                    y2 = cy + perp_y * strip_w / 2 + norm_y * thickness / 2
                    bx1, bx2 = min(x1, x2), max(x1, x2)
                    by1, by2 = min(y1, y2), max(y1, y2)
                    b = (bx1, bx2, by1, by2, source_cz + z_lo, source_cz + z_hi)
                    self.plotter.add_mesh(
                        pv.Box(bounds=b), color="#f97316", opacity=0.4
                    )
        else:
            thickness = 0.2
            for row in range(n_rows):
                z_lo = row * dh
                z_hi = (row + 1) * dh
                for col in range(n_cols):
                    perp_pos = -source_W / 2 + (col + 0.5) * strip_w
                    cx = source_cx + perp_x * perp_pos
                    cy = source_cy + perp_y * perp_pos
                    x1 = cx - perp_x * strip_w / 2 - norm_x * thickness / 2
                    x2 = cx + perp_x * strip_w / 2 + norm_x * thickness / 2
                    y1 = cy - perp_y * strip_w / 2 - norm_y * thickness / 2
                    y2 = cy + perp_y * strip_w / 2 + norm_y * thickness / 2
                    bx1, bx2 = min(x1, x2), max(x1, x2)
                    by1, by2 = min(y1, y2), max(y1, y2)
                    b = (bx1, bx2, by1, by2, source_cz + z_lo, source_cz + z_hi)
                    self.plotter.add_mesh(
                        pv.Box(bounds=b), color="#f97316", opacity=0.4
                    )

    def _draw_slices_and_devices(self, model, buildings, xmin, xmax, ymin, ymax, zmax):
        """Draw slice planes (semi-transparent) and device points (spheres)."""
        pad = model.domain.get("padding", 5.0)
        # Find first combustible center (same logic as FDSGenerator)
        first_cb_center = None
        for b in buildings:
            for story in b.stories:
                for cb in story.combustibles.items:
                    if first_cb_center is None:
                        first_cb_center = (
                            cb.x - b.length / 2 + cb.length / 2 + b.x_offset,
                            cb.y - b.width / 2 + cb.width / 2 + b.y_offset,
                            story.z_bottom + cb.z + cb.height / 2,
                        )

        if not model.output.get("slices", True):
            return

        # Domain extent for slice visualization
        dx = xmax - xmin + pad * 2
        dy = ymax - ymin + pad * 2
        dz = zmax + pad

        if first_cb_center:
            cx, cy, cz = first_cb_center
        else:
            cx, cy, cz = 0, 0, zmax / 2

        # X-slice plane (thin box)
        try:
            sx = pv.Plane(
                center=(cx, (ymin + ymax) / 2, dz / 2),
                direction=(1, 0, 0),
                i_size=dz,
                j_size=dy,
            )
            self.plotter.add_mesh(sx, color="#f9e2af", opacity=0.08, show_edges=False)

            # Y-slice plane
            sy = pv.Plane(
                center=((xmin + xmax) / 2, cy, dz / 2),
                direction=(0, 1, 0),
                i_size=dx,
                j_size=dz,
            )
            self.plotter.add_mesh(sy, color="#a6e3a1", opacity=0.08, show_edges=False)

            # Z-slice plane
            sz_val = cz + 0.5 if first_cb_center else zmax / 2
            sz = pv.Plane(
                center=((xmin + xmax) / 2, (ymin + ymax) / 2, sz_val),
                direction=(0, 0, 1),
                i_size=dx,
                j_size=dy,
            )
            self.plotter.add_mesh(sz, color="#89b4fa", opacity=0.08, show_edges=False)
        except Exception:
            pass  # pv.Plane may not be available in older versions

        # Device points
        if model.output.get("devices", True):
            if first_cb_center:
                cx, cy, cz = first_cb_center
                self.plotter.add_mesh(
                    pv.Sphere(radius=0.3, center=(cx, cy, cz + 0.1)),
                    color="#f38ba8",
                    opacity=0.9,
                )
            for b in buildings:
                for story in b.stories:
                    z_mid = story.z_bottom + story.height / 2
                    self.plotter.add_mesh(
                        pv.Sphere(radius=0.2, center=(b.x_offset, b.y_offset, z_mid)),
                        color="#cba6f7",
                        opacity=0.7,
                    )

    def highlight_building(self, index: int):
        """Highlight a specific building by index in the 3D view."""
        if self._highlighted_building != index:
            self._highlighted_building = index
            if self.model:
                self.update_model(self.model)

    def close(self):
        if HAS_PYVISTA:
            self.plotter.close()
        super().close()