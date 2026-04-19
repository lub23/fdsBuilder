"""Heat source flux decomposition: map (azimuth, elevation, Q) → per-face flux dict.

Convention:
    azimuth = 0°  → YMAX (north)
    azimuth = 90° → XMAX (east)
    azimuth = 180° → YMIN (south)
    azimuth = 270° → XMIN (west)
    elevation > 0 → portion of Q tilts onto ZMAX (top)

For azimuths between cardinal directions, flux splits between the two adjacent
side faces using cos(remainder) / sin(remainder) where remainder = azimuth % 90.
"""
from __future__ import annotations

import math


_QUADRANT_FACES = [
    ("YMAX", "XMAX"),   # 0..90
    ("XMAX", "YMIN"),   # 90..180
    ("YMIN", "XMIN"),   # 180..270
    ("XMIN", "YMAX"),   # 270..360
]


def face_fluxes(azimuth: float, elevation: float, Q: float) -> dict[str, float]:
    """Decompose a radiation Q across MESH faces.

    Args:
        azimuth: 0-360° (wraps). 0 = north = YMAX.
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
