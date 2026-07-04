#!/usr/bin/env python3
"""Fit wall heat-flux response for the Materion Buffalo FDS model.

The generated fitting decks use:
- facility: facilities/materion_buffalo.json
- grid: 1 m across the whole domain
- probes at the source-facing wall, z = facility zmax / 2:
  ``incident_heat_flux`` is the horizontal wall-normal component, and
  ``vertical_heat_flux`` is the vertical component on the nearest clean
  exterior gas-cell top face.  FDS cannot attach this horizontal-surface
  device to the first exterior cell because the thickened wall occupies it.

Three case families are supported:
- side: side boundary heat source only
- top: top strip heat source only
- combo: side + top heat sources together
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from generators.fds_generator import FDSGenerator
from models.building import BuildingGroup


DEFAULT_DURATIONS = (1.36, 2.1, 7.5)
DEFAULT_FLUXES = (200.0, 500.0, 1000.0, 2000.0, 5000.0, 10000.0, 15000.0)
DEFAULT_COMBOS = ((500.0, 500.0), (1000.0, 1000.0), (2000.0, 1000.0))


@dataclass(frozen=True)
class FitCase:
    kind: str
    duration: float
    side_flux: float
    top_flux: float

    @property
    def case_id(self) -> str:
        d_ms = int(round(self.duration * 1000))
        if self.kind == "side":
            return f"mb_s_d{d_ms}_q{int(round(self.side_flux))}"
        if self.kind == "top":
            return f"mb_t_d{d_ms}_q{int(round(self.top_flux))}"
        return (
            f"mb_c_d{d_ms}_s{int(round(self.side_flux))}"
            f"_t{int(round(self.top_flux))}"
        )


def parse_floats(text: str) -> tuple[float, ...]:
    return tuple(float(x.strip()) for x in text.split(",") if x.strip())


def load_facility() -> dict:
    path = PROJECT_DIR / "facilities" / "materion_buffalo.json"
    return json.loads(path.read_text(encoding="utf-8"))


def case_heat_source(case: FitCase) -> dict:
    if case.kind == "side":
        net = case.side_flux
        elevation = 0.0
    elif case.kind == "top":
        net = case.top_flux
        elevation = 90.0
    else:
        net = math.hypot(case.side_flux, case.top_flux)
        elevation = math.degrees(math.atan2(case.top_flux, case.side_flux))
    return {
        "azimuth": 0.0,
        "elevation": elevation,
        "net_heat_flux": net,
        "duration": case.duration,
    }


def replace_head(text: str, case_id: str, case: FitCase) -> str:
    title = (
        f"{case.kind}: side={case.side_flux:.1f} kW/m2, "
        f"top={case.top_flux:.1f} kW/m2, duration={case.duration:.2f}s"
    )
    return re.sub(
        r"&HEAD CHID='[^']+', TITLE='[^']*' /",
        f"&HEAD CHID='{case_id}', TITLE='{title}' /",
        text,
        count=1,
    )


def strip_unneeded_devc(text: str) -> str:
    """Keep only TIMER->OUT and heat-flux DEVC blocks."""
    keep_ids = ("ID='TIMER->OUT'", "ID='incident_heat_flux'", "ID='vertical_heat_flux'")
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


def replace_wall_probe_with_target(text: str) -> str:
    """Replace gas wall-flux DEVC with a grid-face target plate measurement.

    For the fitting study azimuth is fixed at 0, so the source-facing wall is
    x_max.  FDS accepts ``INCIDENT HEAT FLUX`` on a grid-aligned target face
    with ``IOR=-1``; direct placement on the physical thin wall triggers
    ERROR(427), and gas radiative gauges read zero for the external boundary
    heat source.
    """
    pattern = re.compile(
        r"&DEVC XYZ=([-\d.]+),([-\d.]+),([-\d.]+),\n"
        r"\s+QUANTITY='RADIATIVE HEAT FLUX GAS',\n"
        r"\s+ORIENTATION=1\.000,0\.000,0\.000,\n"
        r"\s+ID='incident_heat_flux' /[^\n]*\n",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return text

    px, py, pz = (float(match.group(i)) for i in range(1, 4))
    face_x = px
    top_z = math.floor(pz)
    target = (
        f"&OBST XB={face_x - 1:.2f},{face_x:.2f},"
        f"{py - 0.5:.2f},{py + 0.5:.2f},"
        f"{pz - 0.5:.2f},{pz + 0.5:.2f}, "
        "SURF_ID='WALL', ID='WALL_FLUX_TARGET' /\n"
        f"&DEVC XYZ={face_x:.2f},{py:.2f},{pz:.2f},\n"
        "      QUANTITY='INCIDENT HEAT FLUX',\n"
        "      IOR=1,\n"
        "      ID='incident_heat_flux' /  ! target-plate wall-normal incident heat flux\n"
        f"&OBST XB={face_x + 1:.2f},{face_x + 2:.2f},"
        f"{math.floor(py):.2f},{math.floor(py) + 1:.2f},"
        f"{top_z - 1:.2f},{top_z:.2f}, "
        "SURF_ID='WALL', ID='VERTICAL_FLUX_TARGET' /\n"
        f"&DEVC XYZ={face_x + 1.5:.2f},{math.floor(py) + 0.5:.2f},{top_z:.2f},\n"
        "      QUANTITY='INCIDENT HEAT FLUX',\n"
        "      IOR=3,\n"
        "      ID='vertical_heat_flux' /  ! nearest clean exterior top-surface component\n"
    )
    return pattern.sub(target, text, count=1)


def extend_xmax_domain_for_vertical_target(text: str) -> str:
    """Extend the +X side of the fitting deck by one 1 m cell.

    The physical building still has a 1 m source-to-wall gap.  The extra cell
    is only a clean measurement cell for the horizontal top-face DEVC; the
    ZMAX_TOP radiation strip remains in the original wall-adjacent cell.
    """
    mesh_re = re.compile(
        r"&MESH ID='([^']+)', IJK=(\d+),(\d+),(\d+), "
        r"XB=([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+) /"
    )
    meshes = list(mesh_re.finditer(text))
    if not meshes:
        return text
    old_xmax = max(float(m.group(6)) for m in meshes)
    new_xmax = old_xmax + 1.0

    def mesh_repl(match: re.Match) -> str:
        mesh_id = match.group(1)
        nx, ny, nz = (int(match.group(i)) for i in range(2, 5))
        x0, x1, y0, y1, z0, z1 = (float(match.group(i)) for i in range(5, 11))
        if abs(x1 - old_xmax) < 1e-6:
            nx += 1
            x1 = new_xmax
        return (
            f"&MESH ID='{mesh_id}', IJK={nx},{ny},{nz}, "
            f"XB={x0:.2f},{x1:.2f},{y0:.2f},{y1:.2f},{z0:.2f},{z1:.2f} /"
        )

    text = mesh_re.sub(mesh_repl, text)

    vent_re = re.compile(
        r"(&VENT ID='([^']+)', SURF_ID='([^']+)'(?:, DEVC_ID='[^']+')?, "
        r"XB=)([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)( /[^\n]*\n)"
    )
    zmax_top: tuple[float, float, float] | None = None

    def vent_repl(match: re.Match) -> str:
        nonlocal zmax_top
        prefix = match.group(1)
        vent_id = match.group(2)
        surf_id = match.group(3)
        x0, x1, y0, y1, z0, z1 = (float(match.group(i)) for i in range(4, 10))
        suffix = match.group(10)
        if vent_id == "Domain Vent [ZMAX_TOP]":
            zmax_top = (y0, y1, z0)
        if abs(x0 - old_xmax) < 1e-6 and abs(x1 - old_xmax) < 1e-6:
            x0 = x1 = new_xmax
        elif surf_id == "OPEN" and abs(x1 - old_xmax) < 1e-6 and x0 < old_xmax:
            x1 = new_xmax
        return (
            f"{prefix}{x0:.2f},{x1:.2f},{y0:.2f},{y1:.2f},{z0:.2f},{z1:.2f}{suffix}"
        )

    text = vent_re.sub(vent_repl, text)
    if zmax_top and "ZMAX_OPEN_EXTRA" not in text:
        y0, y1, z = zmax_top
        extra = (
            f"&VENT ID='Domain Vent [ZMAX_OPEN_EXTRA]', SURF_ID='OPEN', "
            f"XB={old_xmax:.2f},{new_xmax:.2f},{y0:.2f},{y1:.2f},{z:.2f},{z:.2f} / "
            "! [ZMAX_OPEN_EXTRA]\n"
        )
        text = text.replace("&VENT ID='Domain Vent [ZMAX_OPEN_2]'", extra + "&VENT ID='Domain Vent [ZMAX_OPEN_2]'", 1)
    return text


def generate_case(case: FitCase, out_dir: Path, margin: float) -> Path:
    data = load_facility()
    bg = BuildingGroup.from_dict(data)
    bg.name = "materion_buffalo"
    bg.domain = {"grid_size": 1.0}
    bg.output = {"slices": False, "devices": True}
    bg.heat_source = case_heat_source(case)
    bg.simulation_time = case.duration + margin

    text = FDSGenerator(bg).generate()
    text = replace_head(text, case.case_id, case)
    text = replace_wall_probe_with_target(text)
    text = extend_xmax_domain_for_vertical_target(text)
    text = strip_unneeded_devc(text)

    out_dir.mkdir(parents=True, exist_ok=True)
    fds_path = out_dir / f"{case.case_id}.fds"
    fds_path.write_text(text, encoding="utf-8")
    return fds_path


def run_case(fds_path: Path, np: int, force: bool = False) -> None:
    out_path = fds_path.with_suffix(".out")
    if out_path.exists() and not force:
        return
    cmd = ["mpiexec", "-n", str(np), "fds", fds_path.name]
    subprocess.run(cmd, cwd=fds_path.parent, check=True)


def read_probe_values(out_dir: Path, case: FitCase) -> dict[str, float]:
    csv_path = out_dir / f"{case.case_id}_devc.csv"
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        if header and header[0].strip() != "Time":
            header = next(reader)
        probe_indices: dict[str, int] = {}
        for idx, name in enumerate(header):
            stripped = name.strip()
            if stripped in {"incident_heat_flux", "vertical_heat_flux"}:
                probe_indices[stripped] = idx
        missing = {"incident_heat_flux", "vertical_heat_flux"} - set(probe_indices)
        if missing:
            raise ValueError(f"{csv_path}: missing columns {sorted(missing)}")

        prev_sample: tuple[float, dict[str, float]] | None = None
        next_sample: tuple[float, dict[str, float]] | None = None
        for row in reader:
            if len(row) <= max(probe_indices.values()):
                continue
            try:
                t = float(row[0])
                values = {
                    name: float(row[idx])
                    for name, idx in probe_indices.items()
                }
            except ValueError:
                continue
            if t <= case.duration + 1e-9:
                if prev_sample is None or t >= prev_sample[0]:
                    prev_sample = (t, values)
            if t >= case.duration - 1e-9:
                if next_sample is None or t <= next_sample[0]:
                    next_sample = (t, values)

    if prev_sample is None and next_sample is None:
        raise ValueError(f"{csv_path}: no probe samples around duration")
    if prev_sample is None:
        return next_sample[1]
    if next_sample is None:
        return prev_sample[1]
    t0, v0 = prev_sample
    t1, v1 = next_sample
    if abs(t1 - t0) < 1e-12:
        return v0
    frac = (case.duration - t0) / (t1 - t0)
    return {
        name: v0[name] + (v1[name] - v0[name]) * frac
        for name in v0
    }


def fit_linear(points: list[tuple[float, float]]) -> dict:
    n = len(points)
    if n < 2:
        raise ValueError("need at least two points")
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points)
    sxy = sum(x * y for x, y in points)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        raise ValueError("singular fit")
    a = (n * sxy - sx * sy) / denom
    b = (sy - a * sx) / n
    y_mean = sy / n
    ss_tot = sum((y - y_mean) ** 2 for _, y in points)
    ss_res = sum((y - (a * x + b)) ** 2 for x, y in points)
    r2 = 1.0 if ss_tot <= 1e-12 else 1 - ss_res / ss_tot
    return {"slope": a, "intercept": b, "r2": r2, "n": n}


def _solve_3x3(a: list[list[float]], b: list[float]) -> list[float]:
    rows = [a[i][:] + [b[i]] for i in range(3)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError("singular fit")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        div = rows[col][col]
        rows[col] = [x / div for x in rows[col]]
        for r in range(3):
            if r == col:
                continue
            factor = rows[r][col]
            rows[r] = [rows[r][c] - factor * rows[col][c] for c in range(4)]
    return [rows[i][3] for i in range(3)]


def fit_quadratic(points: list[tuple[float, float]]) -> dict:
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
    y_mean = sy / n
    ss_tot = sum((y - y_mean) ** 2 for _, y in points)
    ss_res = sum((y - (a2 * x**2 + a1 * x + a0)) ** 2 for x, y in points)
    r2 = 1.0 if ss_tot <= 1e-12 else 1 - ss_res / ss_tot
    return {"quadratic": a2, "linear": a1, "intercept": a0, "r2": r2, "n": n}


def interpolate(points: list[tuple[float, float]], x: float) -> float:
    ordered = sorted(points)
    if x <= ordered[0][0]:
        return ordered[0][1]
    if x >= ordered[-1][0]:
        return ordered[-1][1]
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if x0 <= x <= x1:
            if abs(x1 - x0) < 1e-12:
                return y0
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    raise ValueError(f"cannot interpolate x={x}")


def build_cases(
    durations: tuple[float, ...],
    fluxes: tuple[float, ...],
    combos: tuple[tuple[float, float], ...],
) -> list[FitCase]:
    cases: list[FitCase] = []
    for d in durations:
        for q in fluxes:
            cases.append(FitCase("side", d, q, 0.0))
            cases.append(FitCase("top", d, 0.0, q))
        for side_q, top_q in combos:
            cases.append(FitCase("combo", d, side_q, top_q))
    return cases


def write_summary(out_dir: Path, cases: list[FitCase]) -> Path:
    rows = []
    for case in cases:
        try:
            values = read_probe_values(out_dir, case)
        except Exception as exc:
            rows.append({
                **case.__dict__,
                "case_id": case.case_id,
                "horizontal_flux": None,
                "vertical_flux": None,
                "response_flux": None,
                "error": str(exc),
            })
            continue
        response_flux = (
            values["incident_heat_flux"]
            if case.kind == "side"
            else values["vertical_heat_flux"]
        )
        rows.append({
            **case.__dict__,
            "case_id": case.case_id,
            "horizontal_flux": values["incident_heat_flux"],
            "vertical_flux": values["vertical_heat_flux"],
            "response_flux": response_flux,
            "error": "",
        })

    by_duration: dict[str, dict[str, list[tuple[float, float]]]] = {}
    components: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for row in rows:
        if row["response_flux"] is None:
            continue
        d_key = f"{row['duration']:.2f}".rstrip("0").rstrip(".")
        by_duration.setdefault(d_key, {"side": [], "top": []})
        components.setdefault(
            d_key,
            {"side_h": [], "side_v": [], "top_h": [], "top_v": []},
        )
        if row["kind"] == "side":
            by_duration[d_key]["side"].append((row["side_flux"], row["horizontal_flux"]))
            components[d_key]["side_h"].append((row["side_flux"], row["horizontal_flux"]))
            components[d_key]["side_v"].append((row["side_flux"], row["vertical_flux"]))
        elif row["kind"] == "top":
            by_duration[d_key]["top"].append((row["top_flux"], row["vertical_flux"]))
            components[d_key]["top_h"].append((row["top_flux"], row["horizontal_flux"]))
            components[d_key]["top_v"].append((row["top_flux"], row["vertical_flux"]))

    fits = {}
    for d_key, groups in by_duration.items():
        fits[d_key] = {}
        for kind, points in groups.items():
            if len(points) >= 2:
                fits[d_key][kind] = {"linear": fit_linear(points)}
            if len(points) >= 3:
                fits[d_key][kind]["quadratic"] = fit_quadratic(points)

    combo_checks = []
    for row in rows:
        if row["kind"] != "combo" or row["response_flux"] is None:
            continue
        d_key = f"{row['duration']:.2f}".rstrip("0").rstrip(".")
        groups = components.get(d_key)
        if not groups:
            continue
        side_h = groups.get("side_h", [])
        side_v = groups.get("side_v", [])
        top_h = groups.get("top_h", [])
        top_v = groups.get("top_v", [])
        if min(len(side_h), len(side_v), len(top_h), len(top_v)) < 2:
            continue
        # No q=0 run is included because the requested sweep starts at 200.
        # The horizontal top-source response is effectively the target baseline.
        baseline = sum(y for _, y in top_h) / len(top_h)
        horizontal_pred = (
            interpolate(side_h, row["side_flux"])
            + interpolate(top_h, row["top_flux"])
            - baseline
        )
        vertical_pred = (
            interpolate(side_v, row["side_flux"])
            + interpolate(top_v, row["top_flux"])
            - baseline
        )
        measured_vector = math.hypot(
            row["horizontal_flux"] - baseline,
            row["vertical_flux"] - baseline,
        )
        vector_sum = math.hypot(horizontal_pred - baseline, vertical_pred - baseline)
        combo_checks.append({
            "case_id": row["case_id"],
            "duration": row["duration"],
            "side_flux": row["side_flux"],
            "top_flux": row["top_flux"],
            "measured_horizontal": row["horizontal_flux"],
            "pred_horizontal": horizontal_pred,
            "horizontal_rel_err": (horizontal_pred - row["horizontal_flux"]) / row["horizontal_flux"],
            "measured_vertical": row["vertical_flux"],
            "pred_vertical": vertical_pred,
            "vertical_rel_err": (vertical_pred - row["vertical_flux"]) / row["vertical_flux"],
            "baseline": baseline,
            "vector_delta_measured": measured_vector,
            "vector_sum_pred": vector_sum,
            "vector_sum_rel_err": (
                (vector_sum - measured_vector) / measured_vector
                if abs(measured_vector) > 1e-12 else None
            ),
        })

    summary = {"rows": rows, "fits": fits, "combo_checks": combo_checks}
    summary_path = out_dir / "fit_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = ["# Materion Buffalo Wall Heat-Flux Fit", ""]
    for d_key, groups in fits.items():
        md_lines.append(f"## Duration {d_key} s")
        for kind, fit_group in groups.items():
            fit = fit_group["linear"]
            label = "side->H" if kind == "side" else "top->V"
            md_lines.append(
                f"- {label} linear: wall_flux = {fit['slope']:.6g} * source_flux "
                f"+ {fit['intercept']:.6g}, R2={fit['r2']:.5f}, n={fit['n']}"
            )
            fit = fit_group.get("quadratic")
            if fit:
                md_lines.append(
                    f"- {label} quadratic: wall_flux = {fit['quadratic']:.6g} * source_flux^2 "
                    f"+ {fit['linear']:.6g} * source_flux + {fit['intercept']:.6g}, "
                    f"R2={fit['r2']:.5f}, n={fit['n']}"
                )
        md_lines.append("")
    if combo_checks:
        md_lines.extend(["## Combo Checks", ""])
        for item in combo_checks:
            md_lines.append(
                f"- {item['case_id']}: "
                f"H measured={item['measured_horizontal']:.6g}, pred={item['pred_horizontal']:.6g} "
                f"(rel_err={item['horizontal_rel_err']:.2%}); "
                f"V measured={item['measured_vertical']:.6g}, pred={item['pred_vertical']:.6g} "
                f"(rel_err={item['vertical_rel_err']:.2%}); "
                f"vector_delta measured={item['vector_delta_measured']:.6g}, "
                f"pred={item['vector_sum_pred']:.6g} "
                f"(rel_err={item['vector_sum_rel_err']:.2%})"
            )
    md_path = out_dir / "fit_summary.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="case/fit_results/materion_buffalo_wall_flux")
    parser.add_argument("--durations", default=",".join(str(x) for x in DEFAULT_DURATIONS))
    parser.add_argument("--fluxes", default=",".join(str(int(x)) for x in DEFAULT_FLUXES))
    parser.add_argument(
        "--combos",
        default=";".join(f"{int(s)}:{int(t)}" for s, t in DEFAULT_COMBOS),
        help="semicolon list of side:top flux pairs",
    )
    parser.add_argument("--np", type=int, default=4)
    parser.add_argument("--margin", type=float, default=0.25)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--fit-only", action="store_true")
    args = parser.parse_args()

    durations = parse_floats(args.durations)
    fluxes = parse_floats(args.fluxes)
    combos = tuple(
        tuple(float(x) for x in part.split(":", 1))
        for part in args.combos.split(";")
        if part.strip()
    )
    out_dir = (PROJECT_DIR / args.out_dir).resolve()
    cases = build_cases(durations, fluxes, combos)

    if not args.fit_only:
        for case in cases:
            fds_path = generate_case(case, out_dir, args.margin)
            print(f"generated {fds_path.relative_to(PROJECT_DIR)}")
            if not args.generate_only:
                print(f"running {case.case_id}")
                run_case(fds_path, args.np, force=args.force)

    summary_path = write_summary(out_dir, cases)
    print(f"summary {summary_path.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
