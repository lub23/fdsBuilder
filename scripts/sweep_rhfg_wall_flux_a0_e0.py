#!/usr/bin/env python3
"""Run e0 RADIATIVE HEAT FLUX GAS wall-probe sweeps for Materion Buffalo."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from generators.fds_generator import FDSGenerator, HEAT_FLUX_PROBE_WALL_OFFSET
from models.build_arranger import arrange_buildings
from models.building import BuildingGroup
from models.facility import FacilityManager
from models.heat_source import rad_wall_for_azimuth


DEFAULT_DURATIONS = (1.36, 2.1, 7.5)
DEFAULT_AZIMUTHS = (0.0, 90.0, 180.0, 270.0)
DEFAULT_FLUXES = (
    100.0,
    150.0,
    200.0,
    250.0,
    500.0,
    1000.0,
    2000.0,
    3000.0,
    5000.0,
    6000.0,
    7500.0,
    10000.0,
    12000.0,
    12500.0,
    13000.0,
    15000.0,
    18000.0,
    19000.0,
    20000.0,
    25000.0,
    30000.0,
)

FACE_BY_WALL = {
    "x_max": "XMAX",
    "x_min": "XMIN",
    "y_min": "YMIN",
    "y_max": "YMAX",
}

ORIENTATION_BY_WALL = {
    "x_max": (1.0, 0.0, 0.0),
    "x_min": (-1.0, 0.0, 0.0),
    "y_min": (0.0, -1.0, 0.0),
    "y_max": (0.0, 1.0, 0.0),
}

SCALE_INDEX = {"small": 0, "medium": 1, "large": 2}

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

CASE_ID_ALIASES = {
    "gleason_cutting_tools_corporation": "gleason",
    "metallurgical_facilities_small": "metallurgical_small",
    "metallurgical_facilities_medium": "metallurgical_medium",
    "metallurgical_facilities_large": "metallurgical_large",
    "machinery_manufacturing_small": "machinery_small",
    "machinery_manufacturing_medium": "machinery_medium",
    "machinery_manufacturing_large": "machinery_large",
}


@dataclass(frozen=True)
class SweepCase:
    facility: str
    duration: float
    flux: float
    azimuth: float

    @property
    def t_end(self) -> float:
        return self.duration + 1.0

    @property
    def case_id(self) -> str:
        d_ms = int(round(self.duration * 1000.0))
        t_ms = int(round(self.t_end * 1000.0))
        q = int(round(self.flux))
        az = int(round(self.azimuth))
        facility_id = CASE_ID_ALIASES.get(self.facility, self.facility)
        case_id = f"{facility_id}_q{q}_a{az}_e0_d{d_ms}_t{t_ms}"
        if len(case_id) > 50:
            # FDS truncates CHID at 50 characters, which changes output names.
            facility_id = re.sub(r"[^A-Za-z0-9]+", "_", facility_id)[:20].strip("_")
            case_id = f"{facility_id}_q{q}_a{az}_e0_d{d_ms}_t{t_ms}"
        return case_id


def parse_floats(text: str) -> tuple[float, ...]:
    return tuple(float(part.strip()) for part in text.split(",") if part.strip())


def load_building_group(facility: str) -> BuildingGroup:
    path = PROJECT_DIR / "facilities" / f"{facility}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        bg = BuildingGroup.from_dict(data)
        bg.name = facility
        return bg

    base, sep, scale = facility.rpartition("_")
    if sep and scale in SCALE_INDEX:
        mgr = FacilityManager()
        buildings = []
        for building_name in mgr.list_buildings(base):
            params = mgr.params_for_scale(base, building_name, scale_idx=SCALE_INDEX[scale])
            buildings.append(mgr.load_equivalent(base, building_name, params))
        if len(buildings) > 1:
            layout_applied = mgr.arrange_buildings_by_layout(base, buildings)
            if not layout_applied:
                arrange_buildings(buildings, gap=20.0)
        bg = BuildingGroup(name=facility, buildings=buildings)
        bg.update_z_offsets()
        return bg

    raise FileNotFoundError(f"unknown facility: {facility}")


def grid_size_for_facility(facility: str) -> float:
    if facility in SPECIALIZED_GRIDS:
        return SPECIALIZED_GRIDS[facility]
    base, sep, scale = facility.rpartition("_")
    if sep and base in EQUIVALENT_GRIDS and scale in EQUIVALENT_GRIDS[base]:
        return EQUIVALENT_GRIDS[base][scale]
    return 1.0


def calibration_domain(grid_size: float) -> dict:
    grid_size = float(grid_size)
    return {
        "padding": 5.0,
        "grid_size": grid_size,
        "num_meshes": 4,
        "refinement_zone": {
            "enabled": True,
            "depth": max(1.0, grid_size + 1.0),
            "grid_size": 1.0,
        },
    }


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_DIR))
    except ValueError:
        return str(path)


def replace_head(text: str, case: SweepCase) -> str:
    title = (
        f"NET_HEAT_FLUX={case.flux:.1f} kW/m2, Azimuth={case.azimuth:g}, Elevation=0, "
        f"Duration={case.duration:.2f}s, SimTime={case.t_end:.2f}s"
    )
    return re.sub(
        r"&HEAD CHID='[^']+', TITLE='[^']*' /",
        f"&HEAD CHID='{case.case_id}', TITLE='{title}' /",
        text,
        count=1,
    )


def set_time_and_dump(
    text: str,
    case: SweepCase,
    dt_devc: float,
    time_dt: float | None,
    lock_time_step: bool,
) -> str:
    time_line = f"&TIME T_END={case.t_end:.2f}"
    if time_dt is not None and time_dt > 0:
        time_line += f", DT={time_dt:.4f}"
    if lock_time_step:
        time_line += ", LOCK_TIME_STEP=.TRUE."
    time_line += " /"
    text = re.sub(
        r"&TIME T_END=[^/]+ /",
        time_line,
        text,
        count=1,
    )
    return re.sub(
        r"&DUMP[^/]+/",
        f"&DUMP DT_RESTART=300.0, DT_DEVC={dt_devc:.4f} /",
        text,
        count=1,
    )


def remove_mpi_process_pins(text: str) -> str:
    return re.sub(r", MPI_PROCESS=\d+", "", text)


def force_actual_source_flux(text: str, case: SweepCase) -> str:
    """Make the emitted radiation SURF use ``case.flux`` as actual q_set.

    The generator normally treats ``heat_source.net_heat_flux`` as a calibrated
    target response and converts it before writing FDS.  This sweep studies the
    direct relationship q_measured = f(q_set), so the FDS ``NET_HEAT_FLUX`` must
    be exactly the case flux.
    """
    wall = rad_wall_for_azimuth(case.azimuth)
    face = FACE_BY_WALL[wall]
    surf_re = re.compile(
        rf"(&SURF ID='radiation_{face}', NET_HEAT_FLUX=)([-+\deE.]+)(, COLOR='ORANGE'[^/]* /)"
    )
    text, count = surf_re.subn(
        rf"\g<1>{case.flux:.6g}\g<3>",
        text,
        count=1,
    )
    if count != 1:
        raise ValueError(f"missing radiation_{face} SURF for azimuth {case.azimuth:g}")

    comment = (
        f"! ========== 外部强辐射热源 (NET_HEAT_FLUX={case.flux:.6g} kW/m2, "
        f"azimuth={case.azimuth:g}°, elevation=0°) =========="
    )
    return re.sub(
        r"! ========== 外部强辐射热源[^\n]*==========",
        comment,
        text,
        count=1,
    )


def strip_unneeded_devc(text: str) -> str:
    keep_ids = ("ID='TIMER->OUT'", "ID='incident_heat_flux'")
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("&DEVC"):
            block = [line]
            i += 1
            while i < len(lines) and "/" not in lines[i - 1]:
                block.append(lines[i])
                i += 1
            block_text = "".join(block)
            if any(token in block_text for token in keep_ids):
                out.append(block_text)
            continue
        out.append(line)
        i += 1
    return "".join(out)


def _numbers_from_xb(block: str) -> tuple[float, float, float, float, float, float]:
    match = re.search(
        r"XB=([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)",
        block,
    )
    if not match:
        raise ValueError(f"missing XB in block: {block[:120]}")
    return tuple(float(match.group(i)) for i in range(1, 7))


def _source_coordinate_from_vent(block: str, wall: str) -> float:
    x0, x1, y0, y1, _, _ = _numbers_from_xb(block)
    if wall in {"x_max", "x_min"}:
        if abs(x1 - x0) > 1e-6:
            raise ValueError(f"{wall} radiation source VENT is not planar")
        return x0
    if abs(y1 - y0) > 1e-6:
        raise ValueError(f"{wall} radiation source VENT is not planar")
    return y0


def _source_facing_wall_target(text: str, wall: str, source_coord: float) -> dict[str, float]:
    expected_coord = source_coord - 1.0 if wall in {"x_max", "y_max"} else source_coord + 1.0
    candidates: list[dict[str, float]] = []
    for obst_match in re.finditer(r"&OBST[^/]*SURF_ID='WALL'[^/]* /", text):
        x0, x1, y0, y1, z0, z1 = _numbers_from_xb(obst_match.group(0))
        if wall == "x_max":
            if abs(x1 - expected_coord) <= 1e-6:
                candidates.append({
                    "area": (y1 - y0) * (z1 - z0),
                    "coord": x1,
                    "transverse_1": (y0 + y1) / 2.0,
                    "transverse_2": (z0 + z1) / 2.0,
                })
        elif wall == "x_min":
            if abs(x0 - expected_coord) <= 1e-6:
                candidates.append({
                    "area": (y1 - y0) * (z1 - z0),
                    "coord": x0,
                    "transverse_1": (y0 + y1) / 2.0,
                    "transverse_2": (z0 + z1) / 2.0,
                })
        elif wall == "y_min":
            if abs(y0 - expected_coord) <= 1e-6:
                candidates.append({
                    "area": (x1 - x0) * (z1 - z0),
                    "coord": y0,
                    "transverse_1": (x0 + x1) / 2.0,
                    "transverse_2": (z0 + z1) / 2.0,
                })
        elif wall == "y_max":
            if abs(y1 - expected_coord) <= 1e-6:
                candidates.append({
                    "area": (x1 - x0) * (z1 - z0),
                    "coord": y1,
                    "transverse_1": (x0 + x1) / 2.0,
                    "transverse_2": (z0 + z1) / 2.0,
                })
    if not candidates:
        raise ValueError(f"could not find a {wall} WALL face 1 m from the source")
    return max(candidates, key=lambda item: item["area"])


def _signed_distance_to_source(wall: str, source_coord: float, coord: float) -> float:
    if wall in {"x_max", "y_max"}:
        return source_coord - coord
    return coord - source_coord


def _probe_coord_from_wall(wall: str, wall_coord: float) -> float:
    if wall in {"x_max", "y_max"}:
        return wall_coord + HEAT_FLUX_PROBE_WALL_OFFSET
    return wall_coord - HEAT_FLUX_PROBE_WALL_OFFSET


def move_probe_to_wall_gas_side(text: str, azimuth: float) -> str:
    """Move incident_heat_flux to the selected wall target, just outside in gas."""
    wall = rad_wall_for_azimuth(azimuth)
    face = FACE_BY_WALL[wall]
    source_match = re.search(
        rf"&VENT[^/]*SURF_ID='radiation_{face}'[^/]*XB=[^/]+/",
        text,
    )
    if not source_match:
        raise ValueError(f"missing {face} radiation source VENT")
    source_coord = _source_coordinate_from_vent(source_match.group(0), wall)

    pattern = re.compile(
        r"&DEVC XYZ=([-\d.]+),([-\d.]+),([-\d.]+),\s*"
        r"QUANTITY='([^']+)',\s*"
        r"ORIENTATION=([-\d.]+),([-\d.]+),([-\d.]+),\s*"
        r"ID='incident_heat_flux' /[^\n]*\n?",
        re.DOTALL,
    )
    probe_match = pattern.search(text)
    if not probe_match:
        raise ValueError("missing incident_heat_flux DEVC")
    px, py, pz = (float(probe_match.group(i)) for i in range(1, 4))
    quantity = probe_match.group(4)
    if quantity != "RADIATIVE HEAT FLUX GAS":
        raise ValueError(f"wrong probe quantity: {quantity}")

    target = _source_facing_wall_target(text, wall, source_coord)
    wall_coord = target["coord"]
    if wall in {"x_max", "x_min"}:
        px = _probe_coord_from_wall(wall, wall_coord)
        py = target["transverse_1"]
        pz = target["transverse_2"]
    else:
        py = _probe_coord_from_wall(wall, wall_coord)
        px = target["transverse_1"]
        pz = target["transverse_2"]

    sx, sy, sz = ORIENTATION_BY_WALL[wall]
    replacement = (
        f"&DEVC XYZ={px:.3f},{py:.3f},{pz:.3f},\n"
        "      QUANTITY='RADIATIVE HEAT FLUX GAS',\n"
        f"      ORIENTATION={sx:.3f},{sy:.3f},{sz:.3f},\n"
        f"      ID='incident_heat_flux' /  ! source-aligned gas probe at wall + {HEAT_FLUX_PROBE_WALL_OFFSET:g} m (azimuth={azimuth:g}°, wall={wall})\n\n"
    )
    return pattern.sub(replacement, text, count=1)


def validate_geometry(text: str, azimuth: float) -> dict[str, float | str]:
    wall = rad_wall_for_azimuth(azimuth)
    face = FACE_BY_WALL[wall]
    source_match = re.search(
        rf"&VENT[^/]*SURF_ID='radiation_{face}'[^/]*XB=[^/]+/",
        text,
    )
    if not source_match:
        raise ValueError(f"missing {face} radiation source VENT")
    source_coord = _source_coordinate_from_vent(source_match.group(0), wall)

    probe_match = re.search(
        r"&DEVC XYZ=([-\d.]+),([-\d.]+),([-\d.]+),\s*"
        r"QUANTITY='([^']+)',\s*"
        r"ORIENTATION=([-\d.]+),([-\d.]+),([-\d.]+),\s*"
        r"ID='incident_heat_flux'",
        text,
        re.DOTALL,
    )
    if not probe_match:
        raise ValueError("missing incident_heat_flux DEVC")
    px, py, pz = (float(probe_match.group(i)) for i in range(1, 4))
    quantity = probe_match.group(4)
    orientation = tuple(float(probe_match.group(i)) for i in range(5, 8))
    if quantity != "RADIATIVE HEAT FLUX GAS":
        raise ValueError(f"wrong probe quantity: {quantity}")
    if any(abs(actual - expected) > 1e-6 for actual, expected in zip(orientation, ORIENTATION_BY_WALL[wall])):
        raise ValueError(f"wrong probe orientation for {wall}: {orientation}")

    target = _source_facing_wall_target(text, wall, source_coord)
    wall_coord = target["coord"]
    if wall in {"x_max", "x_min"}:
        probe_coord = px
        source_key = "source_x_m"
        wall_key = "wall_x_m"
        probe_key = "probe_x_m"
    else:
        probe_coord = py
        source_key = "source_y_m"
        wall_key = "wall_y_m"
        probe_key = "probe_y_m"

    source_wall_distance = _signed_distance_to_source(wall, source_coord, wall_coord)
    source_probe_distance = _signed_distance_to_source(wall, source_coord, probe_coord)
    expected_probe_distance = 1.0 - HEAT_FLUX_PROBE_WALL_OFFSET
    if not math.isclose(source_wall_distance, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(f"source-wall distance is {source_wall_distance:.6g} m, not 1 m")
    if not math.isclose(source_probe_distance, expected_probe_distance, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(
            f"source-probe distance is {source_probe_distance:.6g} m, "
            f"not {expected_probe_distance:.6g} m"
        )
    if wall in {"x_max", "x_min"}:
        expected_probe_coord = _probe_coord_from_wall(wall, wall_coord)
        if (
            abs(probe_coord - expected_probe_coord) > 1e-6
            or abs(py - target["transverse_1"]) > 1e-6
            or abs(pz - target["transverse_2"]) > 1e-6
        ):
            raise ValueError("probe is not centered on the selected source-facing wall target")
    else:
        expected_probe_coord = _probe_coord_from_wall(wall, wall_coord)
    if wall in {"y_min", "y_max"} and (
        abs(probe_coord - expected_probe_coord) > 1e-6
        or abs(px - target["transverse_1"]) > 1e-6
        or abs(pz - target["transverse_2"]) > 1e-6
    ):
        raise ValueError("probe is not centered on the selected source-facing wall target")

    return {
        "quantity": quantity,
        "azimuth_deg": azimuth,
        "wall": wall,
        "radiation_face": face,
        source_key: source_coord,
        wall_key: wall_coord,
        "probe_x_m": px,
        "probe_y_m": py,
        "probe_z_m": pz,
        probe_key: probe_coord,
        "source_wall_distance_m": source_wall_distance,
        "source_probe_distance_m": source_probe_distance,
        "probe_wall_offset_m": abs(probe_coord - wall_coord),
        "wall_target_area_m2": target["area"],
    }


def generate_case(
    case: SweepCase,
    out_dir: Path,
    grid_size: float,
    dt_devc: float,
    time_dt: float | None,
    lock_time_step: bool,
) -> Path:
    bg = load_building_group(case.facility)
    bg.domain = calibration_domain(grid_size)
    bg.output = {"slices": False, "devices": True}
    bg.heat_source = {
        "azimuth": case.azimuth,
        "elevation": 0.0,
        "net_heat_flux": case.flux,
        "duration": case.duration,
    }
    bg.simulation_time = case.t_end

    text = FDSGenerator(bg).generate()
    text = replace_head(text, case)
    text = set_time_and_dump(text, case, dt_devc, time_dt, lock_time_step)
    text = force_actual_source_flux(text, case)
    text = move_probe_to_wall_gas_side(text, case.azimuth)
    text = strip_unneeded_devc(text)
    validation = validate_geometry(text, case.azimuth)

    out_dir.mkdir(parents=True, exist_ok=True)
    fds_path = out_dir / f"{case.case_id}.fds"
    fds_path.write_text(text, encoding="utf-8")

    validation_path = out_dir / f"{case.case_id}_validation.json"
    validation_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")
    return fds_path


def run_case(fds_path: Path, np: int, runner: str, fds_exe: str, force: bool, verbose: bool) -> None:
    out_path = fds_path.with_suffix(".out")
    csv_path = fds_path.with_name(f"{fds_path.stem}_devc.csv")
    if out_path.exists() and csv_path.exists() and not force:
        return
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "8"
    env["I_MPI_FABRICS"] = "shm"
    cmd = [runner, "-np", str(np), fds_exe, fds_path.name]
    if verbose:
        subprocess.run(cmd, cwd=fds_path.parent, env=env, check=True)
    else:
        log_path = fds_path.with_name(f"{fds_path.stem}_run.log")
        with log_path.open("w", encoding="utf-8") as log:
            subprocess.run(
                cmd,
                cwd=fds_path.parent,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
    if not csv_path.exists():
        raise RuntimeError(f"FDS did not produce {csv_path.name}")


def read_max_probe(out_dir: Path, case: SweepCase) -> dict[str, float | int]:
    csv_path = out_dir / f"{case.case_id}_devc.csv"
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)
    out_path = out_dir / f"{case.case_id}.out"
    if not out_path.exists():
        raise FileNotFoundError(out_path)
    out_text = out_path.read_text(encoding="utf-8", errors="replace")
    if "STOP: FDS completed successfully" not in out_text:
        raise RuntimeError(f"{case.case_id} did not complete successfully")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        if header and header[0].strip() != "Time":
            header = next(reader)
        try:
            idx = [h.strip().strip('"') for h in header].index("incident_heat_flux")
        except ValueError as exc:
            raise ValueError(f"{csv_path}: missing incident_heat_flux column") from exc

        max_value = -math.inf
        max_time = math.nan
        sample_count = 0
        for row in reader:
            if len(row) <= idx:
                continue
            try:
                t = float(row[0])
                value = float(row[idx])
            except ValueError:
                continue
            sample_count += 1
            if value > max_value:
                max_value = value
                max_time = t
    if sample_count == 0:
        raise ValueError(f"{csv_path}: no numeric probe samples")
    return {
        "facility": case.facility,
        "azimuth": case.azimuth,
        "duration": case.duration,
        "t_end": case.t_end,
        "source_flux": case.flux,
        "measured_flux_max": max_value,
        "time_of_max": max_time,
        "samples": sample_count,
        "case_id": case.case_id,
    }


def read_probe_series(out_dir: Path, case: SweepCase) -> list[tuple[float, float]]:
    csv_path = out_dir / f"{case.case_id}_devc.csv"
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)
    out_path = out_dir / f"{case.case_id}.out"
    if not out_path.exists():
        raise FileNotFoundError(out_path)
    out_text = out_path.read_text(encoding="utf-8", errors="replace")
    if "STOP: FDS completed successfully" not in out_text:
        raise RuntimeError(f"{case.case_id} did not complete successfully")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        if header and header[0].strip() != "Time":
            header = next(reader)
        try:
            idx = [h.strip().strip('"') for h in header].index("incident_heat_flux")
        except ValueError as exc:
            raise ValueError(f"{csv_path}: missing incident_heat_flux column") from exc

        values: list[tuple[float, float]] = []
        for row in reader:
            if len(row) <= idx:
                continue
            try:
                values.append((float(row[0]), float(row[idx])))
            except ValueError:
                continue
    if not values:
        raise ValueError(f"{csv_path}: no numeric probe samples")
    values.sort()
    return values


def read_window_probe_stats(out_dir: Path, case: SweepCase) -> dict[str, float | int | str]:
    values = read_probe_series(out_dir, case)
    t_cut = float(case.duration)

    def interp_at(target: float) -> float:
        if target <= values[0][0]:
            return values[0][1]
        for (t0, v0), (t1, v1) in zip(values, values[1:]):
            if t0 <= target <= t1:
                if math.isclose(t0, t1, rel_tol=0.0, abs_tol=1e-12):
                    return v1
                frac = (target - t0) / (t1 - t0)
                return v0 + frac * (v1 - v0)
        return values[-1][1]

    window = [(0.0, interp_at(0.0))]
    for t, v in values:
        if 0.0 < t < t_cut:
            window.append((t, v))
    window.append((t_cut, interp_at(t_cut)))
    window.sort()
    max_time, max_value = max(window, key=lambda item: item[1])

    if t_cut <= 0:
        avg_value = window[-1][1]
    else:
        area = 0.0
        for (t0, v0), (t1, v1) in zip(window, window[1:]):
            area += 0.5 * (v0 + v1) * (t1 - t0)
        avg_value = area / t_cut

    return {
        "facility": case.facility,
        "azimuth": case.azimuth,
        "duration": case.duration,
        "t_end": case.t_end,
        "source_flux": case.flux,
        "cut_time": t_cut,
        "cut_time_error": 0.0,
        "average_flux_0_to_cut": avg_value,
        "max_flux_0_to_cut": max_value,
        "time_of_window_max": max_time,
        "samples_window": len(window),
        "samples_total": len(values),
        "case_id": case.case_id,
    }


def fit_linear(points: list[tuple[float, float]]) -> dict[str, float | int]:
    n = len(points)
    if n < 2:
        raise ValueError("need at least two points")
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points)
    sxy = sum(x * y for x, y in points)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        raise ValueError("singular linear fit")
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    mean_y = sy / n
    ss_tot = sum((y - mean_y) ** 2 for _, y in points)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in points)
    r2 = 1.0 if ss_tot <= 1e-12 else 1.0 - ss_res / ss_tot
    return {
        "slope": slope,
        "intercept": intercept,
        "r2": r2,
        "n": n,
        "max_abs_error": max(abs(y - (slope * x + intercept)) for x, y in points),
    }


def _solve_3x3(a: list[list[float]], b: list[float]) -> list[float]:
    rows = [a[i][:] + [b[i]] for i in range(3)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(rows[row][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError("singular quadratic fit")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        div = rows[col][col]
        rows[col] = [value / div for value in rows[col]]
        for row in range(3):
            if row == col:
                continue
            factor = rows[row][col]
            rows[row] = [rows[row][i] - factor * rows[col][i] for i in range(4)]
    return [rows[i][3] for i in range(3)]


def fit_quadratic(points: list[tuple[float, float]]) -> dict[str, float | int]:
    n = len(points)
    if n < 3:
        raise ValueError("need at least three points")
    sx = sum(x for x, _ in points)
    sx2 = sum(x**2 for x, _ in points)
    sx3 = sum(x**3 for x, _ in points)
    sx4 = sum(x**4 for x, _ in points)
    sy = sum(y for _, y in points)
    sxy = sum(x * y for x, y in points)
    sx2y = sum(x**2 * y for x, y in points)
    a2, a1, a0 = _solve_3x3(
        [[sx4, sx3, sx2], [sx3, sx2, sx], [sx2, sx, n]],
        [sx2y, sxy, sy],
    )
    mean_y = sy / n
    ss_tot = sum((y - mean_y) ** 2 for _, y in points)
    ss_res = sum((y - (a2 * x**2 + a1 * x + a0)) ** 2 for x, y in points)
    r2 = 1.0 if ss_tot <= 1e-12 else 1.0 - ss_res / ss_tot
    return {
        "quadratic": a2,
        "linear": a1,
        "intercept": a0,
        "r2": r2,
        "n": n,
        "max_abs_error": max(abs(y - (a2 * x**2 + a1 * x + a0)) for x, y in points),
    }


def invert_fit(fit: dict[str, float | int], y: float) -> float:
    if "quadratic" in fit:
        a = float(fit["quadratic"])
        b = float(fit["linear"])
        c = float(fit["intercept"])
        if abs(a) < 1e-18:
            return (y - c) / b
        disc = b * b - 4.0 * a * (c - y)
        if disc < 0:
            raise ValueError(f"negative discriminant for y={y}: {disc}")
        roots = [
            (-b + math.sqrt(disc)) / (2.0 * a),
            (-b - math.sqrt(disc)) / (2.0 * a),
        ]
        positive = [root for root in roots if root >= 0]
        return min(positive) if positive else roots[0]
    return (y - float(fit["intercept"])) / float(fit["slope"])


def build_fits_by_duration(
    rows: list[dict[str, float | int | str]],
    metric: str,
    fit_min: float,
    fit_max: float,
) -> dict[str, dict[str, dict[str, dict[str, float | int] | int]]]:
    by_az_duration: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for row in rows:
        measured = float(row[metric])
        if fit_min <= measured <= fit_max:
            az_key = str(int(round(float(row.get("azimuth", 0.0)))))
            d_key = f"{float(row['duration']):.2f}".rstrip("0").rstrip(".")
            by_az_duration.setdefault(az_key, {}).setdefault(d_key, []).append((float(row["source_flux"]), measured))

    fits: dict[str, dict[str, dict[str, dict[str, float | int] | int]]] = {}
    for az_key, by_duration in by_az_duration.items():
        fits[az_key] = {}
        for d_key, points in by_duration.items():
            fits[az_key][d_key] = {"n": len(points)}
            if len(points) >= 2:
                fits[az_key][d_key]["linear"] = fit_linear(points)
            if len(points) >= 3:
                fits[az_key][d_key]["quadratic"] = fit_quadratic(points)
                qfit = fits[az_key][d_key]["quadratic"]
                assert isinstance(qfit, dict)
                q_low = invert_fit(qfit, fit_min)
                q_high = invert_fit(qfit, fit_max)
                fits[az_key][d_key]["source_flux_range_quadratic"] = {
                    "measured_min": fit_min,
                    "measured_max": fit_max,
                    "source_flux_min": q_low,
                    "source_flux_max": q_high,
                }
    return fits


def write_summary(out_dir: Path, rows: list[dict[str, float | int | str]], fit_min: float, fit_max: float) -> Path:
    by_az_duration: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for row in rows:
        measured = float(row["measured_flux_max"])
        if fit_min <= measured <= fit_max:
            az_key = str(int(round(float(row.get("azimuth", 0.0)))))
            d_key = f"{float(row['duration']):.2f}".rstrip("0").rstrip(".")
            by_az_duration.setdefault(az_key, {}).setdefault(d_key, []).append((float(row["source_flux"]), measured))

    fits: dict[str, dict[str, dict[str, dict[str, float | int] | int]]] = {}
    for az_key, by_duration in by_az_duration.items():
        fits[az_key] = {}
        for d_key, points in by_duration.items():
            fits[az_key][d_key] = {"n": len(points)}
            if len(points) >= 2:
                fits[az_key][d_key]["linear"] = fit_linear(points)
            if len(points) >= 3:
                fits[az_key][d_key]["quadratic"] = fit_quadratic(points)

    summary = {
        "rows": rows,
        "fit_measured_range": [fit_min, fit_max],
        "fits": fits,
    }
    summary_path = out_dir / "rhfg_wall_flux_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    csv_path = out_dir / "rhfg_wall_flux_rows.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "azimuth",
            "facility",
            "duration",
            "t_end",
            "source_flux",
            "measured_flux_max",
            "time_of_max",
            "samples",
            "case_id",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row[name] for name in fieldnames})

    md_lines = [
        "# RADIATIVE HEAT FLUX GAS Wall-Flux Sweep",
        "",
        f"Fit range: measured heat flux {fit_min:g}-{fit_max:g} kW/m2.",
        "",
    ]
    for az_key in sorted(fits, key=lambda value: float(value)):
        md_lines.append(f"## Azimuth {az_key} deg")
        md_lines.append("")
        for d_key in sorted(fits[az_key], key=lambda value: float(value)):
            fit = fits[az_key][d_key]
            if "linear" not in fit:
                md_lines.append(f"### Duration {d_key} s")
                md_lines.append(f"- Not enough points for a linear fit; n={int(fit['n'])}.")
                md_lines.append("")
                continue
            linear_fit = fit["linear"]
            assert isinstance(linear_fit, dict)
            slope = float(linear_fit["slope"])
            intercept = float(linear_fit["intercept"])
            md_lines.append(f"### Duration {d_key} s")
            md_lines.append(
                f"- f(q_set) = {slope:.10g} * q_set + {intercept:.10g}; "
                f"R2={float(linear_fit['r2']):.8f}; n={int(linear_fit['n'])}; "
                f"max_abs_error={float(linear_fit['max_abs_error']):.6g}"
            )
            md_lines.append(
                f"- g(q_measured) = (q_measured - {intercept:.10g}) / {slope:.10g}"
            )
            if "quadratic" in fit:
                quadratic_fit = fit["quadratic"]
                assert isinstance(quadratic_fit, dict)
                a2 = float(quadratic_fit["quadratic"])
                a1 = float(quadratic_fit["linear"])
                a0 = float(quadratic_fit["intercept"])
                md_lines.append(
                    f"- quadratic f(q_set) = {a2:.10g} * q_set^2 + {a1:.10g} * q_set + {a0:.10g}; "
                    f"R2={float(quadratic_fit['r2']):.8f}; n={int(quadratic_fit['n'])}; "
                    f"max_abs_error={float(quadratic_fit['max_abs_error']):.6g}"
                )
                md_lines.append(
                    f"- quadratic g(q_measured) = (-{a1:.10g} + "
                    f"sqrt(({a1:.10g})^2 - 4*({a2:.10g})*({a0:.10g} - q_measured))) / "
                    f"(2*{a2:.10g})"
                )
            md_lines.append("")
    (out_dir / "rhfg_wall_flux_summary.md").write_text("\n".join(md_lines), encoding="utf-8")
    return summary_path


def write_window_summary(out_dir: Path, rows: list[dict[str, float | int | str]], fit_min: float, fit_max: float) -> Path:
    metrics = {
        "average_flux_0_to_cut": "0-to-target-window average",
        "max_flux_0_to_cut": "0-to-target-window maximum",
    }
    fits = {
        metric: build_fits_by_duration(rows, metric, fit_min, fit_max)
        for metric in metrics
    }
    summary = {
        "rows": rows,
        "cut_time_rule": "nearest available output sample time to the requested duration",
        "average_rule": "trapezoidal time integral from 0 to cut_time divided by cut_time",
        "fit_measured_range": [fit_min, fit_max],
        "fits": fits,
    }
    summary_path = out_dir / "rhfg_wall_flux_window_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    csv_path = out_dir / "rhfg_wall_flux_window_rows.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "azimuth",
            "facility",
            "duration",
            "t_end",
            "source_flux",
            "cut_time",
            "cut_time_error",
            "average_flux_0_to_cut",
            "max_flux_0_to_cut",
            "time_of_window_max",
            "samples_window",
            "samples_total",
            "case_id",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row[name] for name in fieldnames})

    md_lines = [
        "# RADIATIVE HEAT FLUX GAS Window Metrics",
        "",
        f"Fit range: measured heat flux {fit_min:g}-{fit_max:g} kW/m2.",
        "Cut time: nearest available output sample time to the requested duration.",
        "Average: trapezoidal time integral from 0 to cut_time divided by cut_time.",
        "",
    ]
    for metric, label in metrics.items():
        md_lines.append(f"## Metric: {label}")
        md_lines.append("")
        for az_key in sorted(fits[metric], key=lambda value: float(value)):
            md_lines.append(f"### Azimuth {az_key} deg")
            md_lines.append("")
            for d_key in sorted(fits[metric][az_key], key=lambda value: float(value)):
                fit = fits[metric][az_key][d_key]
                md_lines.append(f"#### Duration {d_key} s")
                if "linear" not in fit:
                    md_lines.append(f"- Not enough points for a linear fit; n={int(fit['n'])}.")
                    md_lines.append("")
                    continue
                linear_fit = fit["linear"]
                assert isinstance(linear_fit, dict)
                slope = float(linear_fit["slope"])
                intercept = float(linear_fit["intercept"])
                md_lines.append(
                    f"- linear f(q_set) = {slope:.10g} * q_set + {intercept:.10g}; "
                    f"R2={float(linear_fit['r2']):.8f}; n={int(linear_fit['n'])}; "
                    f"max_abs_error={float(linear_fit['max_abs_error']):.6g}"
                )
                md_lines.append(
                    f"- linear g(q_measured) = (q_measured - {intercept:.10g}) / {slope:.10g}"
                )
                if "quadratic" in fit:
                    quadratic_fit = fit["quadratic"]
                    assert isinstance(quadratic_fit, dict)
                    a2 = float(quadratic_fit["quadratic"])
                    a1 = float(quadratic_fit["linear"])
                    a0 = float(quadratic_fit["intercept"])
                    md_lines.append(
                        f"- quadratic f(q_set) = {a2:.10g} * q_set^2 + {a1:.10g} * q_set + {a0:.10g}; "
                        f"R2={float(quadratic_fit['r2']):.8f}; n={int(quadratic_fit['n'])}; "
                        f"max_abs_error={float(quadratic_fit['max_abs_error']):.6g}"
                    )
                    md_lines.append(
                        f"- quadratic g(q_measured) = (-{a1:.10g} + "
                        f"sqrt(({a1:.10g})^2 - 4*({a2:.10g})*({a0:.10g} - q_measured))) / "
                        f"(2*{a2:.10g})"
                    )
                    range_info = fit.get("source_flux_range_quadratic")
                    if isinstance(range_info, dict):
                        md_lines.append(
                            f"- quadratic source range for measured {fit_min:g}-{fit_max:g}: "
                            f"{float(range_info['source_flux_min']):.6g} to "
                            f"{float(range_info['source_flux_max']):.6g} kW/m2"
                        )
                md_lines.append("")
    (out_dir / "rhfg_wall_flux_window_summary.md").write_text("\n".join(md_lines), encoding="utf-8")
    return summary_path


def build_cases(
    durations: tuple[float, ...],
    fluxes: tuple[float, ...],
    azimuths: tuple[float, ...],
    facility: str,
) -> list[SweepCase]:
    return [
        SweepCase(facility=facility, duration=d, flux=q, azimuth=az)
        for az in azimuths
        for d in durations
        for q in fluxes
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="case/rhfg_wall_flux_e0_azimuths")
    parser.add_argument("--facility", default="materion_buffalo")
    parser.add_argument("--grid-size", type=float, default=None)
    parser.add_argument("--durations", default=",".join(str(x) for x in DEFAULT_DURATIONS))
    parser.add_argument("--azimuths", default=",".join(str(int(x)) for x in DEFAULT_AZIMUTHS))
    parser.add_argument("--fluxes", default=",".join(str(int(x)) for x in DEFAULT_FLUXES))
    parser.add_argument("--dt-devc", type=float, default=0.1)
    parser.add_argument("--time-dt", type=float, default=None)
    parser.add_argument("--lock-time-step", action="store_true")
    parser.add_argument("--np", type=int, default=4)
    parser.add_argument("--runner", default="/home/blue/FDS/FDS6/bin/INTEL/bin/mpirun")
    parser.add_argument("--fds-exe", default="fds")
    parser.add_argument("--fit-min", type=float, default=100.0)
    parser.add_argument("--fit-max", type=float, default=20000.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verbose-fds", action="store_true")
    parser.add_argument("--skip-missing", action="store_true")
    parser.add_argument("--window-stats", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--fit-only", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    durations = parse_floats(args.durations)
    azimuths = parse_floats(args.azimuths)
    fluxes = parse_floats(args.fluxes)
    out_dir = (PROJECT_DIR / args.out_dir).resolve()
    cases = build_cases(durations, fluxes, azimuths, args.facility)
    grid_size = args.grid_size if args.grid_size is not None else grid_size_for_facility(args.facility)

    if not args.fit_only:
        for case in cases:
            fds_path = generate_case(case, out_dir, grid_size, args.dt_devc, args.time_dt, args.lock_time_step)
            validation = json.loads(fds_path.with_name(f"{case.case_id}_validation.json").read_text(encoding="utf-8"))
            if not args.quiet:
                print(
                    "generated "
                    f"{display_path(fds_path)} "
                    f"grid={grid_size:g}m "
                    f"azimuth={case.azimuth:g} "
                    f"q={case.flux:g} duration={case.duration:g}s "
                    f"source-wall={validation['source_wall_distance_m']:.3f}m "
                    f"source-probe={validation['source_probe_distance_m']:.3f}m "
                    f"quantity={validation['quantity']}"
                )
            if not args.generate_only:
                if not args.quiet:
                    print(f"running {case.case_id}")
                run_case(fds_path, args.np, args.runner, args.fds_exe, args.force, args.verbose_fds)

    if args.generate_only:
        return

    rows = []
    for case in cases:
        try:
            if args.window_stats:
                rows.append(read_window_probe_stats(out_dir, case))
            else:
                rows.append(read_max_probe(out_dir, case))
        except Exception as exc:
            if not args.skip_missing:
                raise
            if not args.quiet:
                print(f"skipping {case.case_id}: {exc}")
    if args.window_stats:
        summary_path = write_window_summary(out_dir, rows, args.fit_min, args.fit_max)
    else:
        summary_path = write_summary(out_dir, rows, args.fit_min, args.fit_max)
    print(f"summary {display_path(summary_path)}")
    if args.quiet:
        return

    for row in rows:
        if args.window_stats:
            print(
                f"{row['case_id']}: q_set={float(row['source_flux']):g}, "
                f"azimuth={float(row['azimuth']):g}, "
                f"duration={float(row['duration']):g}, "
                f"t_cut={float(row['cut_time']):.6g}, "
                f"q_avg={float(row['average_flux_0_to_cut']):.6g}, "
                f"q_max_window={float(row['max_flux_0_to_cut']):.6g}"
            )
        else:
            print(
                f"{row['case_id']}: q_set={float(row['source_flux']):g}, "
                f"azimuth={float(row['azimuth']):g}, "
                f"duration={float(row['duration']):g}, "
                f"q_meas_max={float(row['measured_flux_max']):.6g}, "
                f"t_max={float(row['time_of_max']):.6g}"
            )


if __name__ == "__main__":
    main()
