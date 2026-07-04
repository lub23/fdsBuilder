#!/usr/bin/env python3
"""Run a0/e0 RADIATIVE HEAT FLUX GAS wall-probe sweep for Materion Buffalo."""

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
from models.building import BuildingGroup


DEFAULT_DURATIONS = (1.36, 2.1, 7.5)
DEFAULT_FLUXES = (100.0, 200.0, 500.0, 1000.0, 2000.0, 5000.0, 10000.0, 15000.0, 20000.0, 25000.0, 30000.0)


@dataclass(frozen=True)
class SweepCase:
    duration: float
    flux: float

    @property
    def t_end(self) -> float:
        return self.duration + 1.0

    @property
    def case_id(self) -> str:
        d_ms = int(round(self.duration * 1000.0))
        t_ms = int(round(self.t_end * 1000.0))
        q = int(round(self.flux))
        return f"materion_buffalo_q{q}_a0_e0_d{d_ms}_t{t_ms}"


def parse_floats(text: str) -> tuple[float, ...]:
    return tuple(float(part.strip()) for part in text.split(",") if part.strip())


def load_facility() -> dict:
    path = PROJECT_DIR / "facilities" / "materion_buffalo.json"
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_DIR))
    except ValueError:
        return str(path)


def replace_head(text: str, case: SweepCase) -> str:
    title = (
        f"NET_HEAT_FLUX={case.flux:.1f} kW/m2, Azimuth=0, Elevation=0, "
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


def validate_geometry(text: str) -> dict[str, float | str]:
    source_match = re.search(
        r"&VENT[^/]*SURF_ID='radiation_XMAX'[^/]*XB=[^/]+/",
        text,
    )
    if not source_match:
        raise ValueError("missing XMAX radiation source VENT")
    sx0, sx1, sy0, sy1, sz0, sz1 = _numbers_from_xb(source_match.group(0))
    if abs(sx1 - sx0) > 1e-6:
        raise ValueError("XMAX radiation source VENT is not planar")
    source_x = sx0

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
    if quantity != "RADIATIVE HEAT FLUX GAS":
        raise ValueError(f"wrong probe quantity: {quantity}")

    wall_faces: list[float] = []
    for obst_match in re.finditer(r"&OBST[^/]*SURF_ID='WALL'[^/]* /", text):
        x0, x1, y0, y1, z0, z1 = _numbers_from_xb(obst_match.group(0))
        if y0 - 1e-6 <= py <= y1 + 1e-6 and z0 - 1e-6 <= pz <= z1 + 1e-6:
            if x1 <= source_x + 1e-6:
                wall_faces.append(x1)
    if not wall_faces:
        raise ValueError("could not find source-facing WALL OBST at probe y/z")
    wall_x = max(wall_faces)

    source_wall_distance = source_x - wall_x
    source_probe_distance = source_x - px
    expected_source_probe_distance = 1.0 - HEAT_FLUX_PROBE_WALL_OFFSET
    if not math.isclose(source_wall_distance, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(f"source-wall distance is {source_wall_distance:.6g} m, not 1 m")
    if not math.isclose(source_probe_distance, expected_source_probe_distance, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(
            f"source-probe distance is {source_probe_distance:.6g} m, "
            f"not {expected_source_probe_distance:.6g} m"
        )

    return {
        "quantity": quantity,
        "source_x_m": source_x,
        "wall_x_m": wall_x,
        "probe_x_m": px,
        "probe_y_m": py,
        "probe_z_m": pz,
        "source_wall_distance_m": source_wall_distance,
        "source_probe_distance_m": source_probe_distance,
        "probe_wall_offset_m": HEAT_FLUX_PROBE_WALL_OFFSET,
    }


def generate_case(
    case: SweepCase,
    out_dir: Path,
    dt_devc: float,
    time_dt: float | None,
    lock_time_step: bool,
) -> Path:
    data = load_facility()
    bg = BuildingGroup.from_dict(data)
    bg.name = "materion_buffalo"
    bg.domain = {"grid_size": 1.0}
    bg.output = {"slices": False, "devices": True}
    bg.heat_source = {
        "azimuth": 0.0,
        "elevation": 0.0,
        "net_heat_flux": case.flux,
        "duration": case.duration,
    }
    bg.simulation_time = case.t_end

    text = FDSGenerator(bg).generate()
    text = replace_head(text, case)
    text = set_time_and_dump(text, case, dt_devc, time_dt, lock_time_step)
    text = remove_mpi_process_pins(text)
    text = strip_unneeded_devc(text)
    validation = validate_geometry(text)

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
    cut_idx = min(
        range(len(values)),
        key=lambda i: (abs(values[i][0] - case.duration), values[i][0]),
    )
    t_cut = values[cut_idx][0]
    window = values[: cut_idx + 1]
    max_time, max_value = max(window, key=lambda item: item[1])

    if t_cut <= 0 or len(window) < 2:
        avg_value = window[-1][1]
    else:
        area = 0.0
        for (t0, v0), (t1, v1) in zip(window, window[1:]):
            area += 0.5 * (v0 + v1) * (t1 - t0)
        avg_value = area / t_cut

    return {
        "duration": case.duration,
        "t_end": case.t_end,
        "source_flux": case.flux,
        "cut_time": t_cut,
        "cut_time_error": t_cut - case.duration,
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
) -> dict[str, dict[str, dict[str, float | int] | int]]:
    by_duration: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        measured = float(row[metric])
        if fit_min <= measured <= fit_max:
            key = f"{float(row['duration']):.2f}".rstrip("0").rstrip(".")
            by_duration.setdefault(key, []).append((float(row["source_flux"]), measured))

    fits: dict[str, dict[str, dict[str, float | int] | int]] = {}
    for key, points in by_duration.items():
        fits[key] = {"n": len(points)}
        if len(points) >= 2:
            fits[key]["linear"] = fit_linear(points)
        if len(points) >= 3:
            fits[key]["quadratic"] = fit_quadratic(points)
            qfit = fits[key]["quadratic"]
            assert isinstance(qfit, dict)
            q_low = invert_fit(qfit, fit_min)
            q_high = invert_fit(qfit, fit_max)
            fits[key]["source_flux_range_quadratic"] = {
                "measured_min": fit_min,
                "measured_max": fit_max,
                "source_flux_min": q_low,
                "source_flux_max": q_high,
            }
    return fits


def write_summary(out_dir: Path, rows: list[dict[str, float | int | str]], fit_min: float, fit_max: float) -> Path:
    by_duration: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        measured = float(row["measured_flux_max"])
        if fit_min <= measured <= fit_max:
            key = f"{float(row['duration']):.2f}".rstrip("0").rstrip(".")
            by_duration.setdefault(key, []).append((float(row["source_flux"]), measured))

    fits: dict[str, dict[str, dict[str, float | int] | int]] = {}
    for key, points in by_duration.items():
        fits[key] = {"n": len(points)}
        if len(points) >= 2:
            fits[key]["linear"] = fit_linear(points)
        if len(points) >= 3:
            fits[key]["quadratic"] = fit_quadratic(points)

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
    for key in sorted(fits, key=lambda value: float(value)):
        fit = fits[key]
        if "linear" not in fit:
            md_lines.append(f"## Duration {key} s")
            md_lines.append(f"- Not enough points for a linear fit; n={int(fit['n'])}.")
            md_lines.append("")
            continue
        linear_fit = fit["linear"]
        assert isinstance(linear_fit, dict)
        slope = float(linear_fit["slope"])
        intercept = float(linear_fit["intercept"])
        md_lines.append(f"## Duration {key} s")
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
        for key in sorted(fits[metric], key=lambda value: float(value)):
            fit = fits[metric][key]
            md_lines.append(f"### Duration {key} s")
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


def build_cases(durations: tuple[float, ...], fluxes: tuple[float, ...]) -> list[SweepCase]:
    return [SweepCase(duration=d, flux=q) for d in durations for q in fluxes]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="case/rhfg_wall_flux_a0_e0")
    parser.add_argument("--durations", default=",".join(str(x) for x in DEFAULT_DURATIONS))
    parser.add_argument("--fluxes", default=",".join(str(int(x)) for x in DEFAULT_FLUXES))
    parser.add_argument("--dt-devc", type=float, default=0.01)
    parser.add_argument("--time-dt", type=float, default=None)
    parser.add_argument("--lock-time-step", action="store_true")
    parser.add_argument("--np", type=int, default=5)
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
    args = parser.parse_args()

    durations = parse_floats(args.durations)
    fluxes = parse_floats(args.fluxes)
    out_dir = (PROJECT_DIR / args.out_dir).resolve()
    cases = build_cases(durations, fluxes)

    if not args.fit_only:
        for case in cases:
            fds_path = generate_case(case, out_dir, args.dt_devc, args.time_dt, args.lock_time_step)
            validation = json.loads(fds_path.with_name(f"{case.case_id}_validation.json").read_text(encoding="utf-8"))
            print(
                "generated "
                f"{display_path(fds_path)} "
                f"q={case.flux:g} duration={case.duration:g}s "
                f"source-wall={validation['source_wall_distance_m']:.3f}m "
                f"source-probe={validation['source_probe_distance_m']:.3f}m "
                f"quantity={validation['quantity']}"
            )
            if not args.generate_only:
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
            print(f"skipping {case.case_id}: {exc}")
    if args.window_stats:
        summary_path = write_window_summary(out_dir, rows, args.fit_min, args.fit_max)
    else:
        summary_path = write_summary(out_dir, rows, args.fit_min, args.fit_max)
    print(f"summary {display_path(summary_path)}")
    for row in rows:
        if args.window_stats:
            print(
                f"{row['case_id']}: q_set={float(row['source_flux']):g}, "
                f"duration={float(row['duration']):g}, "
                f"t_cut={float(row['cut_time']):.6g}, "
                f"q_avg={float(row['average_flux_0_to_cut']):.6g}, "
                f"q_max_window={float(row['max_flux_0_to_cut']):.6g}"
            )
        else:
            print(
                f"{row['case_id']}: q_set={float(row['source_flux']):g}, "
                f"duration={float(row['duration']):g}, "
                f"q_meas_max={float(row['measured_flux_max']):.6g}, "
                f"t_max={float(row['time_of_max']):.6g}"
            )


if __name__ == "__main__":
    main()
