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
from dataclasses import dataclass, field

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
from models.building import BuildingGroup
from models.heat_source import source_orientation
from models.geometry import detect_coplanar_openings, is_coplanar


@dataclass
class BuildingMeshBundle:
    walls: "pv.PolyData | None" = None
    openings: "pv.PolyData | None" = None
    firewalls: "pv.PolyData | None" = None
    roofs: "pv.PolyData | None" = None
    roof_openings: "pv.PolyData | None" = None
    combustibles_per_material: dict = field(default_factory=dict)
    actors: dict = field(default_factory=dict)


def _signature(building):
    """Build a stable geometry signature for cache keying."""

    def _opening_sig(o):
        return (o.wall, o.type, tuple(o.boundary))

    def _fc_sig(fc):
        return (
            fc.name, tuple(fc.boundary), fc.firewall_thickness,
            tuple(_opening_sig(o) for o in fc.openings),
            tuple(
                (c.get("key", ""), c.get("count", 1), c.get("rotation", 0))
                for c in fc.combustibles if isinstance(c, dict)
            ),
            tuple(
                (
                    sc.get("key", ""),
                    sc.get("count", 1),
                    sc.get("orientation", ""),
                    sc.get("rotation", 0),
                )
                for sc in fc.specialized_components if isinstance(sc, dict)
            ),
        )

    def _story_sig(s):
        return (
            s.name, round(s.height, 4),
            tuple(_opening_sig(o) for o in s.openings),
            tuple(_fc_sig(fc) for fc in s.fire_compartments),
            tuple(
                (c.get("key", ""), c.get("count", 1), tuple(c.get("boundary", [])))
                for c in s.combustibles if isinstance(c, dict)
            ),
            tuple(
                (
                    sc.get("key", ""),
                    sc.get("count", 1),
                    tuple(sc.get("boundary", [])),
                    sc.get("orientation", ""),
                    sc.get("rotation", 0),
                )
                for sc in s.specialized_components if isinstance(sc, dict)
            ),
            (round(s.roof.thickness, 4), s.roof.material),
        )

    return (
        building.name,
        round(building.length, 4),
        round(building.width, 4),
        round(building.height, 4),
        round(building.wall_thickness, 4),
        round(building.offset_x, 4),
        round(building.offset_y, 4),
        tuple(_story_sig(s) for s in building.stories),
    )


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
        self._actor_groups: dict[str, list] = {
            "buildings": [],
            "combustibles": [],
            "heat_source": [],
            "slices": [],
            "devices": [],
            "origin": [],
        }
        self._building_cache: dict = {}
        self._cache_max = 100
        self._fds_scene = None  # active FDS preview scene (or None)
        self._fds_heat_source = None
        self._debounce_timer = None
        self._pending_update = False
        self.setup_ui()

    def _add_to_group(self, group: str, actor):
        if actor is None:
            return
        self._actor_groups.setdefault(group, []).append(actor)

    def _clear_group(self, group: str):
        actors = self._actor_groups.get(group, [])
        for a in actors:
            try:
                self.plotter.remove_actor(a)
            except Exception:
                pass
        self._actor_groups[group] = []

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

    @staticmethod
    def _component_orientation_axis(orientation):
        if orientation is None:
            return "x"
        value = str(orientation).strip().lower()
        if value in {
            "y", "ns", "north_south", "north-south", "south-north", "南北", "南北向",
        }:
            return "y"
        return "x"

    def _component_preview_item(self, comp, sc: dict, ci: int) -> dict:
        orientation = sc.get("orientation")
        if orientation is None and sc.get("rotation") == 90:
            orientation = "y"
        rotate_xy = self._component_orientation_axis(orientation) == "y"
        if rotate_xy:
            length, width = comp.total_width, comp.total_length
        else:
            length, width = comp.total_length, comp.total_width
        return {
            "length": length,
            "width": width,
            "height": comp.total_height,
            "color": "GRAY",
            "component_key": sc["key"],
            "_comp": comp,
            "_instance": ci,
            "_rotate_xy": rotate_xy,
        }

    @staticmethod
    def _component_part_bounds(item, part, ox, oy, z_offset):
        if item.get("_rotate_xy"):
            comp = item["_comp"]
            x1 = ox + item["x"] + part.dy
            x2 = x1 + part.width
            y1 = oy + item["y"] + comp.total_length - part.dx - part.length
            y2 = y1 + part.length
            return (x1, x2, y1, y2, part.dz + z_offset, part.dz + part.height + z_offset)
        return (
            ox + item["x"] + part.dx,
            ox + item["x"] + part.dx + part.length,
            oy + item["y"] + part.dy,
            oy + item["y"] + part.dy + part.width,
            part.dz + z_offset,
            part.dz + part.height + z_offset,
        )

    def update_model(self, model, debounce=False, partial=False):
        """Update the model and trigger re-render.

        Accepts either a BuildingGroup directly or a legacy model object
        with a .building_group attribute.

        Args:
            model: BuildingGroup or compatible model
            debounce: If True, debounce the update
            partial: If True, only update changed components (faster for热通量-only changes)
        """
        old_heat_flux = getattr(self, '_last_heat_flux', None)
        new_heat_flux = None
        if model and hasattr(model, 'heat_source'):
            new_heat_flux = model.heat_source.get('net_heat_flux')

        if self._fds_scene is not None:
            # FDS preview is active; do not clobber it with building renders.
            return

        self.model = model
        self._bg = self._resolve_building_group(model)

        if not HAS_PYVISTA or model is None:
            return

        if partial and old_heat_flux is not None and new_heat_flux is not None and old_heat_flux == new_heat_flux:
            return

        if not partial and new_heat_flux is not None:
            self._last_heat_flux = new_heat_flux

        if debounce:
            self._pending_update = True
            self._schedule_debounced_update()
        else:
            self._do_full_render()

    def _do_full_render(self):
        """Full render: buildings + combustibles + heat source + slices + origin + camera."""
        self.wall_actors.clear()
        self.opening_actors.clear()
        # Clear non-building groups; buildings handled by cache attach/detach.
        self._clear_group("combustibles")
        self._clear_group("heat_source")
        self._clear_group("slices")
        self._clear_group("devices")
        self._clear_group("origin")
        # NOTE: do NOT call self.plotter.clear() — it wipes cached building actors.

        bg = self._bg
        if bg is None:
            return

        # Detach all bundles so attach-bundle re-adds cleanly in new order.
        for bundle in self._building_cache.values():
            if bundle.actors:
                for a in bundle.actors.values():
                    try:
                        self.plotter.remove_actor(a)
                    except Exception:
                        pass
                bundle.actors.clear()
        self._clear_group("buildings")

        bbox = self._render_buildings_group(bg)
        if bbox is None:
            return

        self._render_heat_source_group(bg)
        self._render_slices_devices_group(bg, bbox)
        self._render_origin(bg)
        self._finalize_camera(bbox)

    # ── FDS preview scene ─────────────────────────────────────
    def clear_fds_scene(self):
        """Drop the FDS preview so building renders take over again."""
        self._fds_scene = None

    def update_fds_scene(self, scene, heat_source=None):
        """Render an FDS file's geometry (domain + obstruction boxes)."""
        self._fds_scene = scene
        self._fds_heat_source = dict(heat_source or {})
        if not HAS_PYVISTA or scene is None:
            return
        self._render_fds_scene(scene, self._fds_heat_source)

    def _render_fds_scene(self, scene, heat_source=None):
        # Detach cached building actors (keeps meshes cached for later).
        for bundle in self._building_cache.values():
            if bundle.actors:
                for a in bundle.actors.values():
                    try:
                        self.plotter.remove_actor(a)
                    except Exception:
                        pass
                bundle.actors.clear()
        for group in list(self._actor_groups.keys()):
            self._clear_group(group)

        domain = scene.domain or (0, 10, 0, 10, 0, 1)
        xmin, xmax, ymin, ymax, zmin, zmax = domain

        box = pv.Box(bounds=(xmin, xmax, ymin, ymax, zmin, zmax))
        actor = self.plotter.add_mesh(
            box, color="#5c6b8a", style="wireframe", line_width=1.2
        )
        self._add_to_group("origin", actor)

        comb_parts: list = []
        noncomb_parts: list = []
        for o in scene.obstacles:
            parts = comb_parts if scene.combustible(o) else noncomb_parts
            parts.append(pv.Box(bounds=(o.xmin, o.xmax, o.ymin, o.ymax, o.zmin, o.zmax)))
        if comb_parts:
            actor = self.plotter.add_mesh(
                pv.merge(comb_parts), color="#e0703c", opacity=0.55
            )
            self._add_to_group("combustibles", actor)
        if noncomb_parts:
            actor = self.plotter.add_mesh(
                pv.merge(noncomb_parts), color="#707888", opacity=0.35
            )
            self._add_to_group("buildings", actor)

        footprint = self._footprint_bounds(scene=scene)
        self._draw_heat_direction_arrow(
            scene.domain or (0, 10, 0, 10, 0, 1),
            heat_source or self._fds_heat_source,
            footprint,
        )
        self._first_render = True
        self._finalize_camera((xmin, xmax, ymin, ymax, zmax))


    def _render_buildings_group(self, bg):
        """Render building bundles from cache; returns bbox tuple or None."""
        buildings = bg.buildings
        global_max_x = global_max_y = global_max_z = -float("inf")
        global_min_x = global_min_y = float("inf")

        active_sigs = set()
        for bi, building in enumerate(buildings):
            ox, L, oy, W = building.boundary
            t = building.wall_thickness
            is_highlighted = bi == self._highlighted_building
            wall_opacity = 1.0 if is_highlighted else 0.6
            edge_color = "#f97316" if is_highlighted else "#45475a"
            edge_width = 3 if is_highlighted else 1

            global_min_x = min(global_min_x, ox - t)
            global_max_x = max(global_max_x, ox + L + t)
            global_min_y = min(global_min_y, oy - t)
            global_max_y = max(global_max_y, oy + W + t)
            total_h = 0.0
            for s in building.stories:
                total_h = max(total_h, s.z_bottom + s.height)
            if total_h == 0.0:
                total_h = building.height
            global_max_z = max(global_max_z, total_h)

            sig = _signature(building)
            active_sigs.add(sig)
            bundle = self._building_cache.get(sig)
            if bundle is None:
                bundle = self._build_bundle(building)
                self._building_cache[sig] = bundle
                if len(self._building_cache) > self._cache_max:
                    oldest = next(iter(self._building_cache))
                    self._building_cache.pop(oldest)

            self._attach_bundle(bundle, wall_opacity, edge_color, edge_width)

        # Detach stale bundles (present in cache but not in current scene)
        for sig, bundle in list(self._building_cache.items()):
            if sig not in active_sigs and bundle.actors:
                for a in bundle.actors.values():
                    try:
                        self.plotter.remove_actor(a)
                    except Exception:
                        pass
                bundle.actors.clear()

        if global_min_x == float("inf"):
            if buildings:
                b0 = buildings[0]
                ox0, L0, oy0, W0 = b0.boundary
                global_min_x, global_max_x = ox0, ox0 + L0
                global_min_y, global_max_y = oy0, oy0 + W0
            else:
                return None
        if global_max_z == -float("inf"):
            global_max_z = 3.0
        return (
            global_min_x, global_max_x,
            global_min_y, global_max_y,
            global_max_z,
        )

    def _attach_bundle(self, bundle: BuildingMeshBundle,
                       wall_opacity: float, edge_color: str, edge_width: int):
        """Ensure bundle meshes are visible in the plotter; add to groups."""
        if bundle.actors:
            for key, actor in bundle.actors.items():
                if key in ("walls", "firewalls"):
                    actor.prop.opacity = wall_opacity
                    actor.prop.edge_color = edge_color
                    actor.prop.line_width = edge_width
                group = "combustibles" if key.startswith("comb_") else "buildings"
                self._add_to_group(group, actor)
            return

        if bundle.walls is not None:
            a = self.plotter.add_mesh(
                bundle.walls, color="#808080",
                opacity=wall_opacity, show_edges=True,
                edge_color=edge_color, line_width=edge_width,
            )
            bundle.actors["walls"] = a
            self._add_to_group("buildings", a)
        if bundle.firewalls is not None:
            a = self.plotter.add_mesh(
                bundle.firewalls, color="#808080",
                opacity=0.6, show_edges=True,
                edge_color="#45475a", line_width=1,
            )
            bundle.actors["firewalls"] = a
            self._add_to_group("buildings", a)
        if bundle.openings is not None:
            a = self.plotter.add_mesh(bundle.openings, color="#4CAF50", opacity=0.8)
            bundle.actors["openings"] = a
            self._add_to_group("buildings", a)
        if bundle.roofs is not None:
            a = self.plotter.add_mesh(bundle.roofs, color="#888888", opacity=0.4)
            bundle.actors["roofs"] = a
            self._add_to_group("buildings", a)
        if bundle.roof_openings is not None:
            # Render roof openings as bright cyan boxes so they're visible
            a = self.plotter.add_mesh(
                bundle.roof_openings, color="#00ffff", opacity=0.9,
                show_edges=True, edge_color="#ffffff", line_width=2
            )
            bundle.actors["roof_openings"] = a
            self._add_to_group("buildings", a)
        for color, mesh in bundle.combustibles_per_material.items():
            if mesh is None:
                continue
            a = self.plotter.add_mesh(mesh, color=color, opacity=0.8)
            bundle.actors[f"comb_{color}"] = a
            self._add_to_group("combustibles", a)

    def _build_bundle(self, building) -> BuildingMeshBundle:
        """Build a BuildingMeshBundle from a Building object."""
        bundle = BuildingMeshBundle()
        ox, L, oy, W = building.boundary
        t = building.wall_thickness

        def _box(bounds):
            return pv.Box(bounds=bounds)

        wall_boxes: list = []
        opening_boxes: list = []
        firewall_boxes: list = []
        roof_boxes: list = []
        roof_opening_boxes: list = []
        combust_per_color: dict[str, list] = {}

        for story in building.stories:
            z0 = story.z_bottom
            z1 = story.z_top

            half_t = t / 2
            wall_boxes.extend([
                # y-direction walls: shortened at ends so they sit between x-walls
                _box([ox + half_t, ox + L - half_t, oy - half_t, oy + half_t, z0, z1]),
                _box([ox + half_t, ox + L - half_t, oy + W - half_t, oy + W + half_t, z0, z1]),
                # x-direction walls: extended past y-walls to fill corners fully
                _box([ox - half_t, ox + half_t, oy - half_t, oy + W + half_t, z0, z1]),
                _box([ox + L - half_t, ox + L + half_t, oy - half_t, oy + W + half_t, z0, z1]),
            ])

            all_ext = list(story.openings) + detect_coplanar_openings(building, story)
            for op in all_ext:
                box = self._opening_box(op, building, z0, is_exterior=True)
                if box is not None:
                    opening_boxes.append(box)

            for fc in story.fire_compartments:
                firewall_boxes.extend(self._firewall_boxes(fc, building, z0, z1))
                for op in fc.openings:
                    if not is_coplanar(fc.boundary, L, W, op.wall):
                        box = self._opening_box(
                            op, building, z0,
                            is_exterior=False, fc_boundary=fc.boundary,
                        )
                        if box is not None:
                            opening_boxes.append(box)

            if self.show_roof:
                roof_boxes.append(
                    _box([ox - t/2, ox + L + t/2, oy - t/2, oy + W + t/2, z1, z1 + story.roof.thickness])
                )
                # Add roof openings as SEPARATE meshes (not merged with roof)
                for opening in story.roof.openings:
                    bnd = opening.get("boundary", opening.get("bnd", [0, 0, 0, 0]))
                    roof_opening_boxes.append(
                        _box([
                            ox + bnd[0], ox + bnd[0] + bnd[1],
                            oy + bnd[2], oy + bnd[2] + bnd[3],
                            z1 - 0.05, z1 + story.roof.thickness + 0.05
                        ])
                    )

            for fc in story.fire_compartments:
                self._collect_combustible_boxes(
                    fc, story.fire_compartments, ox, oy, z0, combust_per_color)
            self._collect_story_combustible_boxes(story, ox, oy, z0, combust_per_color)

        def _combine(meshes):
            if not meshes:
                return None
            if len(meshes) == 1:
                return meshes[0]
            return pv.merge(meshes)

        bundle.walls = _combine(wall_boxes)
        bundle.openings = _combine(opening_boxes)
        bundle.firewalls = _combine(firewall_boxes)
        bundle.roofs = _combine(roof_boxes)
        bundle.roof_openings = _combine(roof_opening_boxes)
        bundle.combustibles_per_material = {
            color: _combine(boxes) for color, boxes in combust_per_color.items()
        }
        return bundle

    def _opening_box(self, opening, building, z0, is_exterior=True, fc_boundary=None):
        """Return a pv.Box for an opening, or None if inputs invalid."""
        ox, L, oy, W = building.boundary
        w_off, w, h_off, h = opening.boundary

        if is_exterior:
            if opening.wall == "y_min":
                b = [ox + w_off, ox + w_off + w, oy - 0.05, oy + 0.05,
                     z0 + h_off, z0 + h_off + h]
            elif opening.wall == "y_max":
                b = [ox + w_off, ox + w_off + w, oy + W - 0.05, oy + W + 0.05,
                     z0 + h_off, z0 + h_off + h]
            elif opening.wall == "x_min":
                b = [ox - 0.05, ox + 0.05, oy + w_off, oy + w_off + w,
                     z0 + h_off, z0 + h_off + h]
            else:  # x_max
                b = [ox + L - 0.05, ox + L + 0.05, oy + w_off, oy + w_off + w,
                     z0 + h_off, z0 + h_off + h]
        else:
            if fc_boundary is None:
                return None
            fx_min, fx_max, fy_min, fy_max = fc_boundary
            if opening.wall == "y_min":
                b = [ox + fx_min + w_off, ox + fx_min + w_off + w,
                     oy + fy_min - 0.05, oy + fy_min + 0.05,
                     z0 + h_off, z0 + h_off + h]
            elif opening.wall == "y_max":
                b = [ox + fx_min + w_off, ox + fx_min + w_off + w,
                     oy + fy_max - 0.05, oy + fy_max + 0.05,
                     z0 + h_off, z0 + h_off + h]
            elif opening.wall == "x_min":
                b = [ox + fx_min - 0.05, ox + fx_min + 0.05,
                     oy + fy_min + w_off, oy + fy_min + w_off + w,
                     z0 + h_off, z0 + h_off + h]
            else:  # x_max
                b = [ox + fx_max - 0.05, ox + fx_max + 0.05,
                     oy + fy_min + w_off, oy + fy_min + w_off + w,
                     z0 + h_off, z0 + h_off + h]
        return pv.Box(bounds=b)

    def _firewall_boxes(self, fc, building, z0, z1):
        """Return list of pv.Box for a fire compartment's interior firewalls."""
        ox, L, oy, W = building.boundary
        x_min, x_max, y_min, y_max = fc.boundary
        t = fc.firewall_thickness
        boxes = []
        if t <= 0:
            return boxes
        if x_min > 0 and not is_coplanar(fc.boundary, L, W, "x_min"):
            boxes.append(pv.Box(bounds=[
                ox + x_min - t/2, ox + x_min + t/2,
                oy + y_min, oy + y_max, z0, z1,
            ]))
        if x_max < L and not is_coplanar(fc.boundary, L, W, "x_max"):
            boxes.append(pv.Box(bounds=[
                ox + x_max - t/2, ox + x_max + t/2,
                oy + y_min, oy + y_max, z0, z1,
            ]))
        if y_min > 0 and not is_coplanar(fc.boundary, L, W, "y_min"):
            boxes.append(pv.Box(bounds=[
                ox + x_min, ox + x_max,
                oy + y_min - t/2, oy + y_min + t/2, z0, z1,
            ]))
        if y_max < W and not is_coplanar(fc.boundary, L, W, "y_max"):
            boxes.append(pv.Box(bounds=[
                ox + x_min, ox + x_max,
                oy + y_max - t/2, oy + y_max + t/2, z0, z1,
            ]))
        return boxes

    def _collect_combustible_boxes(self, fc, fire_compartments, ox, oy, z_offset, per_color: dict):
        """Populate per_color dict: {hex_color: [pv.Box, ...]}."""
        from models.materials import COMBUSTIBLE_LIBRARY
        from models.combustibles import SPECIALIZED_COMPONENTS
        from models.geometry import layout_items_in_fc_cached

        colors = {
            "BROWN": "#8B4513", "RED": "#CD5C5C", "SALMON": "#FA8072",
            "GRAY": "#808080", "KHAKI": "#BDB76B", "IVORY": "#FFFFF0",
            "MAGENTA": "#FF00FF", "ORANGE": "#FFA500",
        }
        material_colors = {
            "ALUMINUM": "#c0c0c0", "STEEL": "#4a5568",
            "JET_FUEL": "#b45309", "SOLID_PROPELLANT": "#dc2626",
            "GASOLINE": "#f59e0b", "ELECTROLYTE": "#06b6d4",
            "WOOD": "#92400e",
        }

        from generators.fds_generator import _compute_sibling_overlaps
        sibling_excl = _compute_sibling_overlaps(fc, fire_compartments)

        all_items = []

        for sc in fc.specialized_components:
            if isinstance(sc, dict) and "key" in sc and "x" not in sc:
                comp = SPECIALIZED_COMPONENTS.get(sc["key"])
                if not comp:
                    continue
                for ci in range(sc.get("count", 1)):
                    all_items.append(self._component_preview_item(comp, sc, ci))

        for cb in fc.combustibles:
            if isinstance(cb, dict) and "key" in cb and "x" not in cb:
                cb_def = COMBUSTIBLE_LIBRARY.get(cb["key"], {})
                if not cb_def:
                    continue
                length = cb_def.get("length", 1.0)
                width = cb_def.get("width", 0.8)
                rotation = cb.get("rotation", 0)
                if rotation == 90:
                    length, width = width, length
                for _ in range(cb.get("count", 1)):
                    all_items.append({
                        "length": length, "width": width,
                        "height": cb_def.get("height", 0.5),
                        "color": cb_def.get("color", "BROWN"),
                         "component_key": None,
                    })

        placed = layout_items_in_fc_cached(
            fc.boundary, all_items, margin=0.5, gap=1.5,
            exclusions=(sibling_excl if sibling_excl else None),
        )

        for item in placed:
            comp_key = item.get("component_key")
            comp = item.get("_comp")
            if comp_key and comp:
                for part in comp.parts:
                    col = material_colors.get(part.material_key, "#CD853F")
                    box = pv.Box(bounds=self._component_part_bounds(item, part, ox, oy, z_offset))
                    per_color.setdefault(col, []).append(box)
            else:
                col = colors.get(item.get("color", "BROWN"), "#CD853F")
                box = pv.Box(bounds=(
                    ox + item["x"], ox + item["x"] + item["length"],
                    oy + item["y"], oy + item["y"] + item["width"],
                    item.get("z", 0) + z_offset,
                    item.get("z", 0) + item["height"] + z_offset,
                ))
                per_color.setdefault(col, []).append(box)

    def _collect_story_combustible_boxes(self, story, ox, oy, z_offset, per_color: dict):
        """Populate per_color dict from story-level combustibles/specialized_components.

        Each entry carries its own ``boundary`` which defines the placement region.
        """
        from models.materials import COMBUSTIBLE_LIBRARY
        from models.combustibles import SPECIALIZED_COMPONENTS
        from models.geometry import layout_items_in_fc_cached

        colors = {
            "BROWN": "#8B4513", "RED": "#CD5C5C", "SALMON": "#FA8072",
            "GRAY": "#808080", "KHAKI": "#BDB76B", "IVORY": "#FFFFF0",
            "MAGENTA": "#FF00FF", "ORANGE": "#FFA500",
        }
        material_colors = {
            "ALUMINUM": "#c0c0c0", "STEEL": "#4a5568",
            "JET_FUEL": "#b45309", "SOLID_PROPELLANT": "#dc2626",
            "GASOLINE": "#f59e0b", "ELECTROLYTE": "#06b6d4",
            "WOOD": "#92400e",
        }

        # Cumulative placed-item exclusions so items from different entries
        # stay at full gap distance from already-placed rectangles.
        placed_excl: list[tuple[float, float, float, float]] = []

        # Story-level specialized_components
        for sc in story.specialized_components:
            boundary = sc.get("boundary")
            if not boundary or not (isinstance(sc, dict) and "key" in sc):
                continue
            comp = SPECIALIZED_COMPONENTS.get(sc["key"])
            if not comp:
                continue
            items = []
            for ci in range(sc.get("count", 1)):
                items.append(self._component_preview_item(comp, sc, ci))
            placed = layout_items_in_fc_cached(
                boundary, items, margin=0.5, gap=1.5,
                exclusions=(placed_excl if placed_excl else None),
            )
            if placed:
                for p in placed:
                    placed_excl.append((
                        p["x"] - 1.0, p["x"] + p["length"] + 1.0,
                        p["y"] - 1.0, p["y"] + p["width"] + 1.0,
                    ))
            for item in placed:
                comp_key = item.get("component_key")
                comp_obj = item.get("_comp")
                if comp_key and comp_obj:
                    for part in comp_obj.parts:
                        col = material_colors.get(part.material_key, "#CD853F")
                        box = pv.Box(bounds=self._component_part_bounds(item, part, ox, oy, z_offset))
                        per_color.setdefault(col, []).append(box)

        # Story-level combustibles
        for cb in story.combustibles:
            boundary = cb.get("boundary")
            if not boundary or not (isinstance(cb, dict) and "key" in cb):
                continue
            cb_def = COMBUSTIBLE_LIBRARY.get(cb["key"], {})
            if not cb_def:
                continue
            length = cb_def.get("length", 1.0)
            width = cb_def.get("width", 0.8)
            rotation = cb.get("rotation", 0)
            if rotation == 90:
                length, width = width, length
            items = []
            for _ in range(cb.get("count", 1)):
                items.append({
                    "length": length, "width": width,
                    "height": cb_def.get("height", 0.5),
                    "color": cb_def.get("color", "BROWN"),
                    "component_key": None,
                })
            placed = layout_items_in_fc_cached(
                boundary, items, margin=0.5, gap=1.5,
                exclusions=(placed_excl if placed_excl else None),
            )
            if placed:
                for p in placed:
                    placed_excl.append((
                        p["x"] - 1.0, p["x"] + p["length"] + 1.0,
                        p["y"] - 1.0, p["y"] + p["width"] + 1.0,
                    ))
            for item in placed:
                col = colors.get(item.get("color", "BROWN"), "#CD853F")
                box = pv.Box(bounds=(
                    ox + item["x"], ox + item["x"] + item["length"],
                    oy + item["y"], oy + item["y"] + item["width"],
                    item.get("z", 0) + z_offset,
                    item.get("z", 0) + item["height"] + z_offset,
                ))
                per_color.setdefault(col, []).append(box)

    def clear_cache(self):
        """Drop all cached bundles and their actors."""
        for bundle in self._building_cache.values():
            for a in bundle.actors.values():
                try:
                    self.plotter.remove_actor(a)
                except Exception:
                    pass
        self._building_cache.clear()

    def _render_heat_source_group(self, bg):
        self._clear_group("heat_source")
        if not bg.buildings:
            return
        self._draw_heat_direction_arrow(
            self._mesh_domain(bg),
            bg.heat_source,
            self._footprint_bounds(bg=bg),
        )

    def _render_slices_devices_group(self, bg, bbox):
        self._clear_group("slices")
        self._clear_group("devices")
        self._draw_slices_and_devices(bg, bg.buildings, *bbox)

    def _render_origin(self, bg):
        self._clear_group("origin")
        self._draw_origin_marker(bg.buildings)

    def _finalize_camera(self, bbox):
        xmin, xmax, ymin, ymax, zmax = bbox
        bbox_w = xmax - xmin
        bbox_d = ymax - ymin
        self.max_dim = max(bbox_w, bbox_d, zmax)
        self.cx = (xmin + xmax) / 2
        self.cy = (ymin + ymax) / 2
        self.cz = zmax / 2
        if self._first_render:
            self.plotter.reset_camera()
            self.setup_camera()
            self._first_render = False
        else:
            self.plotter.reset_camera_clipping_range()

    # ── Public partial-update API ─────────────────────────────
    def update_buildings(self, model):
        self.model = model
        self._bg = self._resolve_building_group(model)
        if not HAS_PYVISTA or model is None:
            return
        self._do_full_render()

    def update_heat_source(self, model):
        self.model = model
        self._bg = self._resolve_building_group(model)
        if not HAS_PYVISTA or model is None:
            return
        if self._fds_scene is not None:
            return
        if self._bg is None or not self._bg.buildings:
            return
        self._render_heat_source_group(self._bg)
        self.plotter.render()

    def update_fds_heat_source(self, heat_source):
        """Update only the direction indicator in the active FDS preview."""
        if not HAS_PYVISTA or self._fds_scene is None:
            return
        self._fds_heat_source = dict(heat_source or {})
        self._clear_group("heat_source")
        self._draw_heat_direction_arrow(
            self._fds_scene.domain,
            self._fds_heat_source,
            self._footprint_bounds(scene=self._fds_scene),
        )
        self.plotter.render()

    @staticmethod
    def _footprint_bounds(bg=None, scene=None):
        """Return the geometry footprint used to place the direction circle."""
        if bg is not None and getattr(bg, "buildings", None):
            xmin = min(b.offset_x for b in bg.buildings)
            xmax = max(b.offset_x + b.length for b in bg.buildings)
            ymin = min(b.offset_y for b in bg.buildings)
            ymax = max(b.offset_y + b.width for b in bg.buildings)
            zmin = 0.0
            zmax = max(
                max((s.z_bottom + s.height for s in b.stories), default=b.height)
                for b in bg.buildings
            )
            return (xmin, xmax, ymin, ymax, zmin, zmax)
        if scene is not None and getattr(scene, "obstacles", None):
            return (
                min(o.xmin for o in scene.obstacles),
                max(o.xmax for o in scene.obstacles),
                min(o.ymin for o in scene.obstacles),
                max(o.ymax for o in scene.obstacles),
                min(o.zmin for o in scene.obstacles),
                max(o.zmax for o in scene.obstacles),
            )
        return None

    def _draw_heat_direction_arrow(
        self,
        bounds,
        heat_source,
        footprint=None,
    ):
        """Draw the radiation arrow on a circular h/2 trajectory."""
        if not bounds or not heat_source:
            return
        azimuth = float(heat_source.get("azimuth", 0.0))
        elevation = float(heat_source.get("elevation", 0.0))
        if float(heat_source.get("net_heat_flux", 0.0)) <= 0:
            return
        to_source = source_orientation(azimuth, elevation)
        to_building = [-value for value in to_source]
        vector_length = sum(value * value for value in to_building) ** 0.5
        if vector_length <= 1e-9:
            return
        to_building = [value / vector_length for value in to_building]

        x0, x1, y0, y1, z0, z1 = bounds
        geometry = footprint or bounds
        gx0, gx1, gy0, gy1, gz0, gz1 = geometry
        geometry_size = max(gx1 - gx0, gy1 - gy0, gz1 - gz0)
        arrow_length = geometry_size * 0.12
        cx = (gx0 + gx1) / 2
        cy = (gy0 + gy1) / 2
        target_z = (gz0 + gz1) / 2
        horizontal = (math.cos(math.radians(azimuth)), -math.sin(math.radians(azimuth)))
        horizontal_length = math.hypot(*horizontal)
        if horizontal_length <= 1e-9:
            return
        horizontal = [value / horizontal_length for value in horizontal]
        support_radius = (
            abs(horizontal[0]) * (gx1 - gx0) / 2
            + abs(horizontal[1]) * (gy1 - gy0) / 2
        )
        radius = support_radius + arrow_length * 0.35
        target = (
            cx + horizontal[0] * radius,
            cy + horizontal[1] * radius,
            target_z,
        )
        start = [
            target[index] - to_building[index] * arrow_length
            for index in range(3)
        ]
        arrow = pv.Arrow(
            start=start,
            direction=to_building,
            scale=arrow_length,
            shaft_radius=0.028,
            tip_radius=0.085,
            tip_length=0.24,
        )
        actor = self.plotter.add_mesh(arrow, color="#ff6f3c")
        self._add_to_group("heat_source", actor)

    def update_slices_devices(self, model):
        self.model = model
        self._bg = self._resolve_building_group(model)
        if not HAS_PYVISTA or model is None:
            return
        bbox = self._compute_bbox_only()
        if bbox is None:
            return
        self._render_slices_devices_group(self._bg, bbox)
        self.plotter.render()

    def _compute_bbox_only(self):
        """Compute (xmin, xmax, ymin, ymax, zmax) without drawing."""
        bg = self._bg
        if bg is None or not bg.buildings:
            return None
        xmin = ymin = float("inf")
        xmax = ymax = zmax = -float("inf")
        for b in bg.buildings:
            ox, L, oy, W = b.boundary
            t = b.wall_thickness
            xmin = min(xmin, ox - t / 2)
            xmax = max(xmax, ox + L + t / 2)
            ymin = min(ymin, oy - t / 2)
            ymax = max(ymax, oy + W + t / 2)
            total_h = 0.0
            for s in b.stories:
                total_h = max(total_h, s.z_bottom + s.height)
            if total_h == 0:
                total_h = b.height
            zmax = max(zmax, total_h)
        if xmin == float("inf"):
            return None
        if zmax == -float("inf"):
            zmax = 3.0
        return (xmin, xmax, ymin, ymax, zmax)

    # ── Drawing helpers ─────────────────────────────────────

    def _draw_origin_marker(self, buildings):
        """Draw origin marker axes using first building's position."""
        if not buildings:
            return
        b0 = buildings[0]
        ox0, L0, oy0, W0 = b0.boundary
        a = max(L0, W0) * 0.1
        a1 = self.plotter.add_mesh(
            pv.Line((ox0, oy0, 0), (ox0 + a, oy0, 0)), color="red", line_width=4
        )
        a2 = self.plotter.add_mesh(
            pv.Line((ox0, oy0, 0), (ox0, oy0 + a, 0)), color="green", line_width=4
        )
        a3 = self.plotter.add_mesh(
            pv.Line((ox0, oy0, 0), (ox0, oy0, a)), color="blue", line_width=4
        )
        a4 = self.plotter.add_mesh(
            pv.Sphere(radius=a * 0.05, center=(ox0, oy0, 0)), color="white"
        )
        for a_ in (a1, a2, a3, a4):
            self._add_to_group("origin", a_)

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

    @staticmethod
    def _mesh_domain(bg):
        """Replicate generators.fds_generator._compute_mesh's domain expansion.

        Returns (x0, x1, y0, y1, z0, z1). Keeps viewer 3D preview geometry in
        sync with the MESH XB used by FDS.
        """
        from generators.fds_generator import FDSGenerator
        try:
            plan = FDSGenerator(bg)._compute_mesh()
            d = plan.domain
            return (d[0], d[1], d[2], d[3], d[4], d[5])
        except Exception:
            pass
        buildings = bg.buildings
        if not buildings:
            return (0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
        x_min = min(b.offset_x - b.wall_thickness / 2 for b in buildings)
        x_max = max(b.offset_x + b.length + b.wall_thickness / 2 for b in buildings)
        y_min = min(b.offset_y - b.wall_thickness / 2 for b in buildings)
        y_max = max(b.offset_y + b.width + b.wall_thickness / 2 for b in buildings)
        z_max = max(sum(s.height for s in b.stories) for b in buildings)
        expand_x = 1.0
        expand_y = 1.0
        expand_z = 1.0
        return (
            x_min - expand_x,
            x_max + expand_x,
            y_min - expand_y,
            y_max + expand_y,
            0.0,
            z_max + expand_z,
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

        # Use MESH domain for slice extent (matches what FDS will compute).
        mx0, mx1, my0, my1, mz0, mz1 = self._mesh_domain(model)
        dx = mx1 - mx0
        dy = my1 - my0
        dz = mz1 - mz0

        if first_cb_center:
            cx, cy, cz = first_cb_center
        else:
            cx, cy, cz = 0, 0, (mz0 + mz1) / 2

        # PyVista Plane: for direction along X or Y, i_size maps to Z extent
        # and j_size maps to the horizontal perpendicular axis.
        try:
            # X-slice (PBX): normal (1,0,0), plane lies in YZ.
            # i_size → Z, j_size → Y.
            sx = pv.Plane(
                center=(cx, (my0 + my1) / 2, (mz0 + mz1) / 2),
                direction=(1, 0, 0),
                i_size=dz,
                j_size=dy,
            )
            a_sx = self.plotter.add_mesh(sx, color="#f9e2af", opacity=0.08, show_edges=False)
            self._add_to_group("slices", a_sx)

            # Y-slice (PBY): normal (0,1,0), plane lies in XZ.
            # i_size → Z, j_size → X.
            sy = pv.Plane(
                center=((mx0 + mx1) / 2, cy, (mz0 + mz1) / 2),
                direction=(0, 1, 0),
                i_size=dz,
                j_size=dx,
            )
            a_sy = self.plotter.add_mesh(sy, color="#a6e3a1", opacity=0.08, show_edges=False)
            self._add_to_group("slices", a_sy)

            # Z-slice (PBZ): normal (0,0,1), plane lies in XY.
            # i_size → X, j_size → Y.
            sz_val = cz + 0.5 if first_cb_center else (mz0 + mz1) / 2
            sz = pv.Plane(
                center=((mx0 + mx1) / 2, (my0 + my1) / 2, sz_val),
                direction=(0, 0, 1),
                i_size=dx,
                j_size=dy,
            )
            a_sz = self.plotter.add_mesh(sz, color="#89b4fa", opacity=0.08, show_edges=False)
            self._add_to_group("slices", a_sz)
        except Exception:
            pass  # pv.Plane may not be available in older versions

        # Device points
        if model.output.get("devices", True):
            if first_cb_center:
                cx, cy, cz = first_cb_center
                a_dev = self.plotter.add_mesh(
                    pv.Sphere(radius=0.3, center=(cx, cy, cz + 0.1)),
                    color="#f38ba8",
                    opacity=0.9,
                )
                self._add_to_group("devices", a_dev)
            for b in buildings:
                bx, bL, by, bW = b.boundary
                b_cx = bx + bL / 2
                b_cy = by + bW / 2
                for story in b.stories:
                    z_mid = story.z_bottom + story.height / 2
                    a_sp = self.plotter.add_mesh(
                        pv.Sphere(radius=0.2, center=(b_cx, b_cy, z_mid)),
                        color="#cba6f7",
                        opacity=0.7,
                    )
                    self._add_to_group("devices", a_sp)

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
