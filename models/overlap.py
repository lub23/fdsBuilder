#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OBST overlap detection and resolution.

Priority levels (lower = higher priority):
  0 = wall (external/internal/fire partition)
  1 = stairwell
  2 = specialized component
  3 = regular combustible
"""
from dataclasses import dataclass
from typing import List

PRIORITY_WALL = 0
PRIORITY_STAIRWELL = 1
PRIORITY_COMPONENT = 2
PRIORITY_COMBUSTIBLE = 3


@dataclass
class OBSTEntry:
    x1: float
    x2: float
    y1: float
    y2: float
    z1: float
    z2: float
    priority: int
    source_id: str
    source_type: str  # "wall", "stairwell", "component", "combustible"

    @property
    def size_x(self):
        return self.x2 - self.x1

    @property
    def size_y(self):
        return self.y2 - self.y1


def check_overlap(a: OBSTEntry, b: OBSTEntry) -> bool:
    """AABB overlap detection."""
    return (a.x1 < b.x2 and a.x2 > b.x1 and
            a.y1 < b.y2 and a.y2 > b.y1 and
            a.z1 < b.z2 and a.z2 > b.z1)


def resolve_overlaps(entries: List[OBSTEntry],
                     room_x_min: float = 0, room_x_max: float = 1e6,
                     room_y_min: float = 0, room_y_max: float = 1e6,
                     ) -> List[OBSTEntry]:
    """Resolve overlaps by priority: keep high-priority, adjust or remove low-priority.

    Returns list of entries that survived (some may have adjusted positions).
    """
    # Sort by priority (walls first, then stairwells, components, combustibles)
    entries.sort(key=lambda e: e.priority)

    kept: List[OBSTEntry] = []
    removed_ids: set = set()

    for entry in entries:
        if entry.source_id in removed_ids:
            continue

        # Check against all already-kept entries
        overlapping = [k for k in kept if check_overlap(entry, k)]
        if not overlapping:
            kept.append(entry)
            continue

        # If this entry has equal or lower priority than what it overlaps with,
        # try to adjust its position
        if entry.priority >= min(k.priority for k in overlapping):
            adjusted = _try_adjust(entry, kept, room_x_min, room_x_max,
                                   room_y_min, room_y_max)
            if adjusted:
                kept.append(adjusted)
            else:
                removed_ids.add(entry.source_id)
        else:
            # Higher priority than existing - keep it, existing stays too
            # (shouldn't normally happen since we sort by priority)
            kept.append(entry)

    return kept


def _try_adjust(entry: OBSTEntry, existing: List[OBSTEntry],
                rx_min: float, rx_max: float,
                ry_min: float, ry_max: float,
                max_attempts: int = 3) -> OBSTEntry:
    """Try shifting entry to avoid overlaps. Returns adjusted entry or None."""
    sx = entry.size_x + 0.1
    sy = entry.size_y + 0.1
    # Try shifts: +X, -X, +Y, -Y, +X+Y, -X+Y, +X-Y, -X-Y
    shifts = [
        (sx, 0), (-sx, 0), (0, sy), (0, -sy),
        (sx, sy), (-sx, sy), (sx, -sy), (-sx, -sy),
    ]

    for attempt in range(min(max_attempts, len(shifts))):
        dx, dy = shifts[attempt]
        candidate = OBSTEntry(
            x1=entry.x1 + dx, x2=entry.x2 + dx,
            y1=entry.y1 + dy, y2=entry.y2 + dy,
            z1=entry.z1, z2=entry.z2,
            priority=entry.priority,
            source_id=entry.source_id,
            source_type=entry.source_type,
        )
        # Check room bounds
        if (candidate.x1 < rx_min or candidate.x2 > rx_max or
                candidate.y1 < ry_min or candidate.y2 > ry_max):
            continue
        # Check no overlap with existing
        if not any(check_overlap(candidate, k) for k in existing):
            return candidate

    return None