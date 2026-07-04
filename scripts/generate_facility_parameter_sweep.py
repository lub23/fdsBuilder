#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke-test and export facility FDS parameter sweeps.

Smoke tests:
  - specialized facilities: one test case per facility
  - equivalent facilities: one test case per facility and scale
  - high heat flux, high azimuth, non-zero elevation, T_END ~= 3 s

Full export:
  - one folder per specialized facility
  - one folder per equivalent facility scale, e.g. aerospace_small
  - 4 azimuths x 3 elevations x 3 heat fluxes x 3 durations = 108 FDS files
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from itertools import product
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

from generators.fds_generator import FDSGenerator, validate_fds
from models.build_arranger import arrange_buildings
from models.building import Building, BuildingGroup
from models.facility import FacilityManager


AZIMUTHS = (0, 90, 180, 270)
ELEVATIONS = (0, 30, 45)
HEAT_FLUXES = (500, 5000, 15000)
DURATIONS = (1.36, 2.1, 7.5)

SMOKE_HEAT_SOURCE = {
    "azimuth": 270,
    "elevation": 45,
    "net_heat_flux": 15000,
    "duration": 2.1,
}

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

SCALE_INDEX = {"small": 0, "medium": 1, "large": 2}
TOTAL_PER_FOLDER = len(AZIMUTHS) * len(ELEVATIONS) * len(HEAT_FLUXES) * len(DURATIONS)


@dataclass(frozen=True)
class FacilityScenario:
    """A concrete generation target: facility plus optional scale."""

    facility: str
    grid_size: float
    kind: str
    scale: str | None = None

    @property
    def folder_name(self) -> str:
        if self.scale is None:
            return self.facility
        return f"{self.facility}_{self.scale}"

    @property
    def label(self) -> str:
        if self.scale is None:
            return self.facility
        return f"{self.facility}/{self.scale}"


def _duration_ms(duration: float) -> int:
    return int(round(duration * 1000))


def _read_program_path() -> str:
    config_path = PROJECT_DIR / "program_paths.json"
    if not config_path.exists():
        return "/home/blue/FDS/FDS6/bin/fds"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "/home/blue/FDS/FDS6/bin/fds"
    return data.get("fds") or "/home/blue/FDS/FDS6/bin/fds"


def _domain(grid_size: float) -> dict:
    return {
        "padding": 5.0,
        "grid_size": float(grid_size),
        "num_meshes": 4,
        "refinement_zone": {
            "enabled": True,
            "depth": max(1.0, float(grid_size) + 1.0),
            "grid_size": 1.0,
        },
    }


def _load_specialized_bg(scenario: FacilityScenario) -> BuildingGroup:
    path = PROJECT_DIR / "facilities" / f"{scenario.facility}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    buildings = [Building.from_dict(b) for b in data["buildings"]]
    for building in buildings:
        building.update_z_offsets()
    return BuildingGroup(
        name=scenario.folder_name,
        buildings=buildings,
        domain=_domain(scenario.grid_size),
    )


def _load_equivalent_bg(mgr: FacilityManager, scenario: FacilityScenario) -> BuildingGroup:
    if scenario.scale is None:
        raise ValueError(f"{scenario.facility} is missing scale")

    scale_idx = SCALE_INDEX[scenario.scale]
    buildings = []
    for building_name in mgr.list_buildings(scenario.facility):
        params = mgr.params_for_scale(scenario.facility, building_name, scale_idx=scale_idx)
        buildings.append(mgr.load_equivalent(scenario.facility, building_name, params))

    if len(buildings) > 1:
        layout_applied = mgr.arrange_buildings_by_layout(scenario.facility, buildings)
        if not layout_applied:
            arrange_buildings(buildings, gap=20.0)

    bg = BuildingGroup(
        name=scenario.folder_name,
        buildings=buildings,
        domain=_domain(scenario.grid_size),
    )
    bg.update_z_offsets()
    return bg


def load_building_group(mgr: FacilityManager, scenario: FacilityScenario) -> BuildingGroup:
    if scenario.kind == "specialized":
        return _load_specialized_bg(scenario)
    return _load_equivalent_bg(mgr, scenario)


def scenarios() -> list[FacilityScenario]:
    out: list[FacilityScenario] = []
    for facility, grid_size in SPECIALIZED_GRIDS.items():
        out.append(FacilityScenario(facility=facility, grid_size=grid_size, kind="specialized"))
    for facility, scale_grids in EQUIVALENT_GRIDS.items():
        for scale in ("small", "medium", "large"):
            out.append(
                FacilityScenario(
                    facility=facility,
                    scale=scale,
                    grid_size=scale_grids[scale],
                    kind="equivalent",
                )
            )
    return out


def write_case(
    bg: BuildingGroup,
    out_dir: Path,
    case_name: str,
    heat_source: dict,
    simulation_time: float,
) -> tuple[Path, list[str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    bg.heat_source.update(heat_source)
    bg.simulation_time = float(simulation_time)
    fds_text = FDSGenerator(bg).generate()
    warnings = validate_fds(fds_text)
    fds_path = out_dir / f"{case_name}.fds"
    fds_path.write_text(fds_text, encoding="utf-8")
    return fds_path, warnings


def _fds_error_text(text: str) -> str | None:
    patterns = [
        r"ERROR\(\d+\)",
        r"\bERROR:",
        r"\bforrtl:",
        r"\bMPI_ABORT\b",
        r"\bSegmentation fault\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = max(0, match.start() - 300)
            end = min(len(text), match.end() + 700)
            return text[start:end].strip()
    return None


def run_fds(
    fds_path: Path,
    runner: str,
    fds_exe: str,
    np: int,
    timeout_s: int,
) -> tuple[bool, str]:
    log_path = fds_path.with_name(f"{fds_path.stem}_run.log")
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = env.get("OMP_NUM_THREADS", "8")
    env["I_MPI_FABRICS"] = env.get("I_MPI_FABRICS", "shm")
    cmd = [runner, "-np", str(np), fds_exe, fds_path.name]

    started = time.time()
    try:
        with log_path.open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                cmd,
                cwd=fds_path.parent,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout_s,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout_s}s"

    elapsed = time.time() - started
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    out_path = fds_path.with_suffix(".out")
    out_text = out_path.read_text(encoding="utf-8", errors="replace") if out_path.exists() else ""
    error = _fds_error_text(log_text + "\n" + out_text)
    if completed.returncode != 0:
        return False, f"returncode={completed.returncode}; {error or 'see run log'}"
    if error:
        return False, error
    return True, f"ok in {elapsed:.1f}s"


def smoke_tests(args: argparse.Namespace, selected: list[FacilityScenario]) -> list[dict]:
    mgr = FacilityManager()
    root = PROJECT_DIR / args.smoke_out_dir
    rows: list[dict] = []

    for idx, scenario in enumerate(selected, 1):
        print(f"[smoke {idx:02d}/{len(selected):02d}] {scenario.label} grid={scenario.grid_size:g}m")
        bg = load_building_group(mgr, scenario)
        case_name = (
            f"{scenario.folder_name}_smoke"
            f"_q{SMOKE_HEAT_SOURCE['net_heat_flux']}"
            f"_a{SMOKE_HEAT_SOURCE['azimuth']}"
            f"_e{SMOKE_HEAT_SOURCE['elevation']}"
            f"_d{_duration_ms(SMOKE_HEAT_SOURCE['duration'])}"
            f"_t{int(round(args.smoke_time))}"
        )
        fds_path, warnings = write_case(
            bg=bg,
            out_dir=root / scenario.folder_name,
            case_name=case_name,
            heat_source=dict(SMOKE_HEAT_SOURCE),
            simulation_time=args.smoke_time,
        )
        if args.skip_run:
            ok, detail = True, "generated only (--skip-run)"
        else:
            ok, detail = run_fds(
                fds_path=fds_path,
                runner=args.runner,
                fds_exe=args.fds_exe,
                np=args.np,
                timeout_s=args.fds_timeout,
            )
        status = "OK" if ok else "FAIL"
        print(f"  {status}: {fds_path.relative_to(PROJECT_DIR)} ({detail})")
        if warnings:
            print(f"  validation warnings: {len(warnings)}")
        rows.append({
            "facility": scenario.facility,
            "scale": scenario.scale,
            "folder": scenario.folder_name,
            "grid_size": scenario.grid_size,
            "fds": str(fds_path.relative_to(PROJECT_DIR)),
            "ok": ok,
            "detail": detail,
            "validation_warnings": warnings,
        })

    root.mkdir(parents=True, exist_ok=True)
    (root / "smoke_manifest.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return rows


def export_sweep(args: argparse.Namespace, selected: list[FacilityScenario]) -> list[dict]:
    mgr = FacilityManager()
    root = PROJECT_DIR / args.export_out_dir
    root.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    combinations = list(product(HEAT_FLUXES, AZIMUTHS, ELEVATIONS, DURATIONS))
    for idx, scenario in enumerate(selected, 1):
        started = time.time()
        out_dir = root / scenario.folder_name
        bg = load_building_group(mgr, scenario)
        count = 0
        warning_count = 0
        print(
            f"[export {idx:02d}/{len(selected):02d}] {scenario.label} "
            f"grid={scenario.grid_size:g}m -> {out_dir.relative_to(PROJECT_DIR)}"
        )
        for flux, azimuth, elevation, duration in combinations:
            heat_source = {
                "net_heat_flux": flux,
                "azimuth": azimuth,
                "elevation": elevation,
                "duration": duration,
            }
            case_name = (
                f"{scenario.folder_name}"
                f"_q{flux}"
                f"_a{azimuth}"
                f"_e{elevation}"
                f"_d{_duration_ms(duration)}"
                f"_t{int(round(args.full_sim_time))}"
            )
            _fds_path, warnings = write_case(
                bg=bg,
                out_dir=out_dir,
                case_name=case_name,
                heat_source=heat_source,
                simulation_time=args.full_sim_time,
            )
            count += 1
            warning_count += len(warnings)
        elapsed = time.time() - started
        print(f"  wrote {count}/{TOTAL_PER_FOLDER} files in {elapsed:.1f}s")
        rows.append({
            "facility": scenario.facility,
            "scale": scenario.scale,
            "folder": str(out_dir.relative_to(PROJECT_DIR)),
            "grid_size": scenario.grid_size,
            "files": count,
            "expected_files": TOTAL_PER_FOLDER,
            "validation_warning_count": warning_count,
            "elapsed_s": round(elapsed, 3),
        })

    (root / "export_manifest.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return rows


def parse_selection(value: str | None, all_scenarios: list[FacilityScenario]) -> list[FacilityScenario]:
    if not value:
        return all_scenarios
    wanted = {item.strip() for item in value.split(",") if item.strip()}
    selected = [
        scenario
        for scenario in all_scenarios
        if scenario.facility in wanted or scenario.folder_name in wanted
    ]
    missing = sorted(wanted - {s.facility for s in selected} - {s.folder_name for s in selected})
    if missing:
        raise SystemExit(f"unknown facility selection: {', '.join(missing)}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "export", "all"), default="all")
    parser.add_argument("--select", help="comma-separated facility or folder names")
    parser.add_argument("--smoke-out-dir", default="case/facility_smoke_tests")
    parser.add_argument("--export-out-dir", default="case/facility_parameter_sweep")
    parser.add_argument("--smoke-time", type=float, default=3.0)
    parser.add_argument("--full-sim-time", type=float, default=1800.0)
    parser.add_argument("--fds-timeout", type=int, default=900)
    parser.add_argument("--runner", default="/home/blue/FDS/FDS6/bin/INTEL/bin/mpirun")
    parser.add_argument("--fds-exe", default=_read_program_path())
    parser.add_argument("--np", type=int, default=4)
    parser.add_argument("--skip-run", action="store_true", help="generate smoke FDS without running FDS")
    parser.add_argument(
        "--export-even-if-smoke-fails",
        action="store_true",
        help="continue full export even when one or more smoke tests fail",
    )
    args = parser.parse_args()

    selected = parse_selection(args.select, scenarios())
    print(f"Selected {len(selected)} scenario folder(s); expected full export files: {len(selected) * TOTAL_PER_FOLDER}")

    smoke_rows: list[dict] = []
    if args.mode in {"smoke", "all"}:
        smoke_rows = smoke_tests(args, selected)
        failures = [row for row in smoke_rows if not row["ok"]]
        if failures:
            print(f"\nSmoke failures: {len(failures)}")
            for row in failures:
                scale = f"/{row['scale']}" if row["scale"] else ""
                print(f"  - {row['facility']}{scale}: {row['detail']}")
            if args.mode == "all" and not args.export_even_if_smoke_fails:
                print("Full export skipped because smoke tests failed.")
                return 1
            if args.mode == "smoke":
                return 1

    if args.mode in {"export", "all"}:
        rows = export_sweep(args, selected)
        bad = [row for row in rows if row["files"] != row["expected_files"]]
        if bad:
            print(f"\nExport count mismatch: {len(bad)} folder(s)")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
