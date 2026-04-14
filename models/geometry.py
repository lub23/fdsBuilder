#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared geometry utilities for coplanar detection and coordinate transforms.

Functions operate on the new dataclass models from models.building.
"""
from __future__ import annotations

from models.building import Opening

# Valid wall identifiers
_VALID_WALLS = {"x_min", "x_max", "y_min", "y_max"}


def _validate_wall_id(wall_id: str) -> None:
    if wall_id not in _VALID_WALLS:
        raise ValueError(
            f"Invalid wall_id {wall_id!r}. Must be one of {sorted(_VALID_WALLS)}."
        )


# ============================================================
# Wall length helpers
# ============================================================

def wall_length_for_fc(fc_boundary: list[float], wall_id: str) -> float:
    """Return the length of a wall segment within a fire compartment.

    fc_boundary = [x_min, x_max, y_min, y_max].
    x walls (x_min, x_max) -> y_max - y_min.
    y walls (y_min, y_max) -> x_max - x_min.
    """
    _validate_wall_id(wall_id)
    x_min, x_max, y_min, y_max = fc_boundary
    if wall_id.startswith("x"):
        return y_max - y_min
    else:
        return x_max - x_min


def wall_length_for_building(building_boundary: list[float], wall_id: str) -> float:
    """Return the length of an exterior wall of a building.

    building_boundary = [offset_x, length, offset_y, width].
    y walls (y_min, y_max) -> length.
    x walls (x_min, x_max) -> width.
    """
    _validate_wall_id(wall_id)
    _offset_x, length, _offset_y, width = building_boundary
    if wall_id.startswith("y"):
        return length
    else:
        return width


# ============================================================
# Coplanar detection
# ============================================================

def is_coplanar(
    fc_boundary: list[float],
    building_length: float,
    building_width: float,
    wall_id: str,
    tol: float = 1e-6,
) -> bool:
    """Check whether a fire compartment wall lies on the building boundary.

    x_min==0, x_max==building_length, y_min==0, y_max==building_width.
    """
    _validate_wall_id(wall_id)
    x_min, x_max, y_min, y_max = fc_boundary
    checks = {
        "x_min": (x_min, 0.0),
        "x_max": (x_max, building_length),
        "y_min": (y_min, 0.0),
        "y_max": (y_max, building_width),
    }
    val, target = checks[wall_id]
    return abs(val - target) < tol


def fc_wall_start_offset(fc_boundary: list[float], wall_id: str) -> float:
    """Return the start offset of a wall segment within building-local coords.

    y_min/y_max walls: return x_min  (the wall runs along x, starts at x_min).
    x_min/x_max walls: return y_min  (the wall runs along y, starts at y_min).
    """
    _validate_wall_id(wall_id)
    x_min, _x_max, y_min, _y_max = fc_boundary
    if wall_id.startswith("y"):
        return x_min
    else:
        return y_min


def detect_coplanar_openings(building, story) -> list:
    """Detect fire-compartment openings on walls coplanar with the building exterior.

    For each coplanar opening found, a *new* Opening is created with
    boundary[0] shifted by fc_wall_start_offset so that it is expressed
    in building-level coordinates.

    Returns:
        list[Opening]: Openings suitable for punching holes in the building
        exterior walls.
    """
    result: list[Opening] = []
    bld_length = building.boundary[1]
    bld_width = building.boundary[3]

    for fc in story.fire_compartments:
        for opening in fc.openings:
            wall_id = opening.wall
            if not is_coplanar(fc.boundary, bld_length, bld_width, wall_id):
                continue
            # Build shifted copy
            shift = fc_wall_start_offset(fc.boundary, wall_id)
            new_boundary = list(opening.boundary)
            new_boundary[0] += shift
            result.append(Opening(
                wall=opening.wall,
                type=opening.type,
                boundary=new_boundary,
            ))
    return result


# ============================================================
# Offset resolution
# ============================================================

def resolve_negative_offset(w_offset: float, width: float, wall_length: float) -> float:
    """Resolve a possibly-negative wall offset to a positive one.

    Negative offsets are measured from the far end of the wall:
        wall_length + w_offset - width.
    Positive (or zero) offsets are returned unchanged.
    """
    if w_offset < 0:
        return wall_length + w_offset - width
    return w_offset


# ============================================================
# World-coordinate conversion
# ============================================================

def opening_to_world_coords(
    opening,
    building,
    story,
    is_exterior: bool = True,
) -> tuple:
    """Convert an Opening to world coordinates [x1, x2, y1, y2, z1, z2].

    For *exterior* openings the wall plane is on the building boundary.
    For *interior* (is_exterior=False) the wall plane is on the first
    fire compartment whose boundary matches the opening's wall_id.

    Args:
        opening:     Opening instance with .wall and .boundary.
        building:    Building instance with .boundary.
        story:       Story instance with .z_bottom and .fire_compartments.
        is_exterior: If True, reference the building boundary for the wall
                     plane coordinate.  If False, use the FC boundary.

    Returns:
        (x1, x2, y1, y2, z1, z2)
    """
    w_offset, width, h_offset, height = opening.boundary
    wall_id = opening.wall
    offset_x, bld_length, offset_y, bld_width = building.boundary
    z_bottom = story.z_bottom

    z1 = z_bottom + h_offset
    z2 = z_bottom + h_offset + height

    if is_exterior:
        # Wall plane coordinate comes from the building boundary.
        if wall_id == "y_min":
            x1 = offset_x + w_offset
            x2 = offset_x + w_offset + width
            y1 = y2 = offset_y
        elif wall_id == "y_max":
            x1 = offset_x + w_offset
            x2 = offset_x + w_offset + width
            y1 = y2 = offset_y + bld_width
        elif wall_id == "x_min":
            x1 = x2 = offset_x
            y1 = offset_y + w_offset
            y2 = offset_y + w_offset + width
        else:  # x_max
            x1 = x2 = offset_x + bld_length
            y1 = offset_y + w_offset
            y2 = offset_y + w_offset + width
    else:
        # Interior: find FC boundary for the wall plane coordinate.
        fc_boundary = _find_fc_boundary(story, wall_id)
        fc_x_min, fc_x_max, fc_y_min, fc_y_max = fc_boundary

        if wall_id == "y_min":
            x1 = offset_x + w_offset
            x2 = offset_x + w_offset + width
            y1 = y2 = offset_y + fc_y_min
        elif wall_id == "y_max":
            x1 = offset_x + w_offset
            x2 = offset_x + w_offset + width
            y1 = y2 = offset_y + fc_y_max
        elif wall_id == "x_min":
            x1 = x2 = offset_x + fc_x_min
            y1 = offset_y + w_offset
            y2 = offset_y + w_offset + width
        else:  # x_max
            x1 = x2 = offset_x + fc_x_max
            y1 = offset_y + w_offset
            y2 = offset_y + w_offset + width

    return (x1, x2, y1, y2, z1, z2)


def _find_fc_boundary(story, wall_id: str) -> list[float]:
    """Find the first FC boundary matching the wall_id in the story."""
    for fc in story.fire_compartments:
        return fc.boundary
    # Fallback: no FCs -- return zeros
    return [0, 0, 0, 0]


# ============================================================
# Opening boundary validation
# ============================================================

def validate_opening_bounds(
    opening, wall_length: float, story_height: float
) -> list[str]:
    """Validate that an opening fits within its wall segment.

    Returns list of error messages (empty = valid).
    """
    errors = []
    w_off, w, h_off, h = opening.boundary

    # Resolve negative offset
    if w_off < 0:
        w_off = resolve_negative_offset(w_off, w, wall_length)

    if w_off < -0.001:
        errors.append(f"Opening w_offset ({w_off:.2f}) is negative")
    if w_off + w > wall_length + 0.001:
        errors.append(
            f"Opening exceeds wall length: w_offset({w_off:.2f}) + width({w:.2f})"
            f" = {w_off + w:.2f} > wall_length({wall_length:.2f})"
        )
    if h_off < -0.001:
        errors.append(f"Opening h_offset ({h_off:.2f}) is negative")
    if h_off + h > story_height + 0.001:
        errors.append(
            f"Opening exceeds story height: h_offset({h_off:.2f}) + height({h:.2f})"
            f" = {h_off + h:.2f} > story_height({story_height:.2f})"
        )
    return errors


def validate_building(building) -> list[str]:
    """Validate all openings in a building. Returns list of error messages."""
    errors = []

    for si, story in enumerate(building.stories):
        # Story-level exterior openings
        for oi, opening in enumerate(story.openings):
            wall_len = wall_length_for_building(building.boundary, opening.wall)
            errs = validate_opening_bounds(opening, wall_len, story.height)
            for e in errs:
                errors.append(f"Story {story.name}, exterior opening {oi}: {e}")

        # FC openings
        for fc in story.fire_compartments:
            for oi, opening in enumerate(fc.openings):
                wall_len = wall_length_for_fc(fc.boundary, opening.wall)
                errs = validate_opening_bounds(opening, wall_len, story.height)
                for e in errs:
                    errors.append(
                        f"Story {story.name}, FC '{fc.name}', opening {oi}: {e}"
                    )
    return errors
