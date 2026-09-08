"""Helpers for deriving stable FDS/Smokeview file names from a model."""

from __future__ import annotations

import os
import sys
from typing import Any

# Directory where pre-computed SMV results are stored.
# Each subdirectory is `{facility_name}/` and within it,
# `{facility_name}_{simulation_suffix(model)}/` subfolders contain
# pre-computed `{facility_name}_{simulation_suffix(model)}.smv` files.
RESULTS_ROOT = "results"

# Directory holding pre-rendered demo videos. Resolve against the bundle when
# packaged; otherwise a desktop launch from an arbitrary CWD would miss clips.
def _resource_root() -> str:
    bundle_root = os.environ.get("_MEIPASS2") or getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return str(bundle_root)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


RESULTS_ROOT = "results"
VIDEO_ROOT = os.path.join(_resource_root(), "video")


def sanitize_chid(value: str | None, default: str = "building") -> str:
    """Return an ASCII-only CHID-safe identifier.

    Existing UI code historically replaced spaces, dots and hyphens with
    underscores and then dropped non-ASCII characters.  Keep that behavior so
    generated file names remain compatible with previous runs.
    """

    chid = value or default
    chid = chid.replace(" ", "_").replace(".", "_").replace("-", "_")
    chid = "".join(c for c in chid if ord(c) < 128)
    return chid or default


def simulation_suffix(model: Any) -> str:
    """Build the heat-source/simulation suffix used in exported FDS names.

    Format: ``q{flux_kW/m2}_a{azimuth_deg}_e{elevation_deg}_d{duration_ms}_t{sim_time_s}``

    This must match the suffix used when the simulation results were generated.
    """

    hs = getattr(model, "heat_source", {}) or {}
    q_avg_kw = int(hs.get("net_heat_flux", 1000))
    azimuth = int(hs.get("azimuth", 0))
    elevation = int(hs.get("elevation", 0))
    duration = int(float(hs.get("duration", 0)) * 1000)
    sim_time = int(getattr(model, "simulation_time", 0))
    return f"q{q_avg_kw}_a{azimuth}_e{elevation}_d{duration}_t{sim_time}"


def default_fds_filename(model: Any, default: str = "building") -> str:
    """Return the default `.fds` filename for an export/run dialog."""

    chid = sanitize_chid(getattr(model, "name", "") or default, default=default)
    return f"{chid}_{simulation_suffix(model)}.fds"


def default_smv_filename(model: Any, default: str = "building") -> str:
    """Return the expected Smokeview `.smv` filename for the model CHID.

    This includes the simulation suffix so the name matches the file generated
    by FDS when run on a model with these heat-source/sim parameters — that is,
    matches the name FDS itself writes into the working directory based on the
    ``&HEAD CHID='...'`` value the generator emits (which uses the full name
    with suffix).
    """

    chid = sanitize_chid(getattr(model, "name", "") or default, default=default)
    return f"{chid}_{simulation_suffix(model)}.smv"


def results_dir_for(model: Any, default: str = "building") -> str:
    """Return the relative path to the results directory for this model.

    Layout: ``results/{sanitized_facility_name}/{sanitized_facility_name}_{suffix}/``

    Example: ``results/frymaster_corporation/frymaster_corporation_q500_a0_e0_d1360_t1800/``
    """

    name = sanitize_chid(getattr(model, "name", "") or default, default=default)
    return f"{RESULTS_ROOT}/{name}/{name}_{simulation_suffix(model)}"


def results_smv_path(model: Any, default: str = "building") -> str:
    """Return the relative path to the pre-computed ``.smv`` file for a model.

    Path: ``results/{name}/{name}_{suffix}/{name}_{suffix}.smv``
    """

    folder = results_dir_for(model, default=default)
    return f"{folder}/{default_smv_filename(model, default=default)}"


def video_path_for(model: Any, default: str = "building") -> str:
    """Return the relative path to the demo video for a model's condition.

    Path: ``video/{name}_{suffix}.mp4``
    """

    name = sanitize_chid(getattr(model, "name", "") or default, default=default)
    return f"{VIDEO_ROOT}/{name}_{simulation_suffix(model)}.mp4"
