"""Occlusion calculation: count of taller buildings between target and heat source.

The heat source is placed outside the facility bounding box at a fixed radial
offset matching the FDS domain padding (3 m distance + 15 m mesh margin = 18 m).
"""

from __future__ import annotations

import math
from typing import Tuple

from .building import Building
from .facility import Facility


FIXED_SOURCE_OFFSET: float = 18.0  # meters; matches fds_generator.py

# Max perpendicular distance (meters) from target-source line for a building
# to count as "on the line". Deliberately permissive so buildings partially on
# the line still count.
OCCLUSION_LATERAL_TOLERANCE: float = 5.0


def _azimuth_direction(azimuth_deg: float) -> Tuple[float, float]:
    """Compass convention: az=0 is +x (XMAX), increases clockwise.

    Returns unit (dx, dy).
    """
    rad = math.radians(azimuth_deg)
    return (math.cos(rad), -math.sin(rad))


def heat_source_position(facility: Facility, azimuth: float) -> Tuple[float, float]:
    """World-space (x, y) of the heat source given facility + azimuth.

    Source sits at the bbox edge (projected along azimuth direction) + FIXED_SOURCE_OFFSET.
    """
    cx, cy = facility.center
    xmin, xmax, ymin, ymax = facility.bbox
    hx = (xmax - xmin) / 2.0
    hy = (ymax - ymin) / 2.0
    dx, dy = _azimuth_direction(azimuth)
    radius = abs(hx * dx) + abs(hy * dy)
    return (cx + dx * (radius + FIXED_SOURCE_OFFSET), cy + dy * (radius + FIXED_SOURCE_OFFSET))


def _point_line_distance(
    p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]
) -> float:
    """Shortest distance from point p to the segment ab."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    closest_x = ax + t * dx
    closest_y = ay + t * dy
    return math.hypot(px - closest_x, py - closest_y)


def occluding_higher_count(
    facility: Facility, target: Building, azimuth: float
) -> int:
    """Count of OTHER buildings taller than `target` that sit on the
    target → heat_source line (within OCCLUSION_LATERAL_TOLERANCE)."""
    source = heat_source_position(facility, azimuth)
    target_center = (target.center_x, target.center_y)
    count = 0
    for b in facility.buildings:
        if b is target:
            continue
        if b.height <= target.height:
            continue
        b_center = (b.center_x, b.center_y)
        d_target_src = math.hypot(
            source[0] - target_center[0], source[1] - target_center[1]
        )
        d_b_src = math.hypot(source[0] - b_center[0], source[1] - b_center[1])
        if d_b_src >= d_target_src:
            continue
        if _point_line_distance(b_center, target_center, source) > OCCLUSION_LATERAL_TOLERANCE:
            continue
        count += 1
    return count
