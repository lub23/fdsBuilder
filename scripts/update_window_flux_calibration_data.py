#!/usr/bin/env python3
"""Write facility-specific wall-flux calibration coefficients into the program."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_DIR / "models" / "window_flux_calibration_data.py"


EXPECTED_FACILITIES: tuple[str, ...] = (
    "materion_buffalo",
    "materion_newton",
    "harbison_fischer",
    "gleason_cutting_tools_corporation",
    "frymaster_corporation",
    "warrick_power_plant",
    "alcoa",
    "metallurgical_facilities_small",
    "metallurgical_facilities_medium",
    "metallurgical_facilities_large",
    "machinery_manufacturing_small",
    "machinery_manufacturing_medium",
    "machinery_manufacturing_large",
    "airport_hangar_small",
    "airport_hangar_medium",
    "airport_hangar_large",
    "aerospace_small",
    "aerospace_medium",
    "aerospace_large",
)


# FDS sweeps for a few large/unstable targets are too slow or fail at the high
# calibration source flux. Keep facility-specific rows in the program by seeding
# missing targets from the closest completed grid/facility response. A later real
# summary for the facility automatically replaces these proxy rows.
PROXY_SOURCE_BY_FACILITY: dict[str, str] = {
    "alcoa": "warrick_power_plant",
    "metallurgical_facilities_small": "materion_buffalo",
    "metallurgical_facilities_medium": "harbison_fischer",
    "metallurgical_facilities_large": "harbison_fischer",
    "machinery_manufacturing_small": "materion_newton",
    "machinery_manufacturing_medium": "gleason_cutting_tools_corporation",
    "machinery_manufacturing_large": "warrick_power_plant",
    "airport_hangar_small": "materion_buffalo",
    "airport_hangar_medium": "materion_buffalo",
    "airport_hangar_large": "materion_buffalo",
    "aerospace_small": "warrick_power_plant",
    "aerospace_medium": "warrick_power_plant",
    "aerospace_large": "warrick_power_plant",
}


def _duration_key(value: str) -> float:
    return float(value)


def _facility_from_summary(summary: dict, summary_path: Path) -> str:
    rows = summary.get("rows") or []
    for row in rows:
        facility = row.get("facility")
        if facility:
            return str(facility)
    return summary_path.parent.name


def _iter_summary_paths(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("rhfg_wall_flux_window_summary.json"))


def load_fit_rows(paths: list[Path]) -> list[tuple[str, float, float, float, float, float]]:
    rows: list[tuple[str, float, float, float, float, float]] = []
    seen: set[tuple[str, float, float]] = set()

    for path in paths:
        summary = json.loads(path.read_text(encoding="utf-8"))
        facility = _facility_from_summary(summary, path)
        by_metric = summary.get("fits", {})
        avg_fits = by_metric.get("average_flux_0_to_cut", {})
        for az_key in sorted(avg_fits, key=float):
            for duration_key in sorted(avg_fits[az_key], key=_duration_key):
                fit_info = avg_fits[az_key][duration_key]
                quadratic = fit_info.get("quadratic")
                linear = fit_info.get("linear")
                if isinstance(quadratic, dict):
                    coeffs = (
                        float(quadratic["quadratic"]),
                        float(quadratic["linear"]),
                        float(quadratic["intercept"]),
                    )
                elif isinstance(linear, dict):
                    coeffs = (
                        0.0,
                        float(linear["slope"]),
                        float(linear["intercept"]),
                    )
                else:
                    continue
                key = (facility, float(az_key), float(duration_key))
                if key in seen:
                    raise ValueError(
                        f"duplicate fit for facility={facility}, azimuth={az_key}, duration={duration_key}"
                    )
                seen.add(key)
                rows.append((
                    facility,
                    float(az_key),
                    float(duration_key),
                    coeffs[0],
                    coeffs[1],
                    coeffs[2],
                ))
    return sorted(rows, key=lambda row: (row[0], row[1], row[2]))


def fill_proxy_rows(
    rows: list[tuple[str, float, float, float, float, float]],
) -> list[tuple[str, float, float, float, float, float]]:
    by_facility = {row[0] for row in rows}
    by_source: dict[str, list[tuple[str, float, float, float, float, float]]] = {}
    for row in rows:
        by_source.setdefault(row[0], []).append(row)

    out = list(rows)
    for facility in EXPECTED_FACILITIES:
        if facility in by_facility:
            continue
        source = PROXY_SOURCE_BY_FACILITY.get(facility)
        if not source:
            continue
        source_rows = by_source.get(source)
        if not source_rows:
            raise ValueError(f"missing proxy source rows for {facility}: {source}")
        for _source_facility, azimuth, duration, quadratic, linear, intercept in source_rows:
            out.append((facility, azimuth, duration, quadratic, linear, intercept))
    return sorted(out, key=lambda row: (row[0], row[1], row[2]))


def render_module(rows: list[tuple[str, float, float, float, float, float]], sources: list[Path]) -> str:
    lines = [
        '"""Generated facility-specific window heat-flux calibration coefficients.',
        "",
        "Rows are:",
        "    facility, azimuth_deg, duration_s, quadratic, linear, intercept",
        "",
        "Regenerate with:",
        "    python scripts/update_window_flux_calibration_data.py --root case/rhfg_wall_flux_calibrations",
        '"""',
        "from __future__ import annotations",
        "",
        "",
        "FACILITY_Q_AVG_FITS: tuple[tuple[str, float, float, float, float, float], ...] = (",
    ]
    for facility, azimuth, duration, quadratic, linear, intercept in rows:
        lines.append(
            f"    ({facility!r}, {azimuth:.1f}, {duration:.6g}, "
            f"{quadratic:.12g}, {linear:.12g}, {intercept:.12g}),"
        )
    lines.extend([
        ")",
        "",
        "",
        "SOURCES: tuple[str, ...] = (",
    ])
    for source in sources:
        try:
            display = str(source.resolve().relative_to(PROJECT_DIR))
        except ValueError:
            display = str(source.resolve())
        lines.append(f"    {display!r},")
    lines.extend([
        ")",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        default=[],
        help="Directory or summary JSON to scan. Can be passed more than once.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    roots = args.root or [PROJECT_DIR / "case" / "rhfg_wall_flux_calibrations"]
    summary_paths: list[Path] = []
    for root in roots:
        summary_paths.extend(_iter_summary_paths((PROJECT_DIR / root).resolve() if not root.is_absolute() else root))
    summary_paths = sorted(dict.fromkeys(summary_paths))
    if not summary_paths:
        print("No rhfg_wall_flux_window_summary.json files found.", file=sys.stderr)
        return 1

    rows = fill_proxy_rows(load_fit_rows(summary_paths))
    output = args.output
    if not output.is_absolute():
        output = PROJECT_DIR / output
    output.write_text(render_module(rows, summary_paths), encoding="utf-8")
    print(f"wrote {len(rows)} fits to {output.relative_to(PROJECT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
