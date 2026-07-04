"""Heat source flux decomposition: map (azimuth, elevation, Q) → per-face flux dict.

Convention (compass, clockwise from east):
    azimuth = 0°   → XMAX (east)
    azimuth = 90°  → YMIN (south)
    azimuth = 180° → XMIN (west)
    azimuth = 270° → YMAX (north)
    elevation > 0  → portion of Q tilts onto ZMAX (top)

For azimuths between cardinal directions, flux splits between the two adjacent
side faces using cos(remainder) / sin(remainder) where remainder = azimuth % 90.
"""
from __future__ import annotations

import math


_QUADRANT_FACES = [
    ("XMAX", "YMIN"),
    ("YMIN", "XMIN"),
    ("XMIN", "YMAX"),
    ("YMAX", "XMAX"),
]


COMPASS_WALL_OF_AZIMUTH = {
    0:   "x_max",
    90:  "y_min",
    180: "x_min",
    270: "y_max",
}


def face_fluxes(azimuth: float, elevation: float, Q: float) -> dict[str, float]:
    """Decompose a radiation Q across MESH faces.

    Args:
        azimuth: 0-360° (wraps).  0 = east (XMAX), increases clockwise when
                  viewed from above (+z looking down).
        elevation: 0-90° (typically one of {0, 30, 45, 60}).
        Q: Total heat flux in kW/m².

    Returns:
        Dict mapping face name ("XMIN"/"XMAX"/"YMIN"/"YMAX"/"ZMAX") to
        its flux component (kW/m²). Faces with ~0 flux are omitted.
    """
    if Q <= 0:
        return {}

    a = azimuth % 360
    quadrant = int(a // 90) % 4
    primary_face, secondary_face = _QUADRANT_FACES[quadrant]

    rem = math.radians(a - quadrant * 90)
    e = math.radians(elevation)
    cos_e = math.cos(e)
    sin_e = math.sin(e)

    primary = Q * cos_e * math.cos(rem)
    secondary = Q * cos_e * math.sin(rem)
    top = Q * sin_e

    result: dict[str, float] = {}
    tol = 1e-9
    if primary > tol:
        result[primary_face] = primary
    if secondary > tol:
        if secondary_face in result:
            result[secondary_face] += secondary
        else:
            result[secondary_face] = secondary
    if top > tol:
        result["ZMAX"] = top
    return result


def source_orientation(azimuth: float, elevation: float) -> tuple[float, float, float]:
    """Unit vector pointing TOWARD the radiation source (compass convention).

    Compass convention is measured clockwise from +x (east) when viewed from
    above (+z looking down).  Converting that to math basis:
        dx = cos(elevation) * cos(az)             # +x at az=0
        dy = -cos(elevation) * sin(az)            # -y at az=90  (south)
        dz = sin(elevation)                       # +z at az=90

    Returns:
        (dx, dy, dz).
        azimuth=0,  elevation=0 -> (1, 0, 0)   (east  / +x / XMAX).
        azimuth=90, elevation=0 -> (0,-1, 0)   (south / -y / YMIN).
        azimuth=180,elevation=0 -> (-1,0, 0)   (west  / -x / XMIN).
        azimuth=270,elevation=0 -> (0, 1, 0)   (north / +y / YMAX).
    """
    az = math.radians(azimuth)
    el = math.radians(elevation)
    ce = math.cos(el)
    return (ce * math.cos(az), -ce * math.sin(az), math.sin(el))


def rad_wall_for_azimuth(azimuth: float) -> str:
    """Pick the radiation-facing wall id for an arbitrary azimuth.

    For cardinal azimuths returns the exact compass wall; for inter-cardinal
    azimuths returns the wall whose normal is closest to the source direction
    (so the probe / window-flux logic has a reasonable choice even when the
    source is between two perpendicular walls).
    """
    a = azimuth % 360
    if a < 45 or a >= 315:
        return "x_max"
    if a < 135:
        return "y_min"
    if a < 225:
        return "x_min"
    return "y_max"


def horizontal_axis_sign(azimuth: float) -> tuple[str, int]:
    """Dominant horizontal axis/sign of the source direction (compass convention).

    Returns ``("x"|"y", +1|-1)`` — the axis a laid-down rocket lies along
    and the sign its nose points toward (toward the door/source).
    """
    dx, dy, _ = source_orientation(azimuth, 0.0)
    if abs(dx) >= abs(dy):
        return ("x", 1 if dx >= 0 else -1)
    return ("y", 1 if dy >= 0 else -1)
