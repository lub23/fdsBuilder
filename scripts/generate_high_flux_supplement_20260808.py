#!/usr/bin/env python3
"""Export the 2026-08-08 user-approved high-flux supplemental FDS cases.

Each (facility, azimuth, flux) request generates the full elevation/duration
grid: e in {0, 30, 45, 60} x d in {1.36, 2.1, 7.5} s = 12 files per request.
Outputs are isolated under an 20260808 supplement folder, one subfolder per
facility, so they can be reviewed before being copied into package_target_.
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
    _duration_ms,
    load_building_group,
    scenarios,
    write_case,
)

ELEVATIONS = (0, 30, 45, 60)
DURATIONS = (1.36, 2.1, 7.5)
DEFAULT_OUTPUT = "case/facility_high_flux_supplement_20260808"


@dataclass(frozen=True)
class FluxRequest:
    azimuth: int
    flux: int


REQUESTS: dict[str, tuple[FluxRequest, ...]] = {
    "materion_buffalo": tuple(FluxRequest(90, q) for q in (20000, 25000, 30000)),
    "materion_newton": (
        *(FluxRequest(a, q) for a in (180, 270) for q in (20000, 25000, 30000)),
    ),
    "warrick_power_plant": tuple(FluxRequest(180, q) for q in (25000, 30000)),
    "metallurgical_facilities_large": (
        *(FluxRequest(a, q) for a in (270, 180) for q in (25000, 30000)),
    ),
    "machinery_manufacturing_small": tuple(
        FluxRequest(270, q) for q in (25000, 30000)
    ),
    "machinery_manufacturing_medium": tuple(
        FluxRequest(270, q) for q in (25000, 30000)
    ),
    "machinery_manufacturing_large": (
        *(FluxRequest(a, q) for a in (270, 0) for q in (20000, 25000, 30000)),
    ),
    "aerospace_small": tuple(FluxRequest(270, q) for q in (25000, 30000)),
    "aerospace_large": tuple(FluxRequest(270, q) for q in (30000,)),
}


def scenario_map() -> dict[str, object]:
    return {scenario.folder_name: scenario for scenario in scenarios()}


def expected_total() -> int:
    return sum(
        len(ELEVATIONS) * len(DURATIONS)
        for requests in REQUESTS.values()
        for _ in requests
    )


def generate(root: Path, simulation_time: float) -> list[dict]:
    mgr = FacilityManager()
    lookup = scenario_map()
    manifest: list[dict] = []
    total = 0

    for folder, requests in REQUESTS.items():
        scenario = lookup[folder]
        bg = load_building_group(mgr, scenario)
        out_dir = root / folder
        count = warning_count = 0
        for request in requests:
            for elevation, duration in product(ELEVATIONS, DURATIONS):
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
        total += count
        manifest.append({
            "set": "high_flux_supplement",
            "facility": folder,
            "folder": str(out_dir.relative_to(PROJECT_DIR)),
            "files": count,
            "validation_warning_count": warning_count,
        })
        print(f"{folder}: {count} supplemental FDS ({warning_count} warnings)")

    metadata = {
        "purpose": "2026-08-08 approved high-flux (>20000) supplemental export",
        "simulation_time_s": simulation_time,
        "dt_devc_s": DEFAULT_DEVC_DT,
        "elevations_deg": list(ELEVATIONS),
        "durations_s": list(DURATIONS),
        "expected_files": expected_total(),
        "exported_files": total,
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