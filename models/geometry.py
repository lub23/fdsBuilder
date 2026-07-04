#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared geometry utilities for coplanar detection and coordinate transforms.

Functions operate on the new dataclass models from models.building.
"""
from __future__ import annotations

import math

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

# Module-level option to (re-)enable console warnings when an item is
# dropped because it cannot fit in the available region.  Default off:
# most drops are intentional (a small FC cannot host the requested
# combustible type), so reason about them in code rather than carpeting
# the console.  Use :func:`last_layout_drops` to get per-key totals.
_LAYOUT_WARNINGS_ENABLED = False
_LAST_DROPS: dict[str, int] = {}


def enable_layout_warnings(enabled: bool = True) -> None:
    global _LAYOUT_WARNINGS_ENABLED
    _LAYOUT_WARNINGS_ENABLED = bool(enabled)


def last_layout_drops() -> dict[str, int]:
    """Return per-key dropped counts from the most recent ``layout_items_in_fc``.

    The dict is reset on each call, so call immediately after a layout
    invocation.  Useful for end-of-build summaries instead of spamming a
    warning per dropped item.
    """
    out = dict(_LAST_DROPS)
    _LAST_DROPS.clear()
    return out


def _record_layout_drop(item: dict, reason: str) -> None:
    key = item.get("key") or "?"
    _LAST_DROPS[key] = _LAST_DROPS.get(key, 0) + 1
    if _LAYOUT_WARNINGS_ENABLED:
        print(f"WARNING: dropped {key} - {reason}")


# ============================================================
# Layout cache — avoids recomputing expensive layout when the
# same (boundary, items, margin, gap, exclusions, spec_bounds)
# are passed again.  Both the 3D viewer and FDS generator call
# the layout functions for the same fire compartments, so this
# cache eliminates the duplicate O(n²) computation.
# ============================================================

_layout_cache: dict[tuple, list[dict]] = {}
_layout_cache_max = 256


def _items_fingerprint(items: list[dict]) -> tuple:
    """Return a hashable fingerprint for a list of layout item dicts.

    Only keys that affect positioning are included: length, width,
    height, key, component_key, _type, _comp class identity,
    rotation, burnable.
    """
    parts: list[tuple] = []
    for it in items:
        comp_id = id(it.get("_comp")) if it.get("_comp") is not None else None
        parts.append((
            round(it.get("length", 0.0), 6),
            round(it.get("width", 0.0), 6),
            round(it.get("height", 0.0), 6),
            it.get("key", ""),
            it.get("component_key"),
            it.get("_type", ""),
            it.get("burnable"),
            it.get("rotation"),
            comp_id,
            it.get("_instance"),
            it.get("_horizontal"),
            it.get("_axis"),
            it.get("_sign"),
        ))
    return tuple(parts)


def _excl_fingerprint(
    exclusions: list[tuple[float, float, float, float]] | None,
) -> tuple:
    """Hashable fingerprint for exclusions list."""
    if exclusions is None:
        return ()
    return tuple((round(a, 6), round(b, 6), round(c, 6), round(d, 6))
                 for a, b, c, d in exclusions)


def _spec_bounds_fingerprint(
    spec_bounds: tuple[float, float, float, float] | None,
) -> tuple:
    """Hashable fingerprint for spec_bounds."""
    if spec_bounds is None:
        return ()
    return tuple(round(v, 6) for v in spec_bounds)


def clear_layout_cache() -> None:
    """Drop all cached layout results.

    Call this when the underlying model changes (e.g. a new facility
    is loaded, or building parameters are edited).
    """
    _layout_cache.clear()


def layout_items_in_fc_cached(
    fc_boundary: list[float],
    items: list[dict],
    margin: float = 0.5,
    gap: float = 0.5,
    exclusions: list[tuple[float, float, float, float]] | None = None,
    spec_bounds: tuple[float, float, float, float] | None = None,
) -> list[dict]:
    """Cached wrapper for :func:`layout_items_in_fc`.

    On cache hit, returns a deep-copied result so callers can mutate
    (e.g. add ``x``, ``y`` keys downstream) without corrupting the
    cache.  On cache miss, delegates to :func:`layout_items_in_fc`
    and stores a deep copy.
    """
    import copy as _copy
    key = (
        tuple(round(v, 6) for v in fc_boundary),
        _items_fingerprint(items),
        round(margin, 6),
        round(gap, 6),
        _excl_fingerprint(exclusions),
        _spec_bounds_fingerprint(spec_bounds),
    )
    hit = _layout_cache.get(key)
    if hit is not None:
        return _copy.deepcopy(hit)

    result = layout_items_in_fc(
        fc_boundary, items, margin=margin, gap=gap,
        exclusions=exclusions, spec_bounds=spec_bounds,
    )
    # Cache a deep copy so the original can be mutated by callers.
    _layout_cache[key] = _copy.deepcopy(result)
    # Evict oldest if cache is too large.
    if len(_layout_cache) > _layout_cache_max:
        oldest = next(iter(_layout_cache))
        _layout_cache.pop(oldest)
    return result


def auto_fill_rect_cached(
    rect: tuple[float, float, float, float],
    item_defs: list[dict],
    margin: float = 0.5,
    min_gap: float = 0.5,
    require_burnable: bool = True,
) -> list[dict]:
    """Cached wrapper for :func:`auto_fill_rect`.

    Same semantics as :func:`auto_fill_rect` but avoids recomputation
    when the same (rect, item_defs, margin, min_gap, require_burnable)
    are seen again.
    """
    import copy as _copy
    key = (
        tuple(round(v, 6) for v in rect),
        _items_fingerprint(item_defs),
        round(margin, 6),
        round(min_gap, 6),
        require_burnable,
    )
    hit = _layout_cache.get(key)
    if hit is not None:
        return _copy.deepcopy(hit)

    result = auto_fill_rect(
        rect, item_defs, margin=margin, min_gap=min_gap,
        require_burnable=require_burnable,
    )
    _layout_cache[key] = _copy.deepcopy(result)
    if len(_layout_cache) > _layout_cache_max:
        oldest = next(iter(_layout_cache))
        _layout_cache.pop(oldest)
    return result


def partition_free_areas(
    boundaries: list[list[float]],
    exclude_rects: list[tuple[float, float, float, float]] | None = None,
    min_strip: float = 0.5,
    min_area: float = 4.0,
    inset: float = 0.0,
) -> list[tuple[float, float, float, float]]:
    """Carve the union of *boundaries* into axis-aligned rectangles not
    covered by *exclude_rects*.

    Practical use: given a rectangular building footprint and a list of
    fire compartments that occupy overlapping sub-rectangles, return a
    list of axis-aligned rectangles that together cover (approximately)
    the remaining free area.  Each output rect represents a region that
    the layout algorithm can fill independently with no risk of items
    overlapping a sibling FC or neighbouring free-area chunk.

    Parameters
    ----------
    boundaries : list of [x1, x2, y1, y2]
        Outermost container rectangles; their union is the layout canvas.
        Handles >1 polygon (e.g. multi-building bounds) by processing the
        unioned bounding rect of each.
    exclude_rects : list of [x1, x2, y1, y2]
        Inner rectangles that consume the canvas (e.g. fire compartments).
        Returned rectangles are **clipped** so they don't intrude into
        any of those.
    min_strip, min_area : float
        Discard rectangles whose width or height falls below *min_strip* or
        whose area below *min_area* — physically too small to host any
        item (will silently drop in :func:`layout_items_in_fc`).
    inset : float, default 0
        Shrink every emitted rectangle by ``inset`` on each side, leaving
        *inset* metres of clearance from neighbours.  Useful when the
        caller wants each chunk to lay out items independently and have
        a no-overlap buffer between chunks.

    Algorithm
    ---------
    A two-axis sweep:
    1. Build a sorted list of distinct x-coordinates drawn from both the
       canvas and the exclude rects.
    2. For every adjacent x-pair, build a strip of width ``dx`` running the
       whole y-extent of the canvas; within that strip, walk distinct
       y-coordinates and reject sub-strips intersecting any exclude rect.
    Returns rectangles sorted by area, descending.
    """
    rects: list[tuple[float, float, float, float]] = []
    if not boundaries:
        return rects
    excl = list(exclude_rects or [])

    for b in boundaries:
        bx1, bx2, by1, by2 = b
        if bx2 - bx1 <= 0 or by2 - by1 <= 0:
            continue

        # Distinct x coordinates within canvas ∪ exclude rects intersecting
        # the canvas's y-bounds.
        x_anchors: set[float] = {bx1, bx2}
        for ex1, ex2, ey1, ey2 in excl:
            if ey2 <= by1 or ey1 >= by2:
                continue  # exclude rect doesn't overlap this canvas's y
            x_anchors.add(max(bx1, ex1))
            x_anchors.add(min(bx2, ex2))
        xs = sorted(x_anchors)

        for i in range(len(xs) - 1):
            x0_, x1_ = xs[i], xs[i + 1]
            if x1_ - x0_ < min_strip:
                continue

            # Find free y-strips within this x strip.
            y_anchors: set[float] = {by1, by2}
            for ex1, ex2, ey1, ey2 in excl:
                if ex2 <= x0_ or ex1 >= x1_:
                    continue  # exclude rect doesn't intersect this x strip
                y_anchors.add(max(by1, ey1))
                y_anchors.add(min(by2, ey2))
            ys = sorted(y_anchors)

            for j in range(len(ys) - 1):
                y0_, y1_ = ys[j], ys[j + 1]
                if y1_ - y0_ < min_strip:
                    continue
                # Test this sub-rect against all excludes
                clip_used = False
                for ex1, ex2, ey1, ey2 in excl:
                    if ex1 >= x1_ or ex2 <= x0_ or ey1 >= y1_ or ey2 <= y0_:
                        continue
                    # Intersection: shrink the sub-rect
                    # If exclude is just an early/late edge along one axis
                    # we may still have free area to the other side.
                    # Strategy: if exclude covers entire strip in x,
                    # break the strip on y; if covers entire strip in y,
                    # break the strip on x; otherwise the strip is fully
                    # covered (no free area in this sub-rect).
                    if ex1 <= x0_ and ex2 >= x1_:
                        # Full x coverage — drop this sub-rect
                        clip_used = True
                        break
                    if ey1 <= y0_ and ey2 >= y1_:
                        clip_used = True
                        break
                if clip_used:
                    continue
                # Apply optional inset for chunk-to-chunk clearance padding.
                ix0 = x0_ + inset
                ix1 = x1_ - inset
                iy0 = y0_ + inset
                iy1 = y1_ - inset
                if ix1 - ix0 < min_strip or iy1 - iy0 < min_strip:
                    continue
                area = (ix1 - ix0) * (iy1 - iy0)
                if area >= min_area:
                    rects.append((ix0, ix1, iy0, iy1))

    rects.sort(key=lambda r: -(r[1] - r[0]) * (r[3] - r[2]))
    return rects


def auto_fill_rect(
    rect: tuple[float, float, float, float],
    item_defs: list[dict],
    margin: float = 0.5,
    min_gap: float = 0.5,
    require_burnable: bool = True,
) -> list[dict]:
    """Auto-place the best-fitting items inside an axis-aligned rectangle.

    For each rectangle in turn, the function:
    1. Filters *item_defs* to those that physically fit the rectangle's
       inner area (with margin = *margin*).
    2. Filters by ``require_burnable`` (defaults to True: only items with
       ``burnable=True`` are considered — metals etc. are not in scope).
    3. Computes how many of each item would fill the rectangle (cols *
       rows), picks the type with the largest item count (proxy for
       coverage).  Ties broken by largest single item area.
    4. Returns a list of N copies of that item ready for
       :func:`layout_items_in_fc` to position uniformly.

    If no item fits, returns an empty list silently (no warning).

    *item_defs* are dicts like::

        {"key": "WOODEN_PALLET", "length": 3.0, "width": 1.8,
         "height": 1.6, "name": "...", "_type": "combustible",
         "burnable": True}
    """
    out: list[dict] = []
    x0_, x1_, y0_, y1_ = rect
    inner_L = x1_ - x0_
    inner_W = y1_ - y0_
    avail_L = inner_L - 2 * margin
    avail_W = inner_W - 2 * margin
    if avail_L < 0.5 or avail_W < 0.5:
        return out  # too small to ever fit anything

    best_def = None
    best_count = 0
    best_l = 0
    best_w = 0
    best_height = 0.5

    for it in item_defs:
        if require_burnable and not it.get("burnable", False):
            continue
        L = float(it.get("length", 0))
        W = float(it.get("width", 0))
        H = float(it.get("height", 0))
        if L <= 0 or W <= 0:
            continue
        # Try both orientations: in case L>W doesn't fit, attempting W>L
        # gives us a second chance.
        candidates = [(L, W), (W, L)]
        for l_, w_ in candidates:
            if l_ + min_gap > avail_L or w_ + min_gap > avail_W:
                continue
            cols = max(1, int((avail_L + min_gap) // (l_ + min_gap)))
            rows = max(1, int((avail_W + min_gap) // (w_ + min_gap)))
            count = cols * rows
            if count >= 1 and (best_def is None or count > best_count
                                or (count == best_count and l_ * w_ > best_l * best_w)):
                best_def = it
                best_count = count
                best_l = l_
                best_w = w_
                best_height = H

    if best_def is None:
        return out
    payload = {
        "key": best_def.get("key", "?"),
        "name": best_def.get("name", best_def.get("key", "?")),
        "length": best_l,
        "width": best_w,
        "height": best_height,
        "_type": best_def.get("_type", "combustible"),
    }
    for _ in range(best_count):
        out.append(dict(payload))
    return out


def best_fit_for_target(
    rect: tuple[float, float, float, float],
    item_defs: list[dict],
    target_count: int,
    margin: float = 0.5,
    min_gap: float = 0.5,
    require_burnable: bool = True,
) -> tuple[str | None, tuple[float, float, float] | None, int]:
    """Pick the best (item-type, orientation, placement count) triple such
    that the user-supplied ``target_count`` is **honoured**: the returned
    placement count ``n`` satisfies ``target_count <= n <= max(target_count,
    capacity)``, where ``capacity`` is the largest the chosen item can fit
    inside the rect (cols x rows grid).

    Returns ``(key, (l_, w_, h_), n)`` or ``(None, None, 0)`` when nothing
    fits.
    """
    x0_, x1_, y0_, y1_ = rect
    inner_L = x1_ - x0_
    inner_W = y1_ - y0_
    avail_L = inner_L - 2 * margin
    avail_W = inner_W - 2 * margin
    if avail_L < 0.5 or avail_W < 0.5 or target_count <= 0:
        return None, None, 0

    best: tuple[str | None, tuple[float, float, float] | None, int] = (None, None, 0)
    # We want to find the item type whose capacity is closest to (>=)
    # target_count, breaking ties in this priority:
    # 1. Largest "n >= target_count"  (so user count is honoured).
    # 2. If no item fits the full target, fall back to the largest capacity
    #    that fits at least *anything*.
    for it in item_defs:
        if require_burnable and not it.get("burnable", False):
            continue
        L = float(it.get("length", 0))
        W = float(it.get("width", 0))
        H = float(it.get("height", 0))
        if L <= 0 or W <= 0:
            continue
        for l_, w_ in [(L, W), (W, L)]:
            if l_ + min_gap > avail_L or w_ + min_gap > avail_W:
                continue
            cols = max(1, int((avail_L + min_gap) // (l_ + min_gap)))
            rows = max(1, int((avail_W + min_gap) // (w_ + min_gap)))
            cap = cols * rows
            if cap < 1:
                continue
            current_key, _, current_n = best
            if current_key is None:
                if cap >= target_count:
                    best = (it.get("key", "?"), (l_, w_, H), target_count)
                else:
                    best = (it.get("key", "?"), (l_, w_, H), cap)
                continue
            # Prefer item that honours target first
            cap_honours = cap >= target_count
            current_honours = current_n >= target_count
            if cap_honours and not current_honours:
                best = (it.get("key", "?"), (l_, w_, H), target_count)
            elif cap_honours == current_honours:
                # Same honour status: prefer larger n, but never exceed
                # the requested target beyond a 25 % head-room — we want
                # enough items to feel populated but not soup.
                candidate_n = min(cap, max(target_count, int(1.25 * target_count)))
                chosen_n = min(current_n, max(target_count, int(1.25 * target_count)))
                if candidate_n > chosen_n:
                    best = (it.get("key", "?"), (l_, w_, H), min(cap, max(target_count, int(1.25 * target_count))))

    if best[0] is None:
        return None, None, 0
    return best


def fill_rect_targeted(
    rect: tuple[float, float, float, float],
    item_defs: list[dict],
    target_count: int,
    margin: float = 0.5,
    min_gap: float = 0.5,
    require_burnable: bool = True,
) -> list[dict]:
    """Return a list with approximately ``target_count`` copies of the best
    fitting item for ``rect``.

    Caller can still pass a single type to enforce it (only that type is
    in *item_defs*); in multi-type scenarios the type whose grid capacity
    is closest to (≥) the target is picked, with a clamp at ``target *
    1.25`` so we don't overcrowd.

    Returns an empty list silently if nothing fits.
    """
    key, dims, n = best_fit_for_target(
        rect, item_defs, target_count,
        margin=margin, min_gap=min_gap, require_burnable=require_burnable,
    )
    if key is None or dims is None or n <= 0:
        return []
    l_, w_, h_ = dims
    out: list[dict] = []
    for it in item_defs:
        if it.get("key", "?") != key:
            continue
        payload = {
            "key": key,
            "name": it.get("name", key),
            "length": l_,
            "width": w_,
            "height": h_,
            "_type": it.get("_type", "combustible"),
        }
        break
    else:
        payload = {"key": key, "name": key, "length": l_, "width": w_,
                    "height": h_, "_type": "combustible"}
    for _ in range(n):
        out.append(dict(payload))
    return out


def rotate_layout_to_rect(
    rect: tuple[float, float, float, float],
    items: list[dict],
    margin: float = 0.5,
    min_gap: float = 0.5,
) -> list[dict]:
    """Rotate item dimensions so they sit lengthwise along *rect*'s long
    axis.

    Useful when an irregular rectangle is wider than tall — fires spread
    better along the long axis.
    """
    out: list[dict] = []
    _, _, y0_, y1_ = rect
    if y1_ - y0_ > (rect[1] - rect[0]):
        for it in items:
            n = dict(it)
            n["length"], n["width"] = it.get("width", 0), it.get("length", 0)
            out.append(n)
        return out
    return list(items)

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
    spec_bounds: tuple[float, float, float, float] | None = None,
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
    # Reset per-call drop counters so callers can inspect drops for this
    # single layout invocation via :func:`last_layout_drops`.
    _LAST_DROPS.clear()
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
            spec_bounds_internal = _bounding_box(placed)
        else:
            spec_bounds_internal = None
        _place_spread(placed, combustibles, x_min, y_min, fc_L, fc_W,
                      margin, spec_bounds_internal, exclusions=exclusions,
                      min_gap=gap)

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

    # Nothing fits — count drops silently unless verbose is on
    for it in temp:
        _record_layout_drop(it, "no space after exclusions")

def _place_spread(
    out,
    items,
    x_min,
    y_min,
    fc_L,
    fc_W,
    margin,
    spec_bounds,
    exclusions=None,
    min_gap=0.6,
):
    """Distribute items in a FC using a geometric hand-placement scheme.

    Goal:  let each item occupy as much space as it can.  For small item
    counts this becomes a symmetric constellation (centre / plus-shaped /
    quads / Quincunx) where every item sits on a corner-to-centre mid-point
    so distances are maximised.  For larger counts the scheme degrades into
    a refined grid that's been jittered to break row/column alignment and
    pushed apart so identical items don't cluster.
    """
    if not items:
        return
    n = len(items)

    avail_x = fc_L - 2 * margin
    avail_y = fc_W - 2 * margin
    if avail_x <= 0 or avail_y <= 0:
        return

    x_left = x_min + margin
    x_right = x_min + fc_L - margin
    y_bot = y_min + margin
    y_top = y_min + fc_W - margin
    cx_cent = (x_left + x_right) / 2
    cy_cent = (y_bot + y_top) / 2

    if n >= 9 and spec_bounds is None and not exclusions:
        first_l = float(items[0]["length"])
        first_w = float(items[0]["width"])
        if all(
            abs(float(it["length"]) - first_l) < 1e-9
            and abs(float(it["width"]) - first_w) < 1e-9
            for it in items
        ):
            for L, W in ((first_l, first_w), (first_w, first_l)):
                if avail_x < L or avail_y < W:
                    continue
                max_cols = int((avail_x + min_gap) // (L + min_gap))
                max_rows = int((avail_y + min_gap) // (W + min_gap))
                if max_cols <= 0 or max_rows <= 0 or max_cols * max_rows < n:
                    continue
                cols = min(max_cols, n)
                rows = math.ceil(n / cols)
                if rows > max_rows:
                    rows = max_rows
                    cols = math.ceil(n / rows)
                if cols > max_cols:
                    continue
                gap_x = (avail_x - cols * L) / (cols - 1) if cols > 1 else 0.0
                gap_y = (avail_y - rows * W) / (rows - 1) if rows > 1 else 0.0
                if (cols > 1 and gap_x < min_gap - 1e-9) or (
                    rows > 1 and gap_y < min_gap - 1e-9
                ):
                    continue
                for idx, item in enumerate(items):
                    row = idx // cols
                    col = idx % cols
                    new_item = dict(item)
                    new_item["length"] = L
                    new_item["width"] = W
                    new_item["x"] = x_left + col * (L + gap_x)
                    new_item["y"] = y_bot + row * (W + gap_y)
                    new_item["z"] = 0
                    out.append(new_item)
                return

    # Hand-built position set, in item-centre coordinates.
    positions = []

    def _linspace(a, b, n):
        if n <= 0: return []
        if n == 1: return [a]
        step = (b - a) / (n - 1)
        return [a + i * step for i in range(n)]

    def _add(px, py):
        if x_left + 1e-3 < px < x_right - 1e-3                 and y_bot + 1e-3 < py < y_top - 1e-3:
            positions.append((px, py))
        else:
            positions.append((max(x_left + 1e-3, min(x_right - 1e-3, px)),
                              max(y_bot + 1e-3, min(y_top - 1e-3, py))))

    # Avg item envelope for Lloyd spacing target.
    if items:
        avg_l = sum(it["length"] for it in items) / len(items)
        avg_w = sum(it["width"] for it in items) / len(items)
    else:
        avg_l = avg_w = 0.0
    min_sep = avg_l + avg_w
    target_sep = min_sep + min_gap + 0.5

    # Build dense candidate grid of valid item-centre positions.
    candidates = []

    # Symmetric hand-placed anchors biased first.
    if n >= 1:
        candidates.append((x_left + 0.50 * avail_x, y_bot + 0.50 * avail_y))
    if n >= 4:
        # 4 corner midpoints
        candidates.append((x_left + 0.18 * avail_x, y_bot + 0.18 * avail_y))
        candidates.append((x_right - 0.18 * avail_x, y_bot + 0.18 * avail_y))
        candidates.append((x_left + 0.18 * avail_x, y_top - 0.18 * avail_y))
        candidates.append((x_right - 0.18 * avail_x, y_top - 0.18 * avail_y))
    if n == 5:
        # 5 = 4 corners + centre
        candidates.append((x_left + 0.50 * avail_x, y_bot + 0.50 * avail_y))
    if n >= 6 and n <= 8:
        # 4 edge midpoints
        candidates.append((x_left + 0.50 * avail_x, y_bot + 0.18 * avail_y))
        candidates.append((x_right - 0.50 * avail_x, y_bot + 0.18 * avail_y))
        candidates.append((x_left + 0.50 * avail_x, y_top - 0.18 * avail_y))
        candidates.append((x_right - 0.50 * avail_x, y_top - 0.18 * avail_y))
    if n == 8:
        candidates.append((x_left + 0.50 * avail_x, y_bot + 0.50 * avail_y))
        candidates.append((x_right - 0.50 * avail_x, y_top - 0.50 * avail_y))

    # Dense grid for the rest.
    if n > len(candidates):
        Ly_max = max((it["width"] for it in items), default=0)
        Lx_max = max((it["length"] for it in items), default=0)
        # Generate plenty of grid candidates — at least n + slack.
        target_count = max(int(n * 2.5), n + 8, 16)
        step_x = max(min(avail_x, avail_y) / max(target_count, 4), Lx_max * 0.25, 0.4)
        step_y = max(min(avail_x, avail_y) / max(target_count, 4), Ly_max * 0.25, 0.4)
        gx = x_left + Lx_max / 2
        last_gx = None
        while gx < x_right - Lx_max / 2 + 1e-9:
            gy = y_bot + Ly_max / 2
            while gy < y_top - Ly_max / 2 + 1e-9:
                candidates.append((round(gx, 3), round(gy, 3)))
                gy += step_y
            if last_gx is not None and abs(gx - last_gx) < 1e-9:
                break
            last_gx = gx
            gx += step_x

    # Greedy max-min: ALWAYS pick the next available candidate that has
    # the maximum min-distance to the already-chosen set.  This produces
    # ~ symmetric corner-first placements and falls back to the dense grid
    # automatically when n is large.
    seen = set()
    unique_candidates = []
    for c in candidates:
        key = (round(c[0], 2), round(c[1], 2))
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(c)
    candidates = unique_candidates

    chosen_ = []
    for _ in range(n):
        if not candidates:
            break
        # Pick the candidate with the maximum min-distance to existing chosen.
        if not chosen_:
            best = candidates.pop(0)
        else:
            best_score = -1.0
            best_idx = 0
            for i, cand in enumerate(candidates):
                md = min(math.hypot(cand[0] - p[0], cand[1] - p[1]) for p in chosen_)
                if md > best_score:
                    best_score = md
                    best_idx = i
            best = candidates.pop(best_idx)
        chosen_.append(best)
    positions = chosen_

# (min_sep computed above)
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            ax, ay = positions[i]
            bx, by = positions[j]
            dx = bx - ax
            dy = by - ay
            d = math.hypot(dx, dy)
            if d < 1e-3:
                continue
            if d < target_sep:
                push = (target_sep - d) / d * 0.5
                positions[i] = (ax - dx * push, ay - dy * push)
                positions[j] = (bx + dx * push, by + dy * push)

    # Sort items by size descending so the biggest item gets first pick.
    items_sorted = sorted(items, key=lambda it: -(it["length"] * it["width"]))

    placements = []
    placed_rects = []
    for pi, item in enumerate(items_sorted):
        if pi >= len(positions):
            _record_layout_drop(item, "no candidate position")
            continue
        cx, cy_ = positions[pi]
        L, W = item["length"], item["width"]

        # Hard reject: item must fully fit in any placement within the
        # margin-inset rectangle (no clamping tricks).  Try swapping L↔W
        # if the natural orientation can't fit anywhere.
        if (avail_x < L or avail_y < W) and (avail_x < W or avail_y < L):
            _record_layout_drop(item, "item does not fit within margin")
            continue
        swapped = False
        if avail_x < L or avail_y < W:
            L, W = W, L  # swap to make it fit
            swapped = True

        ix1 = cx - L / 2
        ix2 = ix1 + L
        iy1 = cy_ - W / 2
        iy2 = iy1 + W
        if ix1 < x_left:
            ix2 += x_left - ix1
            ix1 = x_left
        if ix2 > x_right:
            ix1 -= ix2 - x_right
            ix2 = x_right
        if iy1 < y_bot:
            iy2 += y_bot - iy1
            iy1 = y_bot
        if iy2 > y_top:
            iy1 -= iy2 - y_top
            iy2 = y_top
        if spec_bounds is not None:
            sx1, sx2, sy1, sy2 = spec_bounds
            if ix1 <= sx2 and ix2 >= sx1 and iy1 <= sy2 and iy2 >= sy1:
                _record_layout_drop(item, "overlaps specialized component")
                continue
        if exclusions is not None:
            hit = False
            for ex1_min, ex1_max, ey1_min, ey1_max in exclusions:
                if ix1 < ex1_max + min_gap and ix2 > ex1_min - min_gap \
                        and iy1 < ey1_max + min_gap and iy2 > ey1_min - min_gap:
                    hit = True
                    break
            if hit:
                _record_layout_drop(item, "overlaps exclusion")
                continue
        hit = False
        for pr in placed_rects:
            pr_ix1, pr_ix2, pr_iy1, pr_iy2 = pr
            if (ix1 < pr_ix2 + min_gap and ix2 > pr_ix1 - min_gap
                    and iy1 < pr_iy2 + min_gap and iy2 > pr_iy1 - min_gap):
                hit = True
                break
        if hit:
            _record_layout_drop(item, "overlaps another item")
            continue
        placements.append(item)
        placed_rects.append((ix1, ix2, iy1, iy2))
        new_item = dict(item)
        new_item["length"] = L
        new_item["width"] = W
        if swapped and new_item.get("_type") == "component" and not new_item.get("_horizontal"):
            new_item["_rotate_xy"] = not bool(new_item.get("_rotate_xy"))
        new_item["x"] = ix1
        new_item["y"] = iy1
        new_item["z"] = 0
        out.append(new_item)



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
