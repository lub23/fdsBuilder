#!/usr/bin/env python3
"""Run wall-flux calibration sweeps for every facility/scale scenario."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SWEEP_SCRIPT = PROJECT_DIR / "scripts" / "sweep_rhfg_wall_flux_a0_e0.py"
UPDATE_SCRIPT = PROJECT_DIR / "scripts" / "update_window_flux_calibration_data.py"


SPECIALIZED_GRIDS = {
    "materion_buffalo": 1.0,
    "materion_newton": 1.0,
    "harbison_fischer": 2.0,
    "gleason_cutting_tools_corporation": 2.0,
    "frymaster_corporation": 2.0,
    "warrick_power_plant": 3.0,
    "alcoa": 3.0,
}

EQUIVALENT_GRIDS = {
    "metallurgical_facilities": {"small": 1.0, "medium": 2.0, "large": 2.0},
    "machinery_manufacturing": {"small": 1.0, "medium": 2.0, "large": 3.0},
    "airport_hangar": {"small": 1.0, "medium": 1.0, "large": 1.0},
    "aerospace": {"small": 3.0, "medium": 3.0, "large": 3.0},
}


@dataclass(frozen=True)
class CalibrationScenario:
    facility: str
    grid_size: float


def scenarios() -> list[CalibrationScenario]:
    out = [
        CalibrationScenario(facility=facility, grid_size=grid_size)
        for facility, grid_size in SPECIALIZED_GRIDS.items()
    ]
    for facility, by_scale in EQUIVALENT_GRIDS.items():
        for scale in ("small", "medium", "large"):
            out.append(
                CalibrationScenario(
                    facility=f"{facility}_{scale}",
                    grid_size=by_scale[scale],
                )
            )
    return out


def parse_selection(value: str | None, all_scenarios: list[CalibrationScenario]) -> list[CalibrationScenario]:
    if not value:
        return all_scenarios
    wanted = {item.strip() for item in value.split(",") if item.strip()}
    selected = [scenario for scenario in all_scenarios if scenario.facility in wanted]
    missing = sorted(wanted - {scenario.facility for scenario in selected})
    if missing:
        raise SystemExit(f"unknown facility selection: {', '.join(missing)}")
    return selected


def _arg_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_DIR))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--select", help="comma-separated facility/scale keys")
    parser.add_argument("--out-root", default="case/rhfg_wall_flux_calibrations")
    parser.add_argument("--durations", default="1.36,2.1,7.5")
    parser.add_argument("--azimuths", default="0,90,180,270")
    parser.add_argument(
        "--fluxes",
        default=(
            "100,150,200,250,500,1000,2000,3000,5000,6000,7500,"
            "10000,12000,12500,13000,15000,18000,19000,20000,25000,30000"
        ),
    )
    parser.add_argument("--dt-devc", type=float, default=0.01)
    parser.add_argument("--np", type=int, default=4)
    parser.add_argument("--runner", default="/home/blue/FDS/FDS6/bin/INTEL/bin/mpirun")
    parser.add_argument("--fds-exe", default="/home/blue/FDS/FDS6/bin/fds")
    parser.add_argument("--fit-min", type=float, default=100.0)
    parser.add_argument("--fit-max", type=float, default=20000.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--fit-only", action="store_true")
    parser.add_argument("--skip-missing", action="store_true")
    parser.add_argument("--skip-update-data", action="store_true")
    parser.add_argument("--verbose-sweep", action="store_true")
    args = parser.parse_args()

    selected = parse_selection(args.select, scenarios())
    out_root = Path(args.out_root)
    if not out_root.is_absolute():
        out_root = PROJECT_DIR / out_root

    for index, scenario in enumerate(selected, 1):
        print(
            f"[{index:02d}/{len(selected):02d}] {scenario.facility} "
            f"grid={scenario.grid_size:g}m"
        )
        cmd = [
            sys.executable,
            str(SWEEP_SCRIPT),
            "--facility",
            scenario.facility,
            "--grid-size",
            str(scenario.grid_size),
            "--out-dir",
            _arg_path(out_root / scenario.facility),
            "--durations",
            args.durations,
            "--azimuths",
            args.azimuths,
            "--fluxes",
            args.fluxes,
            "--dt-devc",
            str(args.dt_devc),
            "--np",
            str(args.np),
            "--runner",
            args.runner,
            "--fds-exe",
            args.fds_exe,
            "--fit-min",
            str(args.fit_min),
            "--fit-max",
            str(args.fit_max),
            "--window-stats",
        ]
        if not args.verbose_sweep:
            cmd.append("--quiet")
        if args.force:
            cmd.append("--force")
        if args.generate_only:
            cmd.append("--generate-only")
        if args.fit_only:
            cmd.append("--fit-only")
        if args.skip_missing:
            cmd.append("--skip-missing")
        subprocess.run(cmd, cwd=PROJECT_DIR, check=True)

    if not args.generate_only and not args.skip_update_data:
        subprocess.run(
            [
                sys.executable,
                str(UPDATE_SCRIPT),
                "--root",
                _arg_path(out_root),
            ],
            cwd=PROJECT_DIR,
            check=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
