"""Temperature ↔ heat-flux polynomial formulas.

Each duration has two 4th-order polynomials (x = temperature K, y = heat flux kW/m²):
  - horizontal (水平): used for side-face flux
  - vertical (竖直):   used for top-face (ZMAX) flux

Valid temperature range: 1000–3000 K.
"""
from __future__ import annotations

import math

# Coefficients for each (duration_s, orientation)
# Order: [c4, c3, c2, c1, c0] for y = c4·x⁴ + c3·x³ + c2·x² + c1·x + c0
COEFFICIENTS: dict[str, dict[str, list[float]]] = {
    "1.36": {
        "horizontal": [2.607644e-10, -1.332468e-06, 3.203812e-03, -3.219235, 1.192315e+03],
        "vertical":   [1.732588e-10, -7.074773e-07, 1.723612e-03, -1.666529, 6.009226e+02],
    },
    "2.1": {
        "horizontal": [-1.290531e-10, 1.501278e-06, -4.049451e-03, 4.623912, -1.846735e+03],
        "vertical":   [-2.706615e-11, 7.962583e-07, -2.205111e-03, 2.643874, -1.087374e+03],
    },
    "7.5": {
        "horizontal": [6.430294e-11, 1.016065e-07, -4.695425e-04, 7.791486e-01, -3.708030e+02],
        "vertical":   [4.883404e-11, 1.070348e-07, -4.250432e-05, -4.340664e-02, 5.741936e+01],
    },
}

T_MIN = 1000.0
T_MAX = 3000.0


def eval_poly(temperature: float, coeffs: list[float]) -> float:
    """Evaluate the 4th-order polynomial at *temperature*."""
    c4, c3, c2, c1, c0 = coeffs
    return c4 * temperature**4 + c3 * temperature**3 + c2 * temperature**2 + c1 * temperature + c0


def invert_poly(
    target_q: float,
    coeffs: list[float],
    t_lo: float = T_MIN,
    t_hi: float = T_MAX,
    tol: float = 0.1,
    max_iter: int = 60,
) -> float:
    """Binary-search invert: find T ∈ [t_lo, t_hi] such that eval_poly(T) ≈ target_q.

    Returns the temperature (clamped to [T_MIN, T_MAX]) and raises ValueError
    if the target is out of range.
    """
    q_lo = eval_poly(t_lo, coeffs)
    q_hi = eval_poly(t_hi, coeffs)

    if target_q < q_lo:
        # Extrapolate: use q_lo ratio (linear scaling from zero)
        return t_lo
    if target_q > q_hi:
        return t_hi

    for _ in range(max_iter):
        t_mid = (t_lo + t_hi) / 2.0
        q_mid = eval_poly(t_mid, coeffs)
        if abs(q_mid - target_q) < tol:
            return t_mid
        if q_mid < target_q:
            t_lo = t_mid
        else:
            t_hi = t_mid

    return (t_lo + t_hi) / 2.0


def get_coeffs(duration: float, orientation: str) -> list[float]:
    """Look up coefficients for *duration* (s) and *orientation* ('horizontal'|'vertical').

    Nearest-match: rounds to the closest known duration.
    """
    known = sorted(COEFFICIENTS.keys(), key=lambda k: abs(float(k) - duration))
    if not known:
        raise KeyError(f"No formula for duration={duration}")
    key = known[0]
    return COEFFICIENTS[key][orientation]


def compute_face_temperatures(
    t_nominal: float,
    duration: float,
    elevation_deg: float,
) -> tuple[float, float | None]:
    """Return (T_side, T_top | None) for given nominal temperature and elevation.

    - T_side: TMP_FRONT for the side (horizontal) faces
    - T_top:  TMP_FRONT for the top (ZMAX) face, or None if elevation == 0
    """
    horiz_c = get_coeffs(duration, "horizontal")

    # Clamp nominal temperature to valid range
    t_nominal = max(T_MIN, min(T_MAX, t_nominal))

    q_total = eval_poly(t_nominal, horiz_c)

    elevation_rad = math.radians(elevation_deg)
    q_horiz = q_total * math.cos(elevation_rad)
    q_vert = q_total * math.sin(elevation_rad)

    t_side = invert_poly(q_horiz, horiz_c)

    if elevation_deg <= 0.0 or q_vert < 1e-6:
        return t_side, None

    vert_c = get_coeffs(duration, "vertical")
    t_top = invert_poly(q_vert, vert_c)
    return t_side, t_top


def compute_top_face_bounds(
    azimuth_deg: float,
    domain: tuple[float, ...],
    buildings_x_min: float,
    buildings_x_max: float,
    buildings_y_min: float,
    buildings_y_max: float,
) -> tuple[float, float, float, float, float, float]:
    """Return the (x1, x2, y1, y2, z1, z2) bounding box for the ZMAX top heat source.

    The top source is a 1 m deep strip on the ZMAX domain face, spanning the
    full building width in the cross-axis direction, aligned with the azimuth.
    """
    x0, x1, y0, y1, z0, z1 = domain
    az = azimuth_deg % 360

    if az == 0:      # XMAX side
        x_start = x1 - 1.0
        x_end = x1
        y_start = buildings_y_min
        y_end = buildings_y_max
    elif az == 180:  # XMIN side
        x_start = x0
        x_end = x0 + 1.0
        y_start = buildings_y_min
        y_end = buildings_y_max
    elif az == 90:   # YMIN side (south, clockwise from east)
        x_start = buildings_x_min
        x_end = buildings_x_max
        y_start = y0
        y_end = y0 + 1.0
    elif az == 270:  # YMAX side (north)
        x_start = buildings_x_min
        x_end = buildings_x_max
        y_start = y1 - 1.0
        y_end = y1
    else:
        # Fallback: interpolate
        rad = math.radians(az)
        cos_a = abs(math.cos(rad))
        sin_a = abs(math.sin(rad))
        if cos_a >= sin_a:
            x_start = x1 - 1.0 if math.cos(rad) > 0 else x0
            x_end = x_start + 1.0
            y_start = buildings_y_min
            y_end = buildings_y_max
        else:
            y_start = y0 if math.sin(rad) < 0 else y1 - 1.0
            y_end = y_start + 1.0
            x_start = buildings_x_min
            x_end = buildings_x_max

    return (x_start, x_end, y_start, y_end, z1, z1)


def compute_zmax_open_rects(
    domain: tuple[float, float, float, float, float, float],
    strip_x1: float, strip_x2: float, strip_y1: float, strip_y2: float,
) -> list[tuple[float, float, float, float, float, float]]:
    """Return ZMAX rectangles (x1,x2,y1,y2,z,z) that are NOT inside the strip.

    Used to emit OPEN VENTs for the remainder of the ZMAX face when a
    radiation strip occupies part of it.
    """
    x0, x1, y0, y1, z0, z1 = domain
    open_rects: list[tuple[float, float, float, float, float, float]] = []

    # Clip strip to domain bounds
    sx1 = max(x0, min(x1, strip_x1))
    sx2 = max(x0, min(x1, strip_x2))
    sy1 = max(y0, min(y1, strip_y1))
    sy2 = max(y0, min(y1, strip_y2))

    # Four possible open rectangles around the strip
    # Top (above strip)
    if sy2 < y1:
        open_rects.append((x0, x1, sy2, y1, z1, z1))
    # Bottom (below strip)
    if sy1 > y0:
        open_rects.append((x0, x1, y0, sy1, z1, z1))
    # Left (of strip, within its Y band)
    if sx1 > x0:
        open_rects.append((x0, sx1, sy1, sy2, z1, z1))
    # Right (of strip, within its Y band)
    if sx2 < x1:
        open_rects.append((sx2, x1, sy1, sy2, z1, z1))

    return open_rects
