#!/usr/bin/env python3
"""Generate full threshold maps and reports from an existing trained artifact.

This keeps the relatively expensive 36-facility threshold scan independent
from model selection/CV, and makes it safe to refresh charts after a training
run that used ``--skip-threshold-heatmaps``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.scripts import train_experimental as train  # noqa: E402
from agent_damage.src.data.experimental import load_experimental_dataset  # noqa: E402

THRESHOLD_ALGORITHM_VERSION = 5


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-dir", type=Path, default=train.CASES_DIR)
    parser.add_argument("--model", type=Path, default=train.CKPT_DIR / "experimental_dk_regressor.pkl")
    parser.add_argument("--summary", type=Path, default=train.OUTPUT_DIR / "experimental_train_summary.json")
    parser.add_argument("--scan-min-flux", type=float, default=100.0)
    parser.add_argument("--scan-max-flux", type=float, default=20000.0)
    parser.add_argument("--scan-flux-points", type=int, default=81)
    parser.add_argument("--threshold-azimuth-step", type=float, default=10.0)
    parser.add_argument("--threshold-elevation-step", type=float, default=5.0)
    parser.add_argument("--worker-facility", default="")
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/fdsbuilder_threshold_cache_20260713"))
    args = parser.parse_args()

    with args.summary.open("r", encoding="utf-8") as stream:
        summary = json.load(stream)

    min_completion = float(summary.get("min_completion", 0.0))
    min_simulation_time_s = float(summary.get("min_simulation_time_s", 100.0))
    df = load_experimental_dataset(
        args.cases_dir,
        min_completion=min_completion,
        min_simulation_time_s=min_simulation_time_s,
    )
    expected_rows = int(summary.get("row_counts", {}).get("all", -1))
    if expected_rows >= 0 and len(df) != expected_rows:
        raise RuntimeError(
            f"Dataset changed since training: summary={expected_rows} rows, current={len(df)}. "
            "Retrain before generating threshold maps."
        )

    # Cache entries must never be reused across a retrain. The previous fixed
    # cache directory could silently combine a new model with old threshold
    # JSON/figures. Coordinator runs therefore get a content-addressed child
    # directory; workers receive that final directory unchanged.
    if not args.worker_facility:
        digest = hashlib.sha256()
        with args.model.open("rb") as model_stream:
            for chunk in iter(lambda: model_stream.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(
            (
                f"|rows={len(df)}|min={args.scan_min_flux}|max={args.scan_max_flux}|points={args.scan_flux_points}"
                f"|a={args.threshold_azimuth_step}|e={args.threshold_elevation_step}"
                f"|algorithm={THRESHOLD_ALGORITHM_VERSION}"
            ).encode("ascii")
        )
        args.cache_dir = args.cache_dir / digest.hexdigest()[:16]
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    if args.worker_facility:
        facility_df = df[df["facility_name"] == args.worker_facility]
        if facility_df.empty:
            raise RuntimeError(f"Unknown facility: {args.worker_facility}")
        with args.model.open("rb") as stream:
            artifact = pickle.load(stream)
        model = artifact["model"]
        train._set_prediction_n_jobs(model, 1)
        rows, figure_paths = train._generate_threshold_heatmaps(
            model,
            facility_df,
            args.cases_dir,
            dict(artifact["facility_index_map"]),
            tuple(artifact["facility_onehot_columns"]),
            train.FIGURE_DIR,
            max_flux=args.scan_max_flux,
            min_flux=args.scan_min_flux,
            flux_points=args.scan_flux_points,
            azimuth_step=args.threshold_azimuth_step,
            elevation_step=args.threshold_elevation_step,
            max_facilities=None,
            cleanup_stale=False,
        )
        cache_path = args.cache_dir / f"{args.worker_facility}.json"
        cache_path.write_text(
            json.dumps({"rows": train._json_safe(rows), "figure_paths": figure_paths}, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[threshold_worker] {args.worker_facility}: {len(rows)} rows")
        return 0

    facilities = sorted(str(name) for name in df["facility_name"].unique())
    observed_max_dk = df.groupby("facility_name")["Dk"].max()
    omitted_facilities = sorted(
        str(name)
        for name, value in observed_max_dk.items()
        if float(value) < train.DK_THRESHOLDS[0]
    )
    plotted_facilities = [name for name in facilities if name not in omitted_facilities]
    expected_figure_names = {
        f"threshold_grid_{name}.png".replace("/", "_") for name in plotted_facilities
    }
    train.THRESHOLD_FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    for old_path in train.THRESHOLD_FIGURE_DIR.glob("threshold_grid_*.png"):
        if old_path.name not in expected_figure_names:
            old_path.unlink()

    for facility in facilities:
        cache_path = args.cache_dir / f"{facility}.json"
        if cache_path.is_file():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                cached_figures = [Path(path) for path in cached.get("figure_paths", [])]
            except (OSError, ValueError, TypeError):
                cached_figures = [Path("/__invalid_cache_entry__")]
            if all(path.is_file() for path in cached_figures):
                print(f"[threshold_report] reuse completed {facility}", flush=True)
                continue
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--cases-dir", str(args.cases_dir),
            "--model", str(args.model),
            "--summary", str(args.summary),
            "--scan-min-flux", str(args.scan_min_flux),
            "--scan-max-flux", str(args.scan_max_flux),
            "--scan-flux-points", str(args.scan_flux_points),
            "--threshold-azimuth-step", str(args.threshold_azimuth_step),
            "--threshold-elevation-step", str(args.threshold_elevation_step),
            "--cache-dir", str(args.cache_dir),
            "--worker-facility", facility,
        ]
        child_env = os.environ.copy()
        child_env.update(
            {
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            }
        )
        for attempt in range(1, 4):
            print(f"[threshold_report] isolated scan {facility} (attempt {attempt}/3)", flush=True)
            result = subprocess.run(cmd, env=child_env)
            if result.returncode == 0:
                break
            if attempt == 3:
                raise RuntimeError(
                    f"Threshold worker for {facility} failed three times; last exit={result.returncode}."
                )

    rows: list[dict] = []
    figure_paths: list[str] = []
    for facility in facilities:
        payload = json.loads((args.cache_dir / f"{facility}.json").read_text(encoding="utf-8"))
        rows.extend(payload["rows"])
        figure_paths.extend(payload["figure_paths"])

    table_path = train.OUTPUT_DIR / "experimental_threshold_scan.csv"
    import pandas as pd

    pd.DataFrame(rows).to_csv(table_path, index=False)
    status_counts = pd.Series([row["censoring_status"] for row in rows]).value_counts().to_dict()
    total_facilities = int(df["facility_name"].nunique())
    expected_figures = len(plotted_facilities)
    summary["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    summary["observed_resistant_facilities"] = train._observed_resistance_rows(df)
    summary["run_status"] = {"active_fds_cases": train._active_fds_cases()}
    summary["threshold_scan"] = {
        "table_path": str(table_path),
        "scan_min_flux": float(args.scan_min_flux),
        "scan_max_flux": float(args.scan_max_flux),
        "scan_flux_points": int(args.scan_flux_points),
        "azimuth_step": float(args.threshold_azimuth_step),
        "elevation_step": float(args.threshold_elevation_step),
        "summary_rows": rows,
        "figure_paths": figure_paths,
        "facility_count": len(figure_paths),
        "expected_facility_count": expected_figures,
        "total_facility_count": total_facilities,
        "plot_omitted_no_observed_damage": omitted_facilities,
        "is_complete": (
            len(figure_paths) == expected_figures
            and len({str(row["facility_name"]) for row in rows}) == total_facilities
        ),
        "censoring_counts": status_counts,
        "facilities_with_fully_censored_cells": sorted(
            {row["facility_name"] for row in rows if row["censoring_status"] == "all_right_censored"}
        ),
    }
    with args.summary.open("w", encoding="utf-8") as stream:
        json.dump(train._json_safe(summary), stream, ensure_ascii=False, indent=2)

    model_params_path = Path(summary["model_parameters_path"])
    report_path = train.OUTPUT_DIR / "experimental_model_report.md"
    train._write_report(
        report_path,
        summary,
        model_params_path,
        {
            "观测样本热通量-Dk响应": summary["figures"]["heat_flux_response"],
            "五折预测值与观测值": summary["figures"]["cv_predicted_vs_observed"],
            "五折等级混淆矩阵": summary["figures"]["cv_confusion_matrix"],
            "模型结构示意图": summary["figures"]["model_schematic"],
            "ExtraTrees双任务架构图": summary["figures"]["extra_trees_architecture"],
            "非设施类型工程因素重要性": summary["figures"]["feature_importance"],
        },
    )
    presentation_path = train.OUTPUT_DIR / "experimental_presentation.html"
    train._write_html_deck(presentation_path, summary)
    print(
        f"[threshold_report] {len(figure_paths)}/{expected_figures} required facility maps "
        f"({len(omitted_facilities)} all-no-damage facilities omitted)"
    )
    print(f"[threshold_report] table: {table_path}")
    print(f"[threshold_report] report: {report_path}")
    print(f"[threshold_report] html: {presentation_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
