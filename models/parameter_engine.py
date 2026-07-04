#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ParameterEngine: expand equivalent-model templates into Building objects.

An equivalent model template stores building dimensions as ranges and
story layouts as ratio-based templates.  ParameterEngine resolves ranges,
expands fire-compartment ratios into absolute coordinates, distributes
exterior openings evenly, and produces a fully formed Building instance.

Scale support:
- ``scale_idx`` field in params selects among {0: small, 1: medium, -1: large}.
- For each combustible / specialized_component in a fire compartment, the
  template may declare an OPTIONAL ``count_scaled`` list
  ``[small, medium, large]``.  When present, the engine picks the entry at
  the requested index; otherwise it falls back to the legacy ``count``.
- The engine also auto-scales ``count`` by ``count_multiplier`` if the
  facility-level ``scale_overrides`` block provides one (see
  ``default_scale_overrides``).
"""
from __future__ import annotations

from models.building import Building, Story, FireCompartment, Opening, Roof


# Index constants for ``scale_idx`` lookup --- consistent with the UI combo
# (``小`` -> 0, ``中`` -> 1, ``大`` -> 2).  Negative values get normalised by
# ``normalise_scale_idx``.
SCALE_SMALL = 0
SCALE_MEDIUM = 1
SCALE_LARGE = 2

SCALE_LABELS = {SCALE_SMALL: "small", SCALE_MEDIUM: "medium", SCALE_LARGE: "large"}


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
    # Scale helpers
    # ------------------------------------------------------------------
    @staticmethod
    def normalise_scale_idx(scale_idx: int) -> int:
        """Map legacy negative indices to canonical ``{0,1,2}``.

        ``-1`` (the old UI value for "大") becomes ``SCALE_LARGE`` (2).  Any
        other negative value falls back to medium.
        """
        if scale_idx is None:
            return SCALE_MEDIUM
        if scale_idx in (SCALE_SMALL, SCALE_MEDIUM, SCALE_LARGE):
            return scale_idx
        if scale_idx < 0:
            return SCALE_LARGE
        # Out-of-range positive -> medium (safe default)
        return SCALE_MEDIUM

    @staticmethod
    def default_scale_overrides() -> dict:
        """Reasonable defaults for scales that aren't explicitly overridden.

        ``fuel_density`` is the multiplier on fuel ``count`` for each scale
        when ``count_scaled`` is NOT provided.  ``fuel_size_multiplier``
        scales fuel linear dimensions (length / width / height) so fuel
        packages track mesh-cell resolution across scales.
        Specialised-component heights are NOT scaled by this multiplier
        (they have explicit ``size_class`` and must fit under the roof).
        """
        return {
            "small":  {"fuel_density": 0.6, "fuel_size_multiplier": 0.6},
            "medium": {"fuel_density": 1.0, "fuel_size_multiplier": 1.0},
            "large":  {"fuel_density": 1.6, "fuel_size_multiplier": 1.4},
        }

    @staticmethod
    def resolve_fuel_count(
        entry: dict,
        scale_idx: int,
        density_multiplier: float | None = None,
    ) -> int:
        """Decide how many items of a fuel/component to emit for this scale.

        Precedence:
        1. ``count_scaled`` (length-3 tuple ``[small, medium, large]``)
        2. ``count`` multiplied by ``density_multiplier`` (if provided)
        3. ``count`` unchanged.

        Result is rounded to the nearest integer (min 1 when source > 0).
        """
        scale_idx = ParameterEngine.normalise_scale_idx(scale_idx)

        if "count_scaled" in entry and isinstance(entry["count_scaled"], (list, tuple)):
            cs = entry["count_scaled"]
            if len(cs) >= 3 and cs[scale_idx] is not None:
                return max(0, int(round(float(cs[scale_idx]))))
            if len(cs) == 1 and cs[0] is not None:
                return max(0, int(round(float(cs[0]))))

        raw = entry.get("count", 0) or 0
        if density_multiplier is not None and density_multiplier > 0 and raw:
            return max(1, int(round(float(raw) * float(density_multiplier))))
        return max(0, int(round(float(raw))))

    # ------------------------------------------------------------------
    # Public generator
    # ------------------------------------------------------------------
    @staticmethod
    def generate(template_building: dict, params: dict,
                 current_offset: tuple[float, float] | None = None) -> Building:
        """Expand a template building dict into a fully formed Building.

        Args:
            template_building: dict from equivalent-model JSON, containing
                ``stories_template``, ``*_range`` fields, etc.
            params: concrete parameters, e.g.
                ``{"length": 85.0, "width": 32.5, "height": 10.0, "stories": 3,
                  "scale_idx": 1,  # 0=small, 1=medium, 2=large (default medium)
                  "fuel_density": 1.0,  # optional multiplier override
                  "fuel_size_multiplier": 1.0}  # optional multiplier override
                ``
            current_offset: optional (offset_x, offset_y) to preserve
                existing building position; otherwise uses template boundary.

        Returns:
            A Building instance with stories, fire compartments, openings,
            and z-offsets populated.
        """
        length = params["length"]
        width = params["width"]
        height = params["height"]
        num_stories = int(params["stories"])

        scale_idx = ParameterEngine.normalise_scale_idx(params.get("scale_idx", 1))
        fuel_density = params.get("fuel_density")
        fuel_size_multiplier = params.get("fuel_size_multiplier")

        templates = template_building.get("stories_template", [])
        story_height = height / num_stories if num_stories > 0 else height

        stories: list[Story] = []
        for i in range(num_stories):
            # Pick the template for this story (clamp to last available)
            tmpl = templates[min(i, len(templates) - 1)] if templates else {}

            # Expand template into an absolute-value story dict
            story_dict = ParameterEngine._expand_story_template(
                tmpl, length, width, story_height,
                scale_idx=scale_idx,
                fuel_density=fuel_density,
                fuel_size_multiplier=fuel_size_multiplier,
            )

            # Override story name to be sequential
            story_dict["name"] = f"{i + 1}F"
            # Override story height to be evenly divided
            story_dict["height"] = story_height

            story = Story.from_dict(story_dict)
            stories.append(story)

        # Read boundary offset from template or preserve existing
        template_boundary = template_building.get("boundary", [0, 0, 0, 0])
        if current_offset is not None:
            offset_x = current_offset[0]
            offset_y = current_offset[1]
        else:
            offset_x = template_boundary[0]
            offset_y = template_boundary[2] if len(template_boundary) > 2 else 0

        building = Building(
            name=template_building.get("name", ""),
            cn_name=template_building.get("cn_name", ""),
            boundary=[offset_x, length, offset_y, width],
            wall_thickness=template_building.get("wall_thickness", 0.5),
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
        scale_idx: int = 1,
        fuel_density: float | None = None,
        fuel_size_multiplier: float | None = None,
    ) -> dict:
        """Expand a ``stories_template`` entry into an absolute-value story dict.

        Handles:
        - ``fire_compartment_ratios`` -> ``fire_compartments``
        - ``opening_templates`` -> ``openings`` inside each FC
        - ``doors``/``windows`` -> story-level exterior ``openings``
        - ``roof`` pass-through

        ``scale_idx``, ``fuel_density`` and ``fuel_size_multiplier`` propagate
        the per-scale resolution of ``count`` / ``count_scaled`` in
        combustibles and specialised_components.
        """
        fuel_size_multiplier = fuel_size_multiplier if (
            fuel_size_multiplier and fuel_size_multiplier > 0
        ) else 1.0
        scale_idx = ParameterEngine.normalise_scale_idx(scale_idx)

        def _absolute_boundary(entry: dict) -> list[float] | None:
            ratio = entry.get("boundary_ratio")
            if isinstance(ratio, (list, tuple)) and len(ratio) >= 4:
                return [
                    float(ratio[0]) * length,
                    float(ratio[1]) * length,
                    float(ratio[2]) * width,
                    float(ratio[3]) * width,
                ]
            boundary = entry.get("boundary")
            if isinstance(boundary, (list, tuple)) and len(boundary) >= 4:
                return [float(v) for v in boundary[:4]]
            return None

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

            # Scale-aware combustibles / specialised components
            scaled_combustibles = []
            for cb in fc_tmpl.get("combustibles", []):
                cb2 = dict(cb)
                cb2["count"] = ParameterEngine.resolve_fuel_count(
                    cb, scale_idx=scale_idx, density_multiplier=fuel_density
                )
                if fuel_size_multiplier != 1.0:
                    cb2["size_multiplier"] = fuel_size_multiplier
                scaled_combustibles.append(cb2)

            scaled_components = []
            for sc in fc_tmpl.get("specialized_components", []):
                sc2 = dict(sc)
                sc2["count"] = ParameterEngine.resolve_fuel_count(
                    sc, scale_idx=scale_idx, density_multiplier=None
                )
                scaled_components.append(sc2)

            fire_compartments.append({
                "name": fc_tmpl.get("name", ""),
                "boundary": fc_boundary,
                "firewall_thickness": fc_tmpl.get("firewall_thickness", 0.5),
                "firewall_material": fc_tmpl.get("firewall_material", "CONCRETE"),
                "openings": fc_openings,
                "combustibles": scaled_combustibles,
                "specialized_components": scaled_components,
            })

        # --- Story-level combustibles / specialised components ---
        # These sit outside individual fire compartments.  Downstream 3D and
        # FDS generation already consume absolute ``boundary`` rectangles, so
        # equivalent templates may declare either ``boundary`` or
        # ``boundary_ratio`` here.
        story_combustibles = []
        for cb in tmpl.get("combustibles", []):
            cb2 = dict(cb)
            boundary = _absolute_boundary(cb)
            if boundary is not None:
                cb2["boundary"] = boundary
            cb2["count"] = ParameterEngine.resolve_fuel_count(
                cb, scale_idx=scale_idx, density_multiplier=fuel_density
            )
            if fuel_size_multiplier != 1.0:
                cb2["size_multiplier"] = fuel_size_multiplier
            story_combustibles.append(cb2)

        story_components = []
        for sc in tmpl.get("specialized_components", []):
            sc2 = dict(sc)
            boundary = _absolute_boundary(sc)
            if boundary is not None:
                sc2["boundary"] = boundary
            sc2["count"] = ParameterEngine.resolve_fuel_count(
                sc, scale_idx=scale_idx, density_multiplier=None
            )
            story_components.append(sc2)

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
            "combustibles": story_combustibles,
            "specialized_components": story_components,
            "roof": tmpl.get("roof", {"thickness": 0.5, "material": "CONCRETE", "openings": []}),
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
