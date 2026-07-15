#!/usr/bin/env python3
"""Export the 2026-07-12 damage-threshold supplemental FDS cases.

Outputs are intentionally isolated from case/facility_parameter_sweep.
The supplemental list uses only user-approved damaging azimuths.  Unless a
case has an explicit duration override, each flux uses all four elevations and
all three durations.  Materion facilities are regenerated on the corrected four-flux grid because
their previous set used the legacy temperature-driven source implementation.
Selected no-damage azimuths use T_END=120 s while retaining ``_t1800`` names.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

from generators.fds_generator import DEFAULT_DEVC_DT
from models.facility import FacilityManager
from scripts.generate_facility_parameter_sweep import (
    FacilityScenario,
    _duration_ms,
    load_building_group,
    scenarios,
    write_case,
)

ELEVATIONS = (0, 30, 45, 60)
DURATIONS = (1.36, 2.1, 7.5)
AZIMUTHS = (0, 90, 180, 270)
MATERION_FLUXES = (500, 5000, 10000, 15000)
DEFAULT_OUTPUT = "case/facility_damage_supplement_20260712"


@dataclass(frozen=True)
class FluxRequest:
    azimuth: int
    flux: int
    durations: tuple[float, ...] = DURATIONS


SUPPLEMENTAL_REQUESTS: dict[str, tuple[FluxRequest, ...]] = {
    "aerospace_medium": (
        *(FluxRequest(180, q) for q in (10000, 18000, 20000)),
        *(FluxRequest(270, q) for q in (10000, 20000)),
    ),
    "aerospace_small": tuple(FluxRequest(270, q) for q in (10000, 18000, 20000)),
    "airport_hangar_large": (
        FluxRequest(180, 250, (7.5,)),
        *(FluxRequest(180, q) for q in (1000, 8000, 10000)),
    ),
    "airport_hangar_medium": tuple(FluxRequest(180, q) for q in (250, 1000, 2500)),
    "airport_hangar_small": tuple(FluxRequest(180, q) for q in (250, 1000, 2500)),
    "machinery_manufacturing_medium": tuple(
        FluxRequest(270, q) for q in (18000, 20000)
    ),
    "machinery_manufacturing_small": tuple(
        FluxRequest(270, q) for q in (8000, 10000, 18000, 20000)
    ),
    "metallurgical_facilities_large": (
        *(FluxRequest(180, q) for q in (8000, 10000, 18000, 20000)),
        *(FluxRequest(270, q) for q in (1000, 2500, 8000, 10000, 18000, 20000)),
    ),
    "metallurgical_facilities_medium": tuple(
        FluxRequest(a, q)
        for a in (180, 270)
        for q in (1000, 2500, 18000, 20000)
    ),
    "metallurgical_facilities_small": (
        *(FluxRequest(180, q) for q in (250, 1000, 2500, 18000, 20000)),
        *(FluxRequest(90, q) for q in (1000, 2500, 18000, 20000)),
        *(FluxRequest(270, q) for q in (250, 1000, 2500, 18000, 20000)),
    ),
    "warrick_power_plant": tuple(
        FluxRequest(180, q) for q in (250, 1000, 2500, 18000, 20000)
    ),
}

NO_RERUN = (
    "alcoa",
    "frymaster_corporation",
    "gleason_cutting_tools_corporation",
    "harbison_fischer",
    "aerospace_large",
)
MATERION = ("materion_buffalo", "materion_newton")


def scenario_map() -> dict[str, FacilityScenario]:
    return {scenario.folder_name: scenario for scenario in scenarios()}


def expected_supplemental_count() -> int:
    return sum(
        len(ELEVATIONS) * len(request.durations)
        for requests in SUPPLEMENTAL_REQUESTS.values()
        for request in requests
    )


def generate(root: Path, simulation_time: float) -> list[dict]:
    mgr = FacilityManager()
    lookup = scenario_map()
    manifest: list[dict] = []

    for folder, requests in SUPPLEMENTAL_REQUESTS.items():
        scenario = lookup[folder]
        bg = load_building_group(mgr, scenario)
        out_dir = root / "supplemental" / folder
        count = warning_count = 0
        for request in requests:
            for elevation, duration in product(ELEVATIONS, request.durations):
                case_name = (
                    f"{folder}_q{request.flux}_a{request.azimuth}_e{elevation}"
                    f"_d{_duration_ms(duration)}_t{int(round(simulation_time))}"
                )
                _, warnings = write_case(
                    bg, out_dir, case_name,
                    {
                        "net_heat_flux": request.flux,
                        "azimuth": request.azimuth,
                        "elevation": elevation,
                        "duration": duration,
                    },
                    simulation_time,
                )
                count += 1
                warning_count += len(warnings)
        manifest.append({
            "set": "supplemental",
            "facility": folder,
            "folder": str(out_dir.relative_to(PROJECT_DIR)),
            "files": count,
            "validation_warning_count": warning_count,
        })
        print(f"{folder}: {count} supplemental FDS")

    # Complete corrected Materion rerun grid.
    for folder in MATERION:
        scenario = lookup[folder]
        bg = load_building_group(mgr, scenario)
        out_dir = root / "materion_full_rerun" / folder
        count = warning_count = 0
        for flux, azimuth, elevation, duration in product(
            MATERION_FLUXES, AZIMUTHS, ELEVATIONS, DURATIONS
        ):
            case_name = (
                f"{folder}_q{flux}_a{azimuth}_e{elevation}"
                f"_d{_duration_ms(duration)}_t{int(round(simulation_time))}"
            )
            # Keep the historical ``_t1800`` filename contract while using a
            # short actual T_END for azimuths that previously showed no damage.
            actual_simulation_time = (
                120.0
                if (folder == "materion_buffalo" and azimuth == 180)
                or (folder == "materion_newton" and azimuth in (0, 90))
                else simulation_time
            )
            _, warnings = write_case(
                bg, out_dir, case_name,
                {
                    "net_heat_flux": flux,
                    "azimuth": azimuth,
                    "elevation": elevation,
                    "duration": duration,
                },
                actual_simulation_time,
            )
            count += 1
            warning_count += len(warnings)
        manifest.append({
            "set": "materion_full_rerun",
            "facility": folder,
            "folder": str(out_dir.relative_to(PROJECT_DIR)),
            "files": count,
            "validation_warning_count": warning_count,
        })
        print(f"{folder}: {count} full-rerun FDS")

    metadata = {
        "purpose": "2026-07-12 damage-threshold supplemental export",
        "simulation_time_s": simulation_time,
        "dt_devc_s": DEFAULT_DEVC_DT,
        "maximum_target_heat_flux_kw_m2": 20000,
        "filename_simulation_time_s": simulation_time,
        "special_actual_simulation_times_s": {
            "materion_buffalo/a180": 120.0,
            "materion_newton/a0,a90": 120.0,
        },
        "default_elevations_deg": list(ELEVATIONS),
        "default_durations_s": list(DURATIONS),
        "no_rerun_facilities": list(NO_RERUN),
        "supplemental_expected_files": expected_supplemental_count(),
        "materion_expected_files": len(MATERION_FLUXES) * len(AZIMUTHS) * len(ELEVATIONS) * len(DURATIONS) * len(MATERION),
        "total_expected_files": expected_supplemental_count() + len(MATERION_FLUXES) * len(AZIMUTHS) * len(ELEVATIONS) * len(DURATIONS) * len(MATERION),
        "folders": manifest,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "export_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=DEFAULT_OUTPUT)
    parser.add_argument("--simulation-time", type=float, default=1800.0)
    args = parser.parse_args()
    root = PROJECT_DIR / args.out_dir
    generate(root, args.simulation_time)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
