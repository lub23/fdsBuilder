#!/usr/bin/env python3
"""Train per-facility split surrogate models for the three families.

specific   -> one GradeConstrainedRegressor per facility, single Dk target
equivalent -> one MultiTargetGradeConstrainedRegressor per facility; per
              sub-target Dk outputs, overall Dk derived by value-weighted sum
hangar     -> one single-target model per airport hangar scale

Evaluation writes cv + holdout grade accuracy per facility; models are pickled
into checkpoints/split_models/.
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor
from sklearn.model_selection import StratifiedKFold, train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.scripts.detect_target_type import _subtarget_files, classify_facilities  # noqa: E402
from agent_damage.src.data.experimental import (  # noqa: E402
    DK_THRESHOLDS,
    dk_to_grade,
    load_experimental_dataset,
    select_per_model_feature_columns,
)
from agent_damage.src.training.regression import (  # noqa: E402
    GradeConstrainedRegressor,
    MultiTargetGradeConstrainedRegressor,
)

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "cases"
FACILITIES_DIR = ROOT.parent / "facilities"
OUTPUT_DIR = ROOT / "output"
CKPT_DIR = ROOT / "checkpoints" / "split_models"

# Per-facility feature extension groups; a variant appends its non-constant
# extra columns to the baseline set returned by select_per_model_feature_columns.
FEATURE_GROUPS: Dict[str, tuple[str, ...]] = {
    "az_flags": (
        "heat_azimuth_is_0", "heat_azimuth_is_90", "heat_azimuth_is_180",
        "heat_azimuth_is_270",
    ),
    "el_flags": (
        "heat_elevation_is_0", "heat_elevation_is_30", "heat_elevation_is_45",
        "heat_elevation_is_60",
    ),
    "dur_flags": ("duration_is_1360ms", "duration_is_2100ms", "duration_is_7500ms"),
    "opening_vent": (
        "incident_open_vent_count", "incident_open_vent_area",
        "incident_open_vent_ratio", "incident_radiation_vent_count",
        "incident_radiation_vent_area", "incident_radiation_vent_ratio",
        "incident_total_opening_count", "incident_total_opening_area",
        "incident_has_opening", "incident_windowless_wall",
    ),
    "heat_combo": (
        "incident_opening_heat_dose", "incident_radiation_heat_dose",
        "no_opening_heat_flux", "incident_asset_front_ratio",
        "incident_asset_front_count", "heat_dose_kw_s_m2", "heat_flux_squared",
    ),
}


def _feature_columns_for(facility_df: pd.DataFrame, variant: Optional[str]) -> List[str]:
    """Baseline feature columns plus any non-constant extra columns of a variant."""
    columns = list(select_per_model_feature_columns(facility_df))
    if not variant or variant == "baseline":
        return columns
    extras = FEATURE_GROUPS.get(variant, ())
    for column in extras:
        if column in facility_df.columns and column not in columns:
            values = facility_df[column].to_numpy(dtype=float)
            values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
            if len(values) and np.nanstd(values) > 1e-12:
                columns.append(column)
    return columns


def _regressor(seed: int, n_estimators: int = 50) -> ExtraTreesRegressor:
    return ExtraTreesRegressor(
        n_estimators=n_estimators, max_features=1.0, min_samples_leaf=1,
        random_state=seed, n_jobs=-1,
    )


def _classifier(seed: int, n_estimators: int = 50) -> ExtraTreesClassifier:
    return ExtraTreesClassifier(
        n_estimators=n_estimators, max_features=1.0, min_samples_leaf=1,
        criterion="entropy", class_weight="balanced",
        random_state=seed, n_jobs=-1,
    )


def _model_templates(seed: int, n_estimators: int = 50) -> Dict[str, Any]:
    return {
        "multi": MultiTargetGradeConstrainedRegressor(
            regressor=_regressor(seed, n_estimators),
            classifier=_classifier(seed, n_estimators),
            thresholds=DK_THRESHOLDS,
        ),
        "single": GradeConstrainedRegressor(
            regressor=_regressor(seed, n_estimators),
            classifier=_classifier(seed, n_estimators),
            thresholds=DK_THRESHOLDS,
        ),
    }


def load_subtarget_targets(
    facility_name: str, cases_root: Path,
) -> tuple[pd.DataFrame, List[str], pd.Series]:
    facility_root = cases_root / facility_name
    frames: list[pd.DataFrame] = []
    weight_map: dict[str, float] = {}
    for csv_path in sorted(_subtarget_files(facility_root)):
        row = pd.read_csv(csv_path, encoding="utf-8-sig")
        name = str(row["subtarget_en"].iloc[0]) if "subtarget_en" in row.columns else csv_path.stem
        target_col = "dk_" + name
        frames.append(row[["case_name", "Dk"]].rename(columns={"Dk": target_col}))
        if "total_asset_value_CNY" in row.columns and row["total_asset_value_CNY"].notna().any():
            weight_map[name] = float(row["total_asset_value_CNY"].dropna().iloc[0])
        else:
            weight_map[name] = 1.0
    if not frames:
        return pd.DataFrame(), [], {}
    merged = frames[0]
    for frame in frames[1:]:
        keep = ["case_name"] + [c for c in frame.columns if c.startswith("dk_")]
        merged = merged.merge(frame[keep], on="case_name", how="inner")
    target_cols = [c for c in merged.columns if c.startswith("dk_")]
    names = [c.replace("dk_", "", 1) for c in target_cols]
    matrix_df = merged[["case_name"] + target_cols].dropna().reset_index(drop=True)
    weights = {n: weight_map.get(n, 1.0) for n in names}
    return matrix_df, names, weights


def _q_monotonic_keep(facility_df: pd.DataFrame) -> np.ndarray:
    """Keep rows whose Dk is monotonic in q within each (a,e,d,t) group.

    Rows whose Dk falls below the running maximum of smaller-q rows in the
    same group break physical monotonicity and are dropped; ties at the
    running max are kept. Returns a boolean mask aligned to facility_df.
    """
    _case_re = re.compile(
        r"^.+_q(?P<q>-?\d+(?:\.\d+)?)"
        r"_a(?P<a>-?\d+(?:\.\d+)?)"
        r"_e(?P<e>-?\d+(?:\.\d+)?)"
        r"_d(?P<d>-?\d+(?:\.\d+)?)"
        r"_t(?P<t>-?\d+(?:\.\d+)?)$",
        re.I,
    )
    keep = np.zeros(len(facility_df), dtype=bool)
    groups: dict[tuple, list[int]] = defaultdict(list)
    for pos, row in enumerate(facility_df.itertuples(index=False)):
        m = _case_re.match(str(row.case_name))
        if m is None:
            keep[pos] = True
            continue
        groups[(m.group("a"), m.group("e"), m.group("d"), m.group("t"))].append(pos)
    for idxs in groups.values():
        if len(idxs) < 2:
            for i in idxs:
                keep[i] = True
            continue
        items = sorted(
            (float(_case_re.match(facility_df.iloc[i]["case_name"]).group("q")), i)
            for i in idxs
        )
        best = -1.0
        for _, i in items:
            dk = float(facility_df.iloc[i]["Dk"])
            if dk >= best - 1e-9:
                keep[i] = True
            best = max(best, dk)
    return keep


def _grade_array(values: np.ndarray) -> np.ndarray:
    flat = np.asarray(values, dtype=float).ravel()
    return np.array([dk_to_grade(float(v)) for v in flat], dtype=int)


def _grade_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(_grade_array(y_true) == _grade_array(y_pred)))


def _subtarget_accuracy(
    y_true: np.ndarray, y_pred: np.ndarray, names: List[str],
) -> List[Dict[str, float]]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.ndim == 1:
        y_true = y_true.reshape(-1, 1)
    if y_pred.ndim == 1:
        y_pred = y_pred.reshape(-1, 1)
    out: list[dict[str, float]] = []
    for col in range(y_true.shape[1]):
        name = names[col] if col < len(names) else str(col)
        out.append({"subtarget": name, "accuracy": _grade_accuracy(y_true[:, col], y_pred[:, col])})
    return out


def _stratify_or_none(labels: np.ndarray) -> Optional[np.ndarray]:
    _, counts = np.unique(labels, return_counts=True)
    if len(counts) < 2 or counts.min() < 2:
        return None
    return labels


def _clipped_predictions(model: Any, X: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(model.predict(X), dtype=float), 0.0, 1.0)


def _regressor_predictions(model: Any, X: np.ndarray) -> np.ndarray:
    """Raw continuous regressor output, bypassing the classifier interval clip."""
    return np.clip(np.asarray(model.regressor_.predict(X), dtype=float), 0.0, 1.0)


def _head_predictions(model: Any, X: np.ndarray, regressor_only: bool) -> np.ndarray:
    if regressor_only:
        return _regressor_predictions(model, X)
    return _clipped_predictions(model, X)


def _train_single(
    facility_df: pd.DataFrame,
    feature_columns: List[str],
    targets: np.ndarray,
    seed: int,
    test_size: float,
    template: Any,
    regressor_only: bool = False,
) -> Dict[str, Any]:
    X = facility_df[feature_columns].to_numpy(dtype=float)
    grades = _grade_array(targets)
    stratify = _stratify_or_none(grades)
    X_train, X_test, y_train, y_test = train_test_split(
        X, targets, test_size=test_size, random_state=seed, stratify=stratify,
    )
    model = clone(template).fit(X_train, y_train)
    y_pred = _head_predictions(model, X_test, regressor_only)

    kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    cv_pred = np.zeros_like(targets, dtype=float)
    for train_idx, test_idx in kf.split(X, grades):
        fold_model = clone(template).fit(X[train_idx], targets[train_idx])
        cv_pred[test_idx] = _head_predictions(fold_model, X[test_idx], regressor_only)

    return {
        "model": model,
        "holdout_grade_accuracy": _grade_accuracy(y_test, y_pred),
        "cv_grade_accuracy": _grade_accuracy(targets, cv_pred),
        "subtarget_holdout_accuracy": _subtarget_accuracy(y_test, y_pred, ["overall"]),
        "subtarget_cv_accuracy": _subtarget_accuracy(targets, cv_pred, ["overall"]),
    }


def _train_multi(
    facility_df: pd.DataFrame,
    feature_columns: List[str],
    matrix: np.ndarray,
    names: List[str],
    weights: Dict[str, float],
    seed: int,
    test_size: float,
    template: Any,
    regressor_only: bool = False,
) -> Dict[str, Any]:
    X = facility_df[feature_columns].to_numpy(dtype=float)
    weight_vector = np.asarray([weights.get(n, 1.0) for n in names], dtype=float)
    total_weight = float(np.sum(weight_vector))
    weight_vector = weight_vector / max(total_weight, 1e-9)
    overall_true = matrix @ weight_vector
    grades = _grade_array(overall_true)
    stratify = _stratify_or_none(grades)
    X_train, X_test, y_train, y_test = train_test_split(
        X, matrix, test_size=test_size, random_state=seed, stratify=stratify,
    )
    model = clone(template).fit(X_train, y_train)
    y_pred = _head_predictions(model, X_test, regressor_only).reshape(y_test.shape)
    overall_true_test = y_test @ weight_vector
    overall_pred_test = y_pred @ weight_vector

    kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    cv_pred = np.zeros_like(matrix, dtype=float)
    for train_idx, test_idx in kf.split(X, grades):
        fold_model = clone(template).fit(X[train_idx], matrix[train_idx])
        cv_pred[test_idx] = _head_predictions(
            fold_model, X[test_idx], regressor_only
        ).reshape(cv_pred[test_idx].shape)
    overall_cv_pred = cv_pred @ weight_vector

    return {
        "model": model,
        "holdout_grade_accuracy": _grade_accuracy(overall_true_test, overall_pred_test),
        "cv_grade_accuracy": _grade_accuracy(overall_true, overall_cv_pred),
        "subtarget_holdout_accuracy": _subtarget_accuracy(y_test, y_pred, names),
        "subtarget_cv_accuracy": _subtarget_accuracy(matrix, cv_pred, names),
    }


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-dir", type=Path, default=CASES_DIR)
    parser.add_argument("--facilities-dir", type=Path, default=FACILITIES_DIR)
    parser.add_argument("--min-completion", type=float, default=0.0)
    parser.add_argument("--min-simulation-time", type=float, default=0.0,
                        help="extra absolute lower bound on simulation_time_s; "
                             "kept if sim>=max(heat_duration, this) or Dk>=0.40")
    parser.add_argument(
        "--facility-sim-floor", type=json.loads, default=None,
        help='JSON dict {"FacilityName": floor_seconds} overriding the global '
             "simulation_time_s floor per facility",
    )
    parser.add_argument(
        "--facility-drop-q-conflict", type=json.loads, default=None,
        help='JSON list of facility names on which to additionally drop rows '
             "whose Dk breaks q-monotonicity within (a,e,d,t) groups",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-estimators", type=int, default=50,
                        help="trees per head (regressor and classifier)")
    parser.add_argument("--test-size", type=float, default=0.20)
    parser.add_argument(
        "--facility-overrides", type=json.loads, default=None,
        help='JSON dict {"FacilityName": {"variant": str, "seed": int, '
             '"regressor_only": bool}}; overrides feature columns, random seed '
             "and grading head per facility. Unset keys keep production defaults.",
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--ckpt-dir", type=Path, default=CKPT_DIR)
    args = parser.parse_args()

    args.ckpt_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest, _ = classify_facilities(args.cases_dir, args.facilities_dir)
    df = load_experimental_dataset(
        args.cases_dir,
        min_completion=args.min_completion,
        min_simulation_time_s=args.min_simulation_time,
    )

    templates = _model_templates(args.seed, args.n_estimators)
    reports: list[dict[str, Any]] = []

    for facility_name in sorted(manifest):
        family = str(manifest[facility_name]["family"])
        if family not in {"specific", "equivalent", "hangar"}:
            continue
        override = (args.facility_overrides or {}).get(facility_name, {})
        seed = int(override.get("seed", args.seed))
        variant = override.get("variant") or "baseline"
        regressor_only = bool(override.get("regressor_only", False))
        templates = _model_templates(seed, args.n_estimators)
        facility_df = df[df["facility_name"].eq(facility_name)].copy()
        if args.facility_sim_floor:
            floor = args.facility_sim_floor.get(facility_name, float(args.min_simulation_time))
            floor_mask = (facility_df["simulation_time_s"] >= floor) | (
                facility_df["Dk"] >= DK_THRESHOLDS[2]
            )
            facility_df = facility_df[floor_mask]
        if args.facility_drop_q_conflict and facility_name in args.facility_drop_q_conflict:
            facility_df = facility_df[_q_monotonic_keep(facility_df)]
        if len(facility_df) < 30:
            print(f"[split] skip {facility_name}: only {len(facility_df)} rows")
            continue
        feature_columns = _feature_columns_for(facility_df, variant)

        if family == "equivalent":
            matrix_df, names, weights = load_subtarget_targets(facility_name, args.cases_dir)
            if matrix_df.empty:
                print(f"[split] skip {facility_name}: empty sub-target summary")
                continue
            joined = facility_df.merge(matrix_df, on="case_name", how="inner")
            if len(joined) < 30:
                print(f"[split] skip {facility_name}: only {len(joined)} joint rows")
                continue
            matrix = joined[["dk_" + n for n in names]].to_numpy(dtype=float)
            result = _train_multi(
                joined, feature_columns, matrix, names, weights,
                seed, args.test_size, templates["multi"], regressor_only=regressor_only,
            )
            facility_df = joined
        else:
            result = _train_single(
                facility_df, feature_columns, facility_df["Dk"].to_numpy(dtype=float),
                seed, args.test_size, templates["single"], regressor_only=regressor_only,
            )

        model = result.pop("model")
        report = {
            "facility_name": facility_name,
            "family": family,
            "feature_count": int(len(feature_columns)),
            "feature_columns": list(feature_columns),
            "case_count": int(len(facility_df)),
            "holdout_grade_accuracy": float(result["holdout_grade_accuracy"]),
            "cv_grade_accuracy": float(result["cv_grade_accuracy"]),
            "subtarget_holdout_accuracy": result["subtarget_holdout_accuracy"],
            "subtarget_cv_accuracy": result["subtarget_cv_accuracy"],
            "config": {
                "seed": seed,
                "variant": variant,
                "regressor_only": regressor_only,
            },
            "model_path": str(args.ckpt_dir / f"{facility_name}.pkl"),
        }
        with open(args.ckpt_dir / f"{facility_name}.pkl", "wb") as f:
            pickle.dump({"model": model, "report": report}, f)
        reports.append(report)
        print(
            f"[split] {family:9s} {facility_name:32s} "
            f"cv={report['cv_grade_accuracy']:.4f} holdout={report['holdout_grade_accuracy']:.4f} "
            f"features={report['feature_count']}"
        )

    summary_path = args.output_dir / "split_model_evaluation.json"
    summary_path.write_text(
        json.dumps({"models": reports}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n评估结果: {summary_path}")
    print(f"模型保存目录: {args.ckpt_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())