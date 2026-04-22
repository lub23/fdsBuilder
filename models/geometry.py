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
    fc_boundary: list[float] | None = None,
) -> tuple:
    """Convert an Opening to world coordinates [x1, x2, y1, y2, z1, z2].

    For *exterior* openings the wall plane is on the building boundary.
    For *interior* (is_exterior=False) the wall plane is on the fire
    compartment boundary given by *fc_boundary*.  If *fc_boundary* is
    ``None``, falls back to the first FC in the story.

    Args:
        opening:     Opening instance with .wall and .boundary.
        building:    Building instance with .boundary.
        story:       Story instance with .z_bottom and .fire_compartments.
        is_exterior: If True, reference the building boundary for the wall
                     plane coordinate.  If False, use the FC boundary.
        fc_boundary: Explicit FC boundary for interior openings.

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
        # Interior: use explicit FC boundary or fallback to first FC.
        if fc_boundary is None:
            fc_boundary = _find_fc_boundary(story, wall_id)
        fc_x_min, fc_x_max, fc_y_min, fc_y_max = fc_boundary

        if wall_id == "y_min":
            x1 = offset_x + fc_x_min + w_offset
            x2 = offset_x + fc_x_min + w_offset + width
            y1 = y2 = offset_y + fc_y_min
        elif wall_id == "y_max":
            x1 = offset_x + fc_x_min + w_offset
            x2 = offset_x + fc_x_min + w_offset + width
            y1 = y2 = offset_y + fc_y_max
        elif wall_id == "x_min":
            x1 = x2 = offset_x + fc_x_min
            y1 = offset_y + fc_y_min + w_offset
            y2 = offset_y + fc_y_min + w_offset + width
        else:  # x_max
            x1 = x2 = offset_x + fc_x_max
            y1 = offset_y + fc_y_min + w_offset
            y2 = offset_y + fc_y_min + w_offset + width

    return (x1, x2, y1, y2, z1, z2)


def _find_fc_boundary(story, wall_id: str) -> list[float]:
    """Find the first FC boundary matching the wall_id in the story."""
    for fc in story.fire_compartments:
        return fc.boundary
    # Fallback: no FCs -- return zeros
    return [0, 0, 0, 0]


# ============================================================
# Layout helpers for combustibles and specialized components
# ============================================================

def _is_specialized(item: dict) -> bool:
    """Check if an item is a specialized component."""
    return item.get("_type") == "component" or bool(item.get("component_key"))


def _intersects_any(
    rect: tuple[float, float, float, float],
    exclusions: list[tuple[float, float, float, float]] | None,
    tol: float = 1e-6,
) -> bool:
    """Return True if rect = (x1, x2, y1, y2) overlaps any exclusion box."""
    if not exclusions:
        return False
    x1, x2, y1, y2 = rect
    for ex1, ex2, ey1, ey2 in exclusions:
        if x1 < ex2 - tol and x2 > ex1 + tol and y1 < ey2 - tol and y2 > ey1 + tol:
            return True
    return False


def layout_items_in_fc(
    fc_boundary: list[float],
    items: list[dict],
    margin: float = 0.5,
    gap: float = 0.5,
    exclusions: list[tuple[float, float, float, float]] | None = None,
) -> list[dict]:
    """Lay out rectangular items in a fire compartment.

    Specialized components are placed compactly and centered.
    Combustibles are spread evenly to fill the available space.

    Each item in *items* must have keys: ``length``, ``width``, ``height``,
    plus any extra keys (``color``, ``key``, etc.) that will be passed through.

    *exclusions* is an optional list of (x1, x2, y1, y2) rectangles (in
    building-local coords) that items must not overlap — used to keep items
    in an outer compartment out of nested sibling compartments.

    Returns a new list of dicts with ``x``, ``y``, ``z`` positions added
    (in building-local coordinates).
    """
    x_min, x_max, y_min, y_max = fc_boundary
    fc_L = x_max - x_min
    fc_W = y_max - y_min

    specialized = [it for it in items if _is_specialized(it)]
    combustibles = [it for it in items if not _is_specialized(it)]

    placed: list[dict] = []

    # 1. Specialized components — compact placement, then centered
    if specialized:
        _place_centered(placed, specialized, x_min, y_min, fc_L, fc_W,
                        margin, gap, exclusions=exclusions)

    # 2. Combustibles — spread evenly to fill the space
    if combustibles:
        spec_bounds = None
        if specialized and placed:
            spec_bounds = _bounding_box(placed)
        _place_spread(placed, combustibles, x_min, y_min, fc_L, fc_W,
                      margin, spec_bounds, exclusions=exclusions)

    return placed


def _bounding_box(placed_items: list[dict]) -> tuple[float, float, float, float]:
    """Return (x_min, x_max, y_min, y_max) of placed items."""
    xs_min = min(it["x"] for it in placed_items)
    xs_max = max(it["x"] + it["length"] for it in placed_items)
    ys_min = min(it["y"] for it in placed_items)
    ys_max = max(it["y"] + it["width"] for it in placed_items)
    return xs_min, xs_max, ys_min, ys_max


def _place_centered(
    out: list[dict],
    items: list[dict],
    x_min: float, y_min: float,
    fc_L: float, fc_W: float,
    margin: float, gap: float,
    exclusions: list[tuple[float, float, float, float]] | None = None,
):
    """Place items compactly, then shift the group to center in the FC.

    If the centered group would overlap any exclusion zone, search for the
    first grid offset (step 0.5 m) where the whole group fits; otherwise
    drop the items with a WARNING.
    """
    primary = "x" if fc_L >= fc_W else "y"
    temp: list[dict] = []
    _place_grid(temp, items, 0, 0, fc_L, fc_W, margin, gap, primary)

    if not temp:
        return

    # Compute bounding box of placed group (relative to 0,0)
    gx_min = min(it["x"] for it in temp)
    gx_max = max(it["x"] + it["length"] for it in temp)
    gy_min = min(it["y"] for it in temp)
    gy_max = max(it["y"] + it["width"] for it in temp)

    group_w = gx_max - gx_min
    group_h = gy_max - gy_min

    def _shift_fits(off_x: float, off_y: float) -> bool:
        if exclusions is None:
            return True
        for it in temp:
            rx1 = it["x"] + off_x
            rx2 = rx1 + it["length"]
            ry1 = it["y"] + off_y
            ry2 = ry1 + it["width"]
            if _intersects_any((rx1, rx2, ry1, ry2), exclusions):
                return False
        return True

    def _apply(off_x: float, off_y: float):
        for it in temp:
            new_item = dict(it)
            new_item["x"] = it["x"] + off_x
            new_item["y"] = it["y"] + off_y
            out.append(new_item)

    # First try centered placement (current behavior)
    off_x = x_min + (fc_L - group_w) / 2 - gx_min
    off_y = y_min + (fc_W - group_h) / 2 - gy_min
    if _shift_fits(off_x, off_y):
        _apply(off_x, off_y)
        return

    # Fallback: scan grid positions on a 0.5 m step looking for a free slot
    step = 0.5
    max_ox = x_min + fc_L - group_w - margin
    max_oy = y_min + fc_W - group_h - margin
    oy_start = x_start = None
    oy = y_min + margin
    while oy <= max_oy + 1e-9:
        ox = x_min + margin
        while ox <= max_ox + 1e-9:
            cand_off_x = ox - gx_min
            cand_off_y = oy - gy_min
            if _shift_fits(cand_off_x, cand_off_y):
                _apply(cand_off_x, cand_off_y)
                return
            ox += step
        oy += step

    # Nothing fits — warn and drop all
    for it in temp:
        print(
            f"WARNING: dropped specialized component "
            f"{it.get('key', '?')} - no space after exclusions"
        )


def _place_spread(
    out: list[dict],
    items: list[dict],
    x_min: float, y_min: float,
    fc_L: float, fc_W: float,
    margin: float,
    spec_bounds: tuple[float, float, float, float] | None,
    exclusions: list[tuple[float, float, float, float]] | None = None,
):
    """Distribute items evenly across the FC to fill the space.

    If *spec_bounds* is given, skip positions that overlap with that region.
    If *exclusions* is given, skip positions that overlap any exclusion box
    (e.g. nested sibling compartments); items that cannot be placed
    anywhere are dropped with a WARNING.
    """
    if not items:
        return

    n = len(items)
    # Use the average item size for grid calculation
    avg_l = sum(it["length"] for it in items) / n
    avg_w = sum(it["width"] for it in items) / n

    avail_x = fc_L - 2 * margin
    avail_y = fc_W - 2 * margin

    if avail_x <= 0 or avail_y <= 0:
        return

    # Determine grid dimensions: find cols x rows that best fills the space
    best_cols, best_rows = 1, n
    best_ratio_diff = float("inf")

    fc_aspect = avail_x / avail_y if avail_y > 0 else 1.0

    for cols in range(1, n + 1):
        rows = -(-n // cols)  # ceil division
        # Aspect ratio of this grid layout
        grid_aspect = (cols * avg_l) / (rows * avg_w) if rows * avg_w > 0 else 1.0
        diff = abs(grid_aspect - fc_aspect)
        if diff < best_ratio_diff:
            best_ratio_diff = diff
            best_cols, best_rows = cols, rows

    cols, rows = best_cols, best_rows

    # Calculate even spacing: distribute gaps so items fill the space
    gap_x = (avail_x - cols * avg_l) / (cols + 1) if cols > 0 else 0
    gap_y = (avail_y - rows * avg_w) / (rows + 1) if rows > 0 else 0
    gap_x = max(gap_x, 0.3)
    gap_y = max(gap_y, 0.3)

    # Recalculate actual total span and center it
    total_x = cols * avg_l + (cols + 1) * gap_x
    total_y = rows * avg_w + (rows + 1) * gap_y
    start_x = x_min + (fc_L - total_x) / 2
    start_y = y_min + (fc_W - total_y) / 2

    idx = 0
    for row in range(rows):
        for col in range(cols):
            if idx >= n:
                break
            cx = start_x + gap_x + col * (avg_l + gap_x)
            cy = start_y + gap_y + row * (avg_w + gap_y)

            item = items[idx]
            ix1, ix2 = cx, cx + item["length"]
            iy1, iy2 = cy, cy + item["width"]

            # Skip if overlapping with specialized component region
            if spec_bounds is not None:
                sx1, sx2, sy1, sy2 = spec_bounds
                if ix1 < sx2 and ix2 > sx1 and iy1 < sy2 and iy2 > sy1:
                    # Overlap — skip this grid cell, don't consume item
                    continue

            # Skip if overlapping any exclusion zone
            if _intersects_any((ix1, ix2, iy1, iy2), exclusions):
                continue

            new_item = dict(item)
            new_item["x"] = cx
            new_item["y"] = cy
            new_item["z"] = 0
            out.append(new_item)
            idx += 1
        if idx >= n:
            break

    # Any items that didn't fit in the grid after exclusions: try a fallback
    # scan at 0.5 m step and greedily place each remaining item in the first
    # free slot. Only items that still don't fit are dropped with WARNING.
    if exclusions and idx < n:
        placed_rects = [_placed_item_rect(p) for p in out]
        step = 0.5
        while idx < n:
            item = items[idx]
            L_i, W_i = item["length"], item["width"]
            found = False
            oy = y_min + margin
            while oy + W_i <= y_min + fc_W - margin + 1e-9 and not found:
                ox = x_min + margin
                while ox + L_i <= x_min + fc_L - margin + 1e-9 and not found:
                    rect = (ox, ox + L_i, oy, oy + W_i)
                    # Reject if hits exclusion, spec region, or already-placed item
                    if _intersects_any(rect, exclusions):
                        ox += step
                        continue
                    if spec_bounds is not None:
                        sx1, sx2, sy1, sy2 = spec_bounds
                        if (rect[0] < sx2 and rect[1] > sx1
                                and rect[2] < sy2 and rect[3] > sy1):
                            ox += step
                            continue
                    if any(_boxes_overlap_rect(rect, pr) for pr in placed_rects):
                        ox += step
                        continue
                    # Place it here
                    new_item = dict(item)
                    new_item["x"] = ox
                    new_item["y"] = oy
                    new_item["z"] = 0
                    out.append(new_item)
                    placed_rects.append(rect)
                    found = True
                oy += step
            if not found:
                print(
                    f"WARNING: dropped {item.get('key', '?')} - "
                    f"no space after exclusions"
                )
            idx += 1


def _placed_item_rect(item):
    return (
        item["x"],
        item["x"] + item["length"],
        item["y"],
        item["y"] + item["width"],
    )


def _boxes_overlap_rect(a, b, tol=1e-6):
    ax1, ax2, ay1, ay2 = a
    bx1, bx2, by1, by2 = b
    return (
        ax1 < bx2 - tol
        and ax2 > bx1 + tol
        and ay1 < by2 - tol
        and ay2 > by1 + tol
    )


def _place_grid(
    out: list[dict],
    items: list[dict],
    x_min: float, y_min: float,
    fc_L: float, fc_W: float,
    margin: float, gap: float,
    primary: str,
):
    """Pack items compactly in rows along the primary axis."""
    cursor_primary = margin
    cursor_secondary = margin
    row_max_secondary = 0.0

    for item in items:
        il = item["length"]  # item X size
        iw = item["width"]   # item Y size

        if primary == "x":
            p_size, s_size = il, iw
            p_limit, s_limit = fc_L, fc_W
        else:
            p_size, s_size = iw, il
            p_limit, s_limit = fc_W, fc_L

        # Does it fit on current row?
        if cursor_primary + p_size > p_limit - margin:
            # Move to next row
            cursor_primary = margin
            cursor_secondary += row_max_secondary + gap
            row_max_secondary = 0.0

        # Does it fit in the secondary direction at all?
        if cursor_secondary + s_size > s_limit - margin:
            continue  # drop item — doesn't fit

        # Also check primary still fits
        if cursor_primary + p_size > p_limit - margin:
            continue  # single item wider than FC — drop

        if primary == "x":
            local_x = x_min + cursor_primary
            local_y = y_min + cursor_secondary
        else:
            local_x = x_min + cursor_secondary
            local_y = y_min + cursor_primary

        new_item = dict(item)
        new_item["x"] = local_x
        new_item["y"] = local_y
        new_item["z"] = 0
        out.append(new_item)

        row_max_secondary = max(row_max_secondary, s_size)
        cursor_primary += p_size + gap


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
