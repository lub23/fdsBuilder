#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ParameterEngine: expand equivalent-model templates into Building objects.

An equivalent model template stores building dimensions as ranges and
story layouts as ratio-based templates.  ParameterEngine resolves ranges,
expands fire-compartment ratios into absolute coordinates, distributes
exterior openings evenly, and produces a fully formed Building instance.
"""
from __future__ import annotations

from models.building import Building, Story, FireCompartment, Opening, Roof


class ParameterEngine:
    """Static helpers for equivalent-model template expansion."""

    # ------------------------------------------------------------------
    # Range resolution
    # ------------------------------------------------------------------
    @staticmethod
    def resolve_range(r: list) -> float:
        """Resolve a range spec to a single value.

        [min, max]          -> (min + max) / 2
        [min, max, default] -> default
        """
        if len(r) >= 3:
            return float(r[2])
        return (r[0] + r[1]) / 2.0

    # ------------------------------------------------------------------
    # Public generator
    # ------------------------------------------------------------------
    @staticmethod
    def generate(template_building: dict, params: dict) -> Building:
        """Expand a template building dict into a fully formed Building.

        Args:
            template_building: dict from equivalent-model JSON, containing
                ``stories_template``, ``*_range`` fields, etc.
            params: concrete parameters, e.g.
                ``{"length": 85.0, "width": 32.5, "height": 10.0, "stories": 3}``

        Returns:
            A Building instance with stories, fire compartments, openings,
            and z-offsets populated.
        """
        length = params["length"]
        width = params["width"]
        height = params["height"]
        num_stories = int(params["stories"])

        templates = template_building.get("stories_template", [])
        story_height = height / num_stories if num_stories > 0 else height

        stories: list[Story] = []
        for i in range(num_stories):
            # Pick the template for this story (clamp to last available)
            tmpl = templates[min(i, len(templates) - 1)] if templates else {}

            # Expand template into an absolute-value story dict
            story_dict = ParameterEngine._expand_story_template(
                tmpl, length, width, story_height
            )

            # Override story name to be sequential
            story_dict["name"] = f"{i + 1}F"
            # Override story height to be evenly divided
            story_dict["height"] = story_height

            story = Story.from_dict(story_dict)
            stories.append(story)

        # Read boundary offset from template
        template_boundary = template_building.get("boundary", [0, 0, 0, 0])
        offset_x = template_boundary[0]
        offset_y = template_boundary[2] if len(template_boundary) > 2 else 0

        building = Building(
            name=template_building.get("name", ""),
            cn_name=template_building.get("cn_name", ""),
            boundary=[offset_x, length, offset_y, width],
            wall_thickness=template_building.get("wall_thickness", 0.24),
            height=height,
            stories=stories,
        )
        building.update_z_offsets()
        return building

    # ------------------------------------------------------------------
    # Story template expansion
    # ------------------------------------------------------------------
    @staticmethod
    def _expand_story_template(
        tmpl: dict,
        length: float,
        width: float,
        story_height: float,
    ) -> dict:
        """Expand a ``stories_template`` entry into an absolute-value story dict.

        Handles:
        - ``fire_compartment_ratios`` -> ``fire_compartments``
        - ``opening_templates`` -> ``openings`` inside each FC
        - ``doors``/``windows`` -> story-level exterior ``openings``
        - ``roof`` pass-through
        """
        # --- Fire compartments ---
        fire_compartments: list[dict] = []
        for fc_tmpl in tmpl.get("fire_compartment_ratios", []):
            ratio = fc_tmpl["boundary_ratio"]
            fc_boundary = [
                ratio[0] * length,
                ratio[1] * length,
                ratio[2] * width,
                ratio[3] * width,
            ]

            # Expand opening_templates for this FC
            fc_openings: list[dict] = []
            for ot in fc_tmpl.get("opening_templates", []):
                wall_id = ot["wall"]
                wall_len = ParameterEngine._wall_length(fc_boundary, wall_id)
                w_offset = ot["w_offset_ratio"] * wall_len
                w = ot["width_ratio"] * wall_len
                # Clamp height to story height
                h = min(ot["height"], story_height)
                fc_openings.append({
                    "wall": wall_id,
                    "type": ot["type"],
                    "boundary": [w_offset, w, ot["h_offset"], h],
                })

            fire_compartments.append({
                "name": fc_tmpl.get("name", ""),
                "boundary": fc_boundary,
                "firewall_thickness": fc_tmpl.get("firewall_thickness", 0.3),
                "firewall_material": fc_tmpl.get("firewall_material", "CONCRETE"),
                "openings": fc_openings,
                "combustibles": fc_tmpl.get("combustibles", []),
                "specialized_components": fc_tmpl.get("specialized_components", []),
            })

        # --- Exterior openings (doors/windows) ---
        exterior_openings = ParameterEngine._distribute_exterior_openings(
            tmpl, length, width, story_height
        )

        # --- Assemble story dict ---
        story_dict: dict = {
            "name": tmpl.get("name", "1F"),
            "height": story_height,
            "fire_compartments": fire_compartments,
            "openings": exterior_openings,
            "roof": tmpl.get("roof", {"thickness": 0.2, "material": "CONCRETE", "openings": []}),
        }
        return story_dict

    # ------------------------------------------------------------------
    # Wall length helper for FC boundaries
    # ------------------------------------------------------------------
    @staticmethod
    def _wall_length(fc_boundary: list[float], wall: str) -> float:
        """Return the length of a wall within a fire compartment.

        x_min / x_max walls: y_max - y_min.
        y_min / y_max walls: x_max - x_min.
        """
        x_min, x_max, y_min, y_max = fc_boundary
        if wall.startswith("x"):
            return y_max - y_min
        return x_max - x_min

    # ------------------------------------------------------------------
    # Exterior opening distribution
    # ------------------------------------------------------------------
    @staticmethod
    def _distribute_exterior_openings(
        tmpl: dict,
        length: float,
        width: float,
        story_height: float,
    ) -> list[dict]:
        """Distribute doors and windows evenly along exterior walls.

        Doors are placed on y_min and y_max walls (wall_len = length).
        Windows are placed on x_min and x_max walls (wall_len = width).

        Spacing for *n* openings on a wall of length *L*::

            spacing = L / (n + 1)
            center_i = spacing * (i + 1)
            w_offset_i = center_i - w / 2

        h_offset: 0 for doors, story_height * 0.4 for windows.

        Returns:
            list of dicts, each ``{"wall": str, "type": str, "boundary": [w_offset, w, h_offset, h]}``.
        """
        result: list[dict] = []

        # --- Doors on y_min / y_max ---
        doors_tmpl = tmpl.get("doors")
        if doors_tmpl:
            w = ParameterEngine.resolve_range(doors_tmpl["width"])
            h = ParameterEngine.resolve_range(doors_tmpl["height"])
            count = int(ParameterEngine.resolve_range(doors_tmpl["count"]))
            wall_len = length  # y walls run along x -> length
            # Clamp height to story height
            h = min(h, story_height)
            # Skip if door wider than wall
            if w > 0 and h > 0 and w <= wall_len:
                for wall_id in ("y_min", "y_max"):
                    if count > 0:
                        spacing = wall_len / (count + 1)
                        for i in range(count):
                            center = spacing * (i + 1)
                            w_offset = max(0.0, center - w / 2)
                            # Clamp to wall bounds
                            if w_offset + w > wall_len:
                                w_offset = wall_len - w
                            result.append({
                                "wall": wall_id,
                                "type": "door",
                                "boundary": [w_offset, w, 0.0, h],
                            })

        # --- Windows on x_min / x_max ---
        windows_tmpl = tmpl.get("windows")
        if windows_tmpl:
            w = ParameterEngine.resolve_range(windows_tmpl["width"])
            h = ParameterEngine.resolve_range(windows_tmpl["height"])
            count = int(ParameterEngine.resolve_range(windows_tmpl["count"]))
            wall_len = width  # x walls run along y -> width
            h_offset = story_height * 0.4
            # Clamp height to story height
            h = min(h, story_height - h_offset)
            if w > 0 and h > 0 and w <= wall_len:
                for wall_id in ("x_min", "x_max"):
                    if count > 0:
                        spacing = wall_len / (count + 1)
                        for i in range(count):
                            center = spacing * (i + 1)
                            w_offset = max(0.0, center - w / 2)
                            if w_offset + w > wall_len:
                                w_offset = wall_len - w
                        result.append({
                            "wall": wall_id,
                            "type": "window",
                            "boundary": [w_offset, w, h_offset, h],
                        })

        return result
