#!/usr/bin/env python3
"""Audit whether observed FDS cases bracket Dk thresholds densely enough.

This is deliberately separate from the surrogate's dense q scan: a fine model
scan cannot manufacture physical support between two widely separated FDS
conditions.  The CSV identifies coarse observed brackets and directions that
still need a 20 MW/m² endpoint.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.src.data.experimental import (  # noqa: E402
    DK_THRESHOLDS,
    grade_name,
    load_experimental_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FACILITIES = (
    "aerospace_small",
    "airport_hangar_large",
    "airport_hangar_small",
    "machinery_manufacturing_medium",
)


def _rounded_midpoint(low: float, high: float) -> float:
    midpoint = (float(low) + float(high)) / 2.0
    rounded = round(midpoint / 250.0) * 250.0
    if rounded <= low or rounded >= high:
        rounded = midpoint
    return float(rounded)


def audit_facility(
    df: pd.DataFrame,
    facility: str,
    *,
    max_flux: float,
    coarse_gap: float,
) -> list[dict[str, object]]:
    selected = df[df["facility_name"].eq(facility)]
    rows: list[dict[str, object]] = []
    group_columns = [
        "heat_azimuth_deg",
        "heat_elevation_deg",
        "radiation_duration_ms",
        "case_t_end_s",
    ]
    for condition, group in selected.groupby(group_columns, dropna=False):
        azimuth, elevation, duration_ms, t_end_s = map(float, condition)
        # Duplicate q values are collapsed conservatively, then a monotonic
        # envelope is used only for locating the first observed crossing.
        curve = (
            group.groupby("heat_flux_kw_m2", as_index=False)["Dk"]
            .max()
            .sort_values("heat_flux_kw_m2")
        )
        q = curve["heat_flux_kw_m2"].to_numpy(dtype=float)
        dk = np.maximum.accumulate(curve["Dk"].to_numpy(dtype=float))
        if not len(q):
            continue
        for threshold in DK_THRESHOLDS:
            hits = np.flatnonzero(dk >= threshold)
            record: dict[str, object] = {
                "facility_name": facility,
                "target_grade": grade_name(DK_THRESHOLDS.index(threshold) + 1),
                "dk_threshold": float(threshold),
                "azimuth_deg": azimuth,
                "elevation_deg": elevation,
                "duration_ms": duration_ms,
                "t_end_s": t_end_s,
                "observed_min_flux": float(q[0]),
                "observed_max_flux": float(q[-1]),
                "lower_flux": np.nan,
                "upper_flux": np.nan,
                "bracket_gap": np.nan,
                "status": "",
                "recommended_flux": np.nan,
                "recommendation": "",
            }
            if not len(hits):
                record["status"] = "not_reached"
                if q[-1] < max_flux:
                    record["recommended_flux"] = max_flux
                    record["recommendation"] = "补充上限工况以确认阈值或右删失"
                else:
                    record["recommendation"] = "20 MW/m²仍未跨越；按右删失处理"
            else:
                hit = int(hits[0])
                if hit == 0:
                    record["status"] = "left_censored"
                    record["upper_flux"] = float(q[0])
                    record["recommendation"] = "最低已有工况已跨越；如需下界应补更低热通量"
                else:
                    low, high = float(q[hit - 1]), float(q[hit])
                    gap = high - low
                    record.update(
                        {
                            "lower_flux": low,
                            "upper_flux": high,
                            "bracket_gap": gap,
                            "status": "coarse_bracket" if gap > coarse_gap else "bracketed",
                        }
                    )
                    if gap > coarse_gap:
                        record["recommended_flux"] = min(
                            _rounded_midpoint(low, high), max_flux
                        )
                        record["recommendation"] = "在跨阈值区间中点补算，缩小物理插值跨度"
            rows.append(record)
    return rows


def _fmt_flux(value: float) -> str:
    return f"{value:,.0f}"


def write_markdown(path: Path, audit: pd.DataFrame, coarse_gap: float, max_flux: float) -> None:
    lines = [
        "# 四个新增设施的阈值数据覆盖审计",
        "",
        "> 本审计检查的是实际 FDS 数据对 Dk 阈值的支撑，不是模型扫描步长。"
        "即使模型按很细的 q 网格扫描，两个实际工况相距过大时仍属于粗插值。",
        "",
        f"- 粗插值判据：相邻实际热通量跨度 > {_fmt_flux(coarse_gap)} kW/m²。",
        f"- 最高允许工况：{_fmt_flux(max_flux)} kW/m²；达到上限仍不跨越则右删失。",
        "",
        "| 设施 | 粗阈值区间数 | 未跨越且缺上限数 | 20 MW/m²右删失数 | 建议新增 q (kW/m²) |",
        "|---|---:|---:|---:|---|",
    ]
    for facility in DEFAULT_FACILITIES:
        part = audit[audit["facility_name"].eq(facility)]
        coarse = int(part["status"].eq("coarse_bracket").sum())
        missing_endpoint = int(
            (part["status"].eq("not_reached") & part["recommended_flux"].notna()).sum()
        )
        censored = int(
            (part["status"].eq("not_reached") & part["recommended_flux"].isna()).sum()
        )
        suggestions = sorted(set(part["recommended_flux"].dropna().astype(float)))
        suggestion_text = ", ".join(_fmt_flux(v) for v in suggestions) or "无"
        lines.append(
            f"| `{facility}` | {coarse} | {missing_endpoint} | {censored} | {suggestion_text} |"
        )

    lines.extend(["", "## 建议工况明细", ""])
    recommended = audit[audit["recommended_flux"].notna()].copy()
    for facility in DEFAULT_FACILITIES:
        part = recommended[recommended["facility_name"].eq(facility)]
        lines.append(f"### `{facility}`")
        if part.empty:
            lines.extend(["", "无需补充阈值定位工况。", ""])
            continue
        grouped = part.groupby("recommended_flux")
        lines.append("")
        for flux, rows in grouped:
            azimuths = ", ".join(f"{v:g}°" for v in sorted(rows["azimuth_deg"].unique()))
            elevations = ", ".join(f"{v:g}°" for v in sorted(rows["elevation_deg"].unique()))
            durations = ", ".join(
                f"{v / 1000:g}s" for v in sorted(rows["duration_ms"].unique())
            )
            reasons = "；".join(sorted(set(rows["recommendation"])))
            lines.append(
                f"- q={_fmt_flux(float(flux))}：a={azimuths}，e={elevations}，"
                f"d={durations}；{reasons}。"
            )
        lines.append("")
    lines.extend(
        [
            "## 使用说明",
            "",
            "- CSV 保留逐个 `方位角 × 俯仰角 × 持续时间 × 等级阈值` 的区间和建议，实际生成补算清单时以 CSV 为准。",
            "- 同一建议 q 可同时服务多个等级阈值，生成 FDS 前应按 `facility + q + a + e + d + t` 去重。",
            "- `left_censored` 表示最低已有 q 已越过阈值；它不是粗插值，但若需要精确下界应继续向低热通量补算。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-dir", type=Path, default=ROOT / "cases")
    parser.add_argument("--facilities", nargs="+", default=list(DEFAULT_FACILITIES))
    parser.add_argument("--max-flux", type=float, default=20000.0)
    parser.add_argument("--coarse-gap", type=float, default=2000.0)
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=ROOT / "output" / "experimental_threshold_data_audit.csv",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=ROOT / "output" / "experimental_threshold_data_audit.md",
    )
    parser.add_argument(
        "--output-recommendations",
        type=Path,
        default=ROOT / "output" / "experimental_threshold_recommended_cases.csv",
    )
    args = parser.parse_args()

    df = load_experimental_dataset(args.cases_dir)
    rows: list[dict[str, object]] = []
    for facility in args.facilities:
        if not df["facility_name"].eq(facility).any():
            raise RuntimeError(f"Facility not found in dataset: {facility}")
        rows.extend(
            audit_facility(
                df,
                facility,
                max_flux=float(args.max_flux),
                coarse_gap=float(args.coarse_gap),
            )
        )
    audit = pd.DataFrame(rows)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.output_csv, index=False)
    recommendation_columns = [
        "facility_name",
        "recommended_flux",
        "azimuth_deg",
        "elevation_deg",
        "duration_ms",
        "t_end_s",
    ]
    recommended = (
        audit[audit["recommended_flux"].notna()][recommendation_columns]
        .drop_duplicates()
        .sort_values(recommendation_columns)
        .rename(columns={"recommended_flux": "heat_flux_kw_m2"})
    )

    def case_number(value: float) -> str:
        return f"{float(value):g}"

    recommended["case_name"] = [
        f"{row.facility_name}_q{case_number(row.heat_flux_kw_m2)}"
        f"_a{case_number(row.azimuth_deg)}_e{case_number(row.elevation_deg)}"
        f"_d{case_number(row.duration_ms)}_t{case_number(row.t_end_s)}"
        for row in recommended.itertuples(index=False)
    ]
    recommended.to_csv(args.output_recommendations, index=False)
    write_markdown(args.output_md, audit, float(args.coarse_gap), float(args.max_flux))
    print(f"[threshold_audit] rows={len(audit)} csv={args.output_csv}")
    print(f"[threshold_audit] report={args.output_md}")
    print(
        f"[threshold_audit] recommended_cases={len(recommended)} "
        f"csv={args.output_recommendations}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
