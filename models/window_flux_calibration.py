"""Window heat-flux calibration formulas.

The UI heat-flux value is a target 0-to-duration window average, ``q_avg``.
FDS boundary radiation still needs the source setting, ``q_set``.  The fitted
quadratic response is:

    q_avg = a * q_set^2 + b * q_set + c

Coefficients come from ``case/rhfg_wall_flux_a0_e0/rhfg_wall_flux_window_summary.md``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowFluxFit:
    duration: float
    quadratic: float
    linear: float
    intercept: float


Q_AVG_FITS: tuple[WindowFluxFit, ...] = (
    WindowFluxFit(
        duration=1.36,
        quadratic=9.345910456e-6,
        linear=0.3282799168,
        intercept=-130.3021806,
    ),
    WindowFluxFit(
        duration=2.1,
        quadratic=2.590789423e-5,
        linear=0.3561706941,
        intercept=-77.05735928,
    ),
    WindowFluxFit(
        duration=7.5,
        quadratic=1.921917542e-4,
        linear=0.6232269677,
        intercept=-65.09560627,
    ),
)


def fit_for_duration(duration: float) -> WindowFluxFit:
    """Return the calibrated fit nearest to ``duration`` seconds."""
    return min(Q_AVG_FITS, key=lambda fit: abs(fit.duration - float(duration)))


def q_avg_to_q_set(q_avg: float, duration: float) -> float:
    """Convert target window-average heat flux to FDS source heat flux.

    Args:
        q_avg: Target 0-to-duration average heat flux in kW/m2.
        duration: Requested source duration in seconds.  The nearest calibrated
            duration fit is used.

    Returns:
        FDS source ``q_set`` in kW/m2.
    """
    fit = fit_for_duration(duration)
    a = fit.quadratic
    b = fit.linear
    c = fit.intercept
    discriminant = b * b - 4.0 * a * (c - float(q_avg))
    if discriminant < 0:
        raise ValueError(
            f"q_avg={q_avg:g} kW/m2 is outside the calibrated quadratic domain"
        )
    return (-b + math.sqrt(discriminant)) / (2.0 * a)

