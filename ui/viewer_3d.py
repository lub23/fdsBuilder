#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File  : viewer_3d.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 2.0
@Desc  : 3D viewer component for building model visualization
"""

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
from models.building import BuildingGroup, Building, Story, Opening, FireCompartment, Roof
from models.geometry import detect_coplanar_openings, is_coplanar
from models.materials import MATERIAL_LIBRARY


# ============================================================
# 3D可视化组件
# ============================================================
class Viewer3D(QWidget):
    """3D可视化查看器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self._bg = None  # resolved BuildingGroup
        self.wall_actors = []
        self.opening_actors = []
        self.selected_wall = -1
        self.selected_opening = -1
        self.visible_stories = None  # None = 全部显示; Set[(bi, si)] for multi-building
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
            self.plotter.set_background("#1e1e2e")
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

    def _resolve_building_group(self, model) -> BuildingGroup:
        """Resolve model to a BuildingGroup, handling backward compat."""
        if isinstance(model, BuildingGroup):
            return model
        if hasattr(model, "building_group"):
            bg = model.building_group
            if isinstance(bg, BuildingGroup):
                return bg
        # Fallback: return empty group
        return BuildingGroup()

    def _is_story_visible(self, bi: int, si: int) -> bool:
        """Check if a story is visible given current visibility filter."""
        if self.visible_stories is None:
            return True
        # Support both (bi, si) tuples and plain si ints for backward compat
        if (bi, si) in self.visible_stories:
            return True
        if si in self.visible_stories:
            return True
        return False

    def update_model(self, model, debounce=False):
        """Update the model and trigger re-render.

        Accepts either a BuildingGroup directly or a legacy model object
        with a .building_group attribute.
        """
        self.model = model
        self._bg = self._resolve_building_group(model)

        if not HAS_PYVISTA or model is None:
            return
        if debounce:
            self._pending_update = True
            self._schedule_debounced_update()
        else:
            self._do_full_render()

    def _do_full_render(self):
        """Perform full render using boundary-based wall rendering."""
        self.wall_actors.clear()
        self.opening_actors.clear()
        self.plotter.clear()

        bg = self._bg
        if bg is None:
            return

        # Render all buildings in the group
        buildings = bg.buildings
        global_max_x = global_max_y = global_max_z = -float("inf")
        global_min_x = global_min_y = float("inf")

        for bi, building in enumerate(buildings):
            ox, L, oy, W = building.boundary
            t = building.wall_thickness

            is_highlighted = bi == self._highlighted_building
            wall_opacity = 1.0 if is_highlighted else 0.6
            edge_color = "#f97316" if is_highlighted else "#45475a"
            edge_width = 3 if is_highlighted else 1

            # Track bounding box
            global_min_x = min(global_min_x, ox - t)
            global_max_x = max(global_max_x, ox + L + t)
            global_min_y = min(global_min_y, oy - t)
            global_max_y = max(global_max_y, oy + W + t)

            # Compute total height for this building
            total_h = 0.0
            for s in building.stories:
                total_h = max(total_h, s.z_bottom + s.height)
            if total_h == 0.0:
                total_h = building.height
            global_max_z = max(global_max_z, total_h)

            for si, story in enumerate(building.stories):
                if not self._is_story_visible(bi, si):
                    continue

                z0 = story.z_bottom
                z1 = story.z_top

                # 1. Exterior walls (4 boxes from boundary)
                self._draw_exterior_walls(
                    ox, L, oy, W, t, z0, z1,
                    wall_opacity=wall_opacity,
                    edge_color=edge_color,
                    edge_width=edge_width,
                )

                # 2. Exterior openings (story.openings + coplanar FC openings)
                all_ext_openings = list(story.openings)
                all_ext_openings += detect_coplanar_openings(building, story)
                for opening in all_ext_openings:
                    actor = self._draw_opening(opening, building, z0, is_exterior=True)
                    if actor:
                        self.opening_actors.append(((bi, si), actor))

                # 3. Fire compartment firewalls (non-coplanar boundaries, red semi-transparent)
                for fc in story.fire_compartments:
                    self._draw_firewalls(fc, building, z0, z1)
                    # 4. Internal openings (on non-coplanar walls)
                    for opening in fc.openings:
                        if not is_coplanar(fc.boundary, L, W, opening.wall):
                            self._draw_opening(
                                opening, building, z0, is_exterior=False,
                                fc_boundary=fc.boundary,
                            )

                # 5. Roof
                if self.show_roof:
                    self._draw_roof(story.roof, ox, L, oy, W, z1)

                # 6. Combustibles per FC
                for fc in story.fire_compartments:
                    self._draw_combustibles(fc, ox, oy, z0)

        # Heat source (uses building group bounding box)
        hs = bg.heat_source
        if hs.get("enabled", False):
            self._add_heat_source(
                bg,
                global_min_x,
                global_max_x,
                global_min_y,
                global_max_y,
                global_max_z,
            )
        # Slice planes and device points
        self._draw_slices_and_devices(
            bg,
            buildings,
            global_min_x,
            global_max_x,
            global_min_y,
            global_max_y,
            global_max_z,
        )

        # Origin + camera
        self._draw_origin_marker(buildings)
        if global_max_z == -float("inf"):
            global_max_z = 3.0
        if global_min_x == float("inf"):
            # Fallback: use first building or defaults
            if buildings:
                b0 = buildings[0]
                ox0, L0, oy0, W0 = b0.boundary
                global_min_x = ox0
                global_max_x = ox0 + L0
                global_min_y = oy0
                global_max_y = oy0 + W0
            else:
                global_min_x, global_max_x = -10, 10
                global_min_y, global_max_y = -5, 5

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

    # ── Drawing helpers ─────────────────────────────────────

    def _draw_exterior_walls(self, ox, L, oy, W, t, z0, z1,
                             wall_color="#808080", wall_opacity=0.6,
                             edge_color="#45475a", edge_width=1):
        """Draw 4 exterior wall boxes using PyVista."""
        walls = [
            # South wall (y_min)
            (ox - t / 2, ox + L + t / 2, oy - t, oy, z0, z1),
            # North wall (y_max)
            (ox - t / 2, ox + L + t / 2, oy + W, oy + W + t, z0, z1),
            # West wall (x_min)
            (ox - t, ox, oy - t / 2, oy + W + t / 2, z0, z1),
            # East wall (x_max)
            (ox + L, ox + L + t, oy - t / 2, oy + W + t / 2, z0, z1),
        ]
        for bounds in walls:
            box = pv.Box(bounds=bounds)
            actor = self.plotter.add_mesh(
                box,
                color=wall_color,
                opacity=wall_opacity,
                show_edges=True,
                edge_color=edge_color,
                line_width=edge_width,
            )
            self.wall_actors.append(actor)

    def _draw_opening(self, opening: Opening, building: Building, z0: float,
                      is_exterior: bool = True, fc_boundary=None):
        """Draw an opening as a colored box on the wall surface."""
        ox, L, oy, W = building.boundary
        w_off, w, h_off, h = opening.boundary
        color = "#4CAF50" if opening.type == "door" else "#2196F3"  # green=door, blue=window

        if is_exterior:
            if opening.wall == "y_min":
                box = pv.Box(bounds=[ox + w_off, ox + w_off + w,
                                     oy - 0.05, oy + 0.05,
                                     z0 + h_off, z0 + h_off + h])
            elif opening.wall == "y_max":
                box = pv.Box(bounds=[ox + w_off, ox + w_off + w,
                                     oy + W - 0.05, oy + W + 0.05,
                                     z0 + h_off, z0 + h_off + h])
            elif opening.wall == "x_min":
                box = pv.Box(bounds=[ox - 0.05, ox + 0.05,
                                     oy + w_off, oy + w_off + w,
                                     z0 + h_off, z0 + h_off + h])
            else:  # x_max
                box = pv.Box(bounds=[ox + L - 0.05, ox + L + 0.05,
                                     oy + w_off, oy + w_off + w,
                                     z0 + h_off, z0 + h_off + h])
        else:
            # Interior opening on FC boundary
            if fc_boundary is None:
                return None
            fx_min, fx_max, fy_min, fy_max = fc_boundary
            if opening.wall == "y_min":
                box = pv.Box(bounds=[ox + w_off, ox + w_off + w,
                                     oy + fy_min - 0.05, oy + fy_min + 0.05,
                                     z0 + h_off, z0 + h_off + h])
            elif opening.wall == "y_max":
                box = pv.Box(bounds=[ox + w_off, ox + w_off + w,
                                     oy + fy_max - 0.05, oy + fy_max + 0.05,
                                     z0 + h_off, z0 + h_off + h])
            elif opening.wall == "x_min":
                box = pv.Box(bounds=[ox + fx_min - 0.05, ox + fx_min + 0.05,
                                     oy + w_off, oy + w_off + w,
                                     z0 + h_off, z0 + h_off + h])
            else:  # x_max
                box = pv.Box(bounds=[ox + fx_max - 0.05, ox + fx_max + 0.05,
                                     oy + w_off, oy + w_off + w,
                                     z0 + h_off, z0 + h_off + h])

        return self.plotter.add_mesh(box, color=color, opacity=0.8)

    def _draw_firewalls(self, fc: FireCompartment, building: Building, z0, z1):
        """Draw non-coplanar FC boundaries as walls (same color as exterior walls)."""
        ox, L, oy, W = building.boundary
        x_min, x_max, y_min, y_max = fc.boundary
        t = fc.firewall_thickness
        if t <= 0:
            return

        fw_color = "#808080"
        fw_opacity = 0.6

        # Only draw non-coplanar boundaries (interior partitions)
        if x_min > 0 and not is_coplanar(fc.boundary, L, W, "x_min"):
            box = pv.Box(bounds=[ox + x_min - t / 2, ox + x_min + t / 2,
                                  oy + y_min, oy + y_max, z0, z1])
            self.plotter.add_mesh(box, color=fw_color, opacity=fw_opacity, show_edges=True,
                                  edge_color="#45475a", line_width=1)
        if x_max < L and not is_coplanar(fc.boundary, L, W, "x_max"):
            box = pv.Box(bounds=[ox + x_max - t / 2, ox + x_max + t / 2,
                                  oy + y_min, oy + y_max, z0, z1])
            self.plotter.add_mesh(box, color=fw_color, opacity=fw_opacity, show_edges=True,
                                  edge_color="#45475a", line_width=1)
        if y_min > 0 and not is_coplanar(fc.boundary, L, W, "y_min"):
            box = pv.Box(bounds=[ox + x_min, ox + x_max,
                                  oy + y_min - t / 2, oy + y_min + t / 2, z0, z1])
            self.plotter.add_mesh(box, color=fw_color, opacity=fw_opacity, show_edges=True,
                                  edge_color="#45475a", line_width=1)
        if y_max < W and not is_coplanar(fc.boundary, L, W, "y_max"):
            box = pv.Box(bounds=[ox + x_min, ox + x_max,
                                  oy + y_max - t / 2, oy + y_max + t / 2, z0, z1])
            self.plotter.add_mesh(box, color=fw_color, opacity=fw_opacity, show_edges=True,
                                  edge_color="#45475a", line_width=1)

    def _draw_roof(self, roof: Roof, ox, L, oy, W, z_top):
        """Draw a roof slab above a story."""
        slab = pv.Box(bounds=[ox, ox + L, oy, oy + W, z_top, z_top + roof.thickness])
        self.plotter.add_mesh(slab, color="#888888", opacity=0.4)

    def _draw_combustibles(self, fc: FireCompartment, ox, oy, z_offset):
        """Draw combustible items within a fire compartment.

        Handles both positioned objects (with x/y/z) and key+count dicts
        (expanded via grid layout within FC boundary).
        """
        from models.materials import COMBUSTIBLE_LIBRARY
        from models.combustibles import SPECIALIZED_COMPONENTS

        colors = {
            "BROWN": "#8B4513", "RED": "#CD5C5C", "SALMON": "#FA8072",
            "GRAY": "#808080", "KHAKI": "#BDB76B", "IVORY": "#FFFFF0",
            "MAGENTA": "#FF00FF", "ORANGE": "#FFA500",
        }
        material_colors = {
            "ALUMINUM": "#c0c0c0", "STEEL": "#4a5568", "JET_FUEL": "#b45309",
            "SOLID_PROPELLANT": "#dc2626", "GASOLINE": "#f59e0b",
            "ELECTROLYTE": "#06b6d4", "WOOD": "#92400e",
        }

        fc_xmin, fc_xmax, fc_ymin, fc_ymax = fc.boundary
        fc_L = fc_xmax - fc_xmin
        fc_W = fc_ymax - fc_ymin

        # Expand key+count entries into positioned items
        positioned_items = []
        item_index = 0
        for cb in fc.combustibles:
            if isinstance(cb, dict) and "key" in cb and "x" not in cb:
                # key+count format — expand with grid layout
                key = cb["key"]
                count = cb.get("count", 1)
                cb_def = COMBUSTIBLE_LIBRARY.get(key, {})
                cb_L = cb_def.get("length", 1.0)
                cb_W = cb_def.get("width", 0.8)
                cb_H = cb_def.get("height", 0.5)
                cb_color = cb_def.get("color", "BROWN")
                for ci in range(count):
                    cols = max(1, int(fc_L / (cb_L + 0.5)))
                    row = item_index // cols
                    col = item_index % cols
                    local_x = fc_xmin + 0.5 + col * (cb_L + 0.5)
                    local_y = fc_ymin + 0.5 + row * (cb_W + 0.5)
                    if local_x + cb_L > fc_xmax:
                        local_x = fc_xmax - cb_L - 0.1
                    if local_y + cb_W > fc_ymax:
                        local_y = fc_ymax - cb_W - 0.1
                    positioned_items.append({
                        "x": local_x, "y": local_y, "z": 0,
                        "length": cb_L, "width": cb_W, "height": cb_H,
                        "color": cb_color, "component_key": None, "material_key": None,
                    })
                    item_index += 1
            elif isinstance(cb, dict):
                # Already positioned dict
                positioned_items.append(cb)
            else:
                # Combustible object
                positioned_items.append({
                    "x": cb.x, "y": cb.y, "z": cb.z,
                    "length": cb.length, "width": cb.width, "height": cb.height,
                    "color": getattr(cb, "color", "BROWN"),
                    "component_key": getattr(cb, "component_key", None),
                    "material_key": getattr(cb, "material_key", None),
                })

        # Expand specialized_components similarly
        sc_index = 0
        for sc in fc.specialized_components:
            if isinstance(sc, dict) and "key" in sc and "x" not in sc:
                key = sc["key"]
                count = sc.get("count", 1)
                comp = SPECIALIZED_COMPONENTS.get(key)
                if not comp:
                    continue
                for ci in range(count):
                    total_needed = comp.total_length
                    start_x = fc_xmin + 1.0 + sc_index * (total_needed + 2.0)
                    center_y = fc_ymin + (fc_W - comp.total_width) / 2
                    for part in comp.parts:
                        positioned_items.append({
                            "x": start_x + part.dx, "y": center_y + part.dy, "z": part.dz,
                            "length": part.length, "width": part.width, "height": part.height,
                            "color": "GRAY", "component_key": key,
                            "material_key": part.material_key,
                        })
                    sc_index += 1

        # Draw all positioned items
        for item in positioned_items:
            cb_x = item["x"]
            cb_y = item["y"]
            cb_z = item.get("z", 0)
            cb_length = item["length"]
            cb_width = item["width"]
            cb_height = item["height"]
            cb_component_key = item.get("component_key")
            cb_material_key = item.get("material_key")

            if cb_component_key and cb_material_key:
                color = material_colors.get(cb_material_key, "#CD853F")
            else:
                color = colors.get(item.get("color", "BROWN"), "#CD853F")

            box = pv.Box(
                bounds=(
                    ox + cb_x,
                    ox + cb_x + cb_length,
                    oy + cb_y,
                    oy + cb_y + cb_width,
                    cb_z + z_offset,
                    cb_z + cb_height + z_offset,
                )
            )
            self.plotter.add_mesh(box, color=color, opacity=0.8)

    def _draw_origin_marker(self, buildings):
        """Draw origin marker axes using first building's position."""
        if not buildings:
            return
        b0 = buildings[0]
        ox0, L0, oy0, W0 = b0.boundary
        a = max(L0, W0) * 0.1
        self.plotter.add_mesh(
            pv.Line((ox0, oy0, 0), (ox0 + a, oy0, 0)), color="red", line_width=4
        )
        self.plotter.add_mesh(
            pv.Line((ox0, oy0, 0), (ox0, oy0 + a, 0)), color="green", line_width=4
        )
        self.plotter.add_mesh(
            pv.Line((ox0, oy0, 0), (ox0, oy0, a)), color="blue", line_width=4
        )
        self.plotter.add_mesh(
            pv.Sphere(radius=a * 0.05, center=(ox0, oy0, 0)), color="white"
        )

    # Keep legacy name as alias
    def draw_origin_marker(self):
        bg = self._bg
        if bg and bg.buildings:
            self._draw_origin_marker(bg.buildings)

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
        for i, actor in enumerate(self.wall_actors):
            if actor is None:
                continue
            actor.prop.color = "#808080"
            actor.prop.opacity = 0.6

        if 0 <= index < len(self.wall_actors):
            actor = self.wall_actors[index]
            if actor:
                actor.prop.color = "#f97316"
                actor.prop.opacity = 1.0

        self.selected_wall = index
        self.plotter.render()

    def highlight_opening(self, index: int):
        if not HAS_PYVISTA:
            return
        for item in self.opening_actors:
            if isinstance(item, tuple):
                _, actor = item
            else:
                actor = item
            if actor:
                actor.prop.color = "#4CAF50"
                actor.prop.opacity = 0.6

        if 0 <= index < len(self.opening_actors):
            item = self.opening_actors[index]
            if isinstance(item, tuple):
                _, actor = item
            else:
                actor = item
            if actor:
                actor.prop.color = "#f97316"
                actor.prop.opacity = 1.0

        self.selected_opening = index
        self.plotter.render()

    def _add_heat_source(self, model, g_xmin, g_xmax, g_ymin, g_ymax, g_zmax):
        hs = model.heat_source
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
        # Find first combustible center
        first_cb_center = None
        for b in buildings:
            ox, L, oy, W = b.boundary
            for story in b.stories:
                for fc in story.fire_compartments:
                    for cb in fc.combustibles:
                        if first_cb_center is None:
                            if isinstance(cb, dict):
                                cb_x = cb.get("x", 0)
                                cb_y = cb.get("y", 0)
                                cb_z = cb.get("z", 0)
                                cb_length = cb.get("length", 1)
                                cb_width = cb.get("width", 1)
                                cb_height = cb.get("height", 1)
                            else:
                                cb_x = cb.x
                                cb_y = cb.y
                                cb_z = cb.z
                                cb_length = cb.length
                                cb_width = cb.width
                                cb_height = cb.height
                            first_cb_center = (
                                ox + cb_x + cb_length / 2,
                                oy + cb_y + cb_width / 2,
                                story.z_bottom + cb_z + cb_height / 2,
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
                bx, bL, by, bW = b.boundary
                b_cx = bx + bL / 2
                b_cy = by + bW / 2
                for story in b.stories:
                    z_mid = story.z_bottom + story.height / 2
                    self.plotter.add_mesh(
                        pv.Sphere(radius=0.2, center=(b_cx, b_cy, z_mid)),
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
