#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Layout helpers for keeping scaled-up buildings from overlapping.

When an equivalent-model building is scaled up to "large", its length/width
expand but its ``boundary[0]`` and ``boundary[2]`` (offset_x / offset_y)
keep their original mid-scale values.  Adjacent buildings originally placed
in a tight grid can then bleed into each other.

``arrange_buildings`` is an *opt-in* helper used by the facility panel /
batch generator (NOT by ``Building.from_dict`` of specialised models).  It
detects overlaps in world coordinates and packs the affected buildings
along the X axis so that no two AABB X-intervals intersect.  Y offsets
stay intact — the layout was originally designed in 2-D, so only the
coordinate the buildings overlap in needs to be repacked.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from models.building import Building


def _bbox(b: Building) -> tuple[float, float, float, float]:
    """Axis-aligned bounding box in world coordinates (excluding walls)."""
    return (
        b.offset_x,
        b.offset_x + b.length,
        b.offset_y,
        b.offset_y + b.width,
    )


def _overlap(a: tuple[float, float], b: tuple[float, float], tol: float = 1e-6) -> float:
    """Positive overlap length along one axis (0 if disjoint)."""
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    return max(0.0, hi - lo)


def has_overlap(buildings: Sequence[Building], tol: float = 0.01) -> bool:
    """True if any two buildings have non-trivial X *and* Y overlap."""
    n = len(buildings)
    for i in range(n):
        ai = _bbox(buildings[i])
        for j in range(i + 1, n):
            aj = _bbox(buildings[j])
            if _overlap((ai[0], ai[1]), (aj[0], aj[1])) > tol and _overlap(
                (ai[2], ai[3]), (aj[2], aj[3])
            ) > tol:
                return True
    return False


def arrange_buildings(
    buildings: Iterable[Building],
    gap: float = 20.0,
    preserve_offsets: bool = False,
) -> list[Building]:
    """Pack *buildings* along the X axis without overlap.

    Strategy:
    1. Sort by current X (offset_x) — keeps relative L-R order.
    2. Walk left to right; if a building would intersect the previous one
       (along both X and Y — only X-move is required) reset its offset_x to
       ``prev_x_max + gap``.
    3. Y offsets are *preserved* unless a building has ``offset_y < 0`` —
       such buildings are lifted to ``offset_y = 0`` so the layout lives in
       the all-positive quadrant the smoke view band expects.

    Returns the input list (mutated in place) for ergonomic chaining.
    """
    items = list(buildings)
    if not items:
        return items

    items.sort(key=lambda b: (b.offset_x, b.offset_y))

    # Lift any negative-Y buildings so the layout doesn't fall below origin.
    min_y = min(b.offset_y for b in items)
    if min_y < 0:
        lift = -min_y
        for b in items:
            b.boundary[2] += lift

    cursor_x = items[0].offset_x
    cursor_right_x = items[0].offset_x + items[0].length

    if preserve_offsets:
        return items

    for i in range(1, len(items)):
        b = items[i]
        desired_left = b.offset_x
        if desired_left < cursor_right_x + gap:
            b.boundary[0] = cursor_right_x + gap
        cursor_right_x = b.offset_x + b.length
        _ = cursor_x  # appease linters; track kept for debug

    return items
