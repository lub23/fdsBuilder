"""Window heat-flux calibration formulas.

The UI heat-flux value is a target 0-to-duration window average, ``q_avg``.
FDS boundary radiation still needs the source setting, ``q_set``.  The fitted
quadratic response is:

    q_avg = a * q_set^2 + b * q_set + c

Facility-specific coefficients are preferred when available.  The default
entries preserve the previous global fit as a fallback for older/generated
models that do not yet have a facility-specific sweep.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


DEFAULT_FACILITY = "__default__"


@dataclass(frozen=True)
class WindowFluxFit:
    duration: float
    quadratic: float
    linear: float
    intercept: float
    facility: str = DEFAULT_FACILITY
    azimuth: float = 0.0


DEFAULT_Q_AVG_FITS: tuple[WindowFluxFit, ...] = (
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


try:
    from models.window_flux_calibration_data import FACILITY_Q_AVG_FITS as _RAW_FACILITY_Q_AVG_FITS
except Exception:
    _RAW_FACILITY_Q_AVG_FITS = ()


FACILITY_Q_AVG_FITS: tuple[WindowFluxFit, ...] = tuple(
    WindowFluxFit(
        facility=str(row[0]),
        azimuth=float(row[1]),
        duration=float(row[2]),
        quadratic=float(row[3]),
        linear=float(row[4]),
        intercept=float(row[5]),
    )
    for row in _RAW_FACILITY_Q_AVG_FITS
)


Q_AVG_FITS: tuple[WindowFluxFit, ...] = DEFAULT_Q_AVG_FITS + FACILITY_Q_AVG_FITS


def _normalize_facility(facility: str | None) -> str:
    if not facility:
        return DEFAULT_FACILITY
    return facility.strip().replace("-", "_")


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _candidate_facility_keys(facility: str | None) -> tuple[str, ...]:
    key = _normalize_facility(facility)
    if key == DEFAULT_FACILITY:
        return (DEFAULT_FACILITY,)
    return (key, DEFAULT_FACILITY)


def fit_for_duration(
    duration: float,
    facility: str | None = None,
    azimuth: float | None = None,
) -> WindowFluxFit:
    """Return the nearest calibrated fit.

    Facility and azimuth are optional for backward compatibility.  When a
    facility-specific fit is not available, the previous global fit is used.
    """
    requested_duration = float(duration)
    requested_azimuth = float(azimuth or 0.0) % 360.0

    for facility_key in _candidate_facility_keys(facility):
        candidates = [fit for fit in Q_AVG_FITS if fit.facility == facility_key]
        if not candidates:
            continue
        if azimuth is not None:
            nearest_angle = min(
                _angle_diff(float(fit.azimuth), requested_azimuth)
                for fit in candidates
            )
            candidates = [
                fit
                for fit in candidates
                if math.isclose(
                    _angle_diff(float(fit.azimuth), requested_azimuth),
                    nearest_angle,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            ]
        return min(candidates, key=lambda fit: abs(float(fit.duration) - requested_duration))

    raise KeyError("No window heat-flux calibration fits are configured")


def q_set_to_q_avg(
    q_set: float,
    duration: float,
    facility: str | None = None,
    azimuth: float | None = None,
) -> float:
    """Convert FDS source heat flux to target window-average heat flux."""
    fit = fit_for_duration(duration, facility=facility, azimuth=azimuth)
    q = float(q_set)
    return fit.quadratic * q * q + fit.linear * q + fit.intercept


def q_avg_to_q_set(
    q_avg: float,
    duration: float,
    facility: str | None = None,
    azimuth: float | None = None,
) -> float:
    """Convert target window-average heat flux to FDS source heat flux.

    Args:
        q_avg: Target 0-to-duration average heat flux in kW/m2.
        duration: Requested source duration in seconds.  The nearest calibrated
            duration fit is used.
        facility: Optional facility/scale key, e.g. ``materion_buffalo`` or
            ``airport_hangar_small``.
        azimuth: Optional source azimuth in degrees.

    Returns:
        FDS source ``q_set`` in kW/m2.
    """
    fit = fit_for_duration(duration, facility=facility, azimuth=azimuth)
    a = fit.quadratic
    b = fit.linear
    c = fit.intercept
    if abs(a) < 1e-18:
        if abs(b) < 1e-18:
            raise ValueError("calibration fit has zero quadratic and linear coefficients")
        return (float(q_avg) - c) / b
    discriminant = b * b - 4.0 * a * (c - float(q_avg))
    if discriminant < 0:
        raise ValueError(
            f"q_avg={q_avg:g} kW/m2 is outside the calibrated quadratic domain"
        )
    return (-b + math.sqrt(discriminant)) / (2.0 * a)
