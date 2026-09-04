#!/usr/bin/env python3
"""Hyperparameter sweep for the per-facility GradeConstrainedRegressor.

Reuses the production data pipeline (filters, feature selection, split) and
evaluation protocol (stratified holdout + 5-fold CV) from train_split_models,
replacing only the model templates.

Run from the repository root:

  .venv/bin/python agent_damage/scripts/hp_sweep.py \
      --configs baseline,trees200 --facilities ligen,boeing
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.scripts.detect_target_type import classify_facilities  # noqa: E402
from agent_damage.scripts.train_split_models import (  # noqa: E402
    _q_monotonic_keep,
    _train_multi,
    _train_single,
    load_subtarget_targets,
)
from agent_damage.src.data.experimental import (  # noqa: E402
    DK_THRESHOLDS,
    load_experimental_dataset,
    select_per_model_feature_columns,
)

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "cases"
FACILITIES_DIR = ROOT.parent / "facilities"
OUTPUT_DIR = ROOT / "output"

BASE_HP: Dict[str, Any] = {
    "n_estimators": 500, "max_features": 1.0, "min_samples_leaf": 1,
    "random_state": 42, "n_jobs": -1,
}

SWEEP_CONFIGS: List[Dict[str, Any]] = [
    {"label": "baseline"},
    {"label": "trees200", "n_estimators": 200},
    {"label": "trees100", "n_estimators": 100},
    {"label": "trees75", "n_estimators": 75},
    {"label": "trees50", "n_estimators": 50},
    {"label": "trees300", "n_estimators": 300},
    {"label": "trees400", "n_estimators": 400},
    {"label": "mf033", "max_features": 0.33},
    {"label": "mf05", "max_features": 0.5},
    {"label": "mf05_t200", "max_features": 0.5, "n_estimators": 200},
    {"label": "msl2", "min_samples_leaf": 2},
    {"label": "msl5", "min_samples_leaf": 5},
    {"label": "combo", "max_features": 0.5, "min_samples_leaf": 2, "n_estimators": 300},
    {"label": "boot_mf05", "bootstrap": True, "max_features": 0.5},
    {"label": "clf_nobalance", "classifier_class_weight": None},
    {"label": "clf_gini", "classifier_criterion": "gini"},
    {"label": "rf", "kind": "random_forest", "max_features": 0.5, "min_samples_leaf": 2},
]

FAILING_11 = [
    "Boeing_Satellite01", "aerospace_medium", "airport_hangar_large", "boeing",
    "lcc", "ligen", "machinery_manufacturing_medium",
    "machinery_manufacturing_small", "materion_newton", "ocb", "sspf",
]
HEALTHY_CONTROLS = ["Hangar", "alcoa", "tesla", "vab"]
DEFAULT_FACILITIES = sorted(set(FAILING_11) | set(HEALTHY_CONTROLS))


def make_estimator(kind: str, role: str, seed: int, hp: Dict[str, Any]):
    params: Dict[str, Any] = dict(BASE_HP)
    for key in ("n_estimators", "max_features", "min_samples_leaf", "bootstrap"):
        if key in hp:
            params[key] = hp[key]
    params["random_state"] = seed
    if role == "reg":
        forest = RandomForestRegressor if kind == "random_forest" else ExtraTreesRegressor
        return forest(**params)
    if hp.get("classifier_criterion") is not None:
        params["criterion"] = hp["classifier_criterion"]
    if hp.get("classifier_class_weight") is not None:
        params["class_weight"] = hp["classifier_class_weight"]
    forest = RandomForestClassifier if kind == "random_forest" else ExtraTreesClassifier
    return forest(**params)


def _templates(seed: int, hp: Dict[str, Any]) -> dict:
    from agent_damage.src.training.regression import (
        GradeConstrainedRegressor,
        MultiTargetGradeConstrainedRegressor,
    )

    kind = hp.get("kind", "extra_trees")
    reg = make_estimator(kind, "reg", seed, hp)
    clf = make_estimator(kind, "clf", seed, hp)
    return {
        "single": GradeConstrainedRegressor(
            regressor=reg, classifier=clf, thresholds=DK_THRESHOLDS,
        ),
        "multi": MultiTargetGradeConstrainedRegressor(
            regressor=reg, classifier=clf, thresholds=DK_THRESHOLDS,
        ),
    }


def _eval_facility_holdout(cfg: Dict[str, Any], family: str, fac_df, matrix_df,
                           names, weights, feature_columns, seed: int,
                           test_size: float) -> dict:
    from agent_damage.scripts.train_split_models import _stratify_or_none
    from agent_damage.src.training.regression import (
        GradeConstrainedRegressor,
        MultiTargetGradeConstrainedRegressor,
        clipped_dk_predictions,
    )
    from sklearn.model_selection import train_test_split

    kind = cfg.get("kind", "extra_trees")
    reg = make_estimator(kind, "reg", seed, cfg)
    clf = make_estimator(kind, "clf", seed, cfg)
    X = fac_df[feature_columns].to_numpy(dtype=float)
    if family == "equivalent" and matrix_df is not None:
        matrix = fac_df[["dk_" + n for n in names]].to_numpy(dtype=float)
        weight_vector = np.asarray([weights.get(n, 1.0) for n in names], dtype=float)
        weight_vector = weight_vector / max(float(np.sum(weight_vector)), 1e-9)
        overall_true = matrix @ weight_vector
        grades = _grade_array_(overall_true)
        stratify = _stratify_or_none(grades)
        X_train, X_test, y_train, y_test = train_test_split(
            X, matrix, test_size=test_size, random_state=seed, stratify=stratify,
        )
        model = MultiTargetGradeConstrainedRegressor(
            regressor=reg, classifier=clf, thresholds=DK_THRESHOLDS,
        ).fit(X_train, y_train)
        y_pred = _clipped_preds(model, X_test)
        overall_true_test = y_test @ weight_vector
        overall_pred_test = y_pred @ weight_vector
        return {
            "holdout_grade_accuracy": float(_accuracy(overall_true_test, overall_pred_test)),
            "cv_grade_accuracy": None,
            "case_count": int(len(fac_df)),
        }
    y = fac_df["Dk"].to_numpy(dtype=float)
    grades = _grade_array_(y)
    stratify = _stratify_or_none(grades)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=stratify,
    )
    model = GradeConstrainedRegressor(
        regressor=reg, classifier=clf, thresholds=DK_THRESHOLDS,
    ).fit(X_train, y_train)
    y_pred = _clipped_preds(model, X_test)
    return {"holdout_grade_accuracy": float(_accuracy(y_test, y_pred)),
            "cv_grade_accuracy": None, "case_count": int(len(fac_df))}


def _accuracy(y_true, y_pred) -> float:
    from agent_damage.scripts.train_split_models import _grade_accuracy
    return _grade_accuracy(y_true, y_pred)


def _clipped_preds(model, X) -> np.ndarray:
    return np.clip(np.asarray(model.predict(X), dtype=float), 0.0, 1.0)


def _grade_array_(values) -> np.ndarray:
    from agent_damage.scripts.train_split_models import _grade_array
    return _grade_array(values)


def _eval_facility(cfg: Dict[str, Any], family: str, fac_df, matrix_df, names,
                   weights, feature_columns, seed: int, test_size: float,
                   holdout_only: bool = False) -> dict:
    if holdout_only:
        return _eval_facility_holdout(
            cfg, family, fac_df, matrix_df, names, weights,
            feature_columns, seed, test_size,
        )
    templates = _templates(seed, cfg)
    if family == "equivalent" and matrix_df is not None:
        matrix = fac_df[["dk_" + n for n in names]].to_numpy(dtype=float)
        return _train_multi(
            fac_df, feature_columns, matrix, names, weights,
            seed, test_size, templates["multi"],
        )
    return _train_single(
        fac_df, feature_columns, fac_df["Dk"].to_numpy(dtype=float),
        seed, test_size, templates["single"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-dir", type=Path, default=CASES_DIR)
    parser.add_argument("--facilities-dir", type=Path, default=FACILITIES_DIR)
    parser.add_argument("--configs", type=str, default="all")
    parser.add_argument("--facilities", type=str, default="default")
    parser.add_argument("--min-simulation-time", type=float, default=0.0)
    parser.add_argument("--facility-sim-floor", type=json.loads,
                        default={"sspf": 180.0, "tesla": 60.0, "SLC": 135.0})
    parser.add_argument("--facility-drop-q-conflict", type=json.loads,
                        default=["boeing", "lcc", "factory", "maf", "SLC"])
    parser.add_argument("--q-clean", type=str, default="conflict",
                        choices=["none", "conflict", "global"],
                        help="data-quality cleaning: none=no q-monotonic drop; "
                             "conflict=only facilities in --facility-drop-q-conflict "
                             "(current production behavior); global=apply "
                             "_q_monotonic_keep to every facility")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.20)
    parser.add_argument("--holdout-only", action="store_true",
                        help="skip 5-fold CV: only evaluate the holdout split")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "hp_sweep_results.json")
    args = parser.parse_args()

    selected = (
        [c["label"] for c in SWEEP_CONFIGS]
        if args.configs == "all"
        else [x.strip() for x in args.configs.split(",") if x.strip()]
    )
    cfgs = [c for c in SWEEP_CONFIGS if c["label"] in selected]
    if not cfgs:
        print(f"sweep: no configs matched {selected}")
        return 1

    facilities_filter = None
    if args.facilities == "default":
        facilities_filter = set(DEFAULT_FACILITIES)
    elif args.facilities != "all":
        facilities_filter = set(x.strip() for x in args.facilities.split(",") if x.strip())

    print("loading dataset ...")
    t0 = time.time()
    df = load_experimental_dataset(
        args.cases_dir, min_completion=0.0,
        min_simulation_time_s=args.min_simulation_time,
    )
    print(f"dataset ready ({time.time() - t0:.1f}s, n={len(df)})")

    manifest, _ = classify_facilities(args.cases_dir, args.facilities_dir)
    results: Dict[str, Any] = {"configs": {}}

    for cfg in cfgs:
        label = cfg["label"]
        rows: dict = {}
        t1 = time.time()
        for facility_name in sorted(manifest):
            if facilities_filter is not None and facility_name not in facilities_filter:
                continue
            family = str(manifest[facility_name]["family"])
            if family not in {"specific", "equivalent", "hangar"}:
                continue
            fac_df = df[df["facility_name"].eq(facility_name)].copy()
            floor = args.facility_sim_floor.get(facility_name, float(args.min_simulation_time))
            fac_df = fac_df[(fac_df["simulation_time_s"] >= floor)
                            | (fac_df["Dk"] >= DK_THRESHOLDS[2])]
            if args.q_clean == "global":
                fac_df = fac_df[_q_monotonic_keep(fac_df)]
            elif args.q_clean == "conflict" and facility_name in args.facility_drop_q_conflict:
                fac_df = fac_df[_q_monotonic_keep(fac_df)]
            if len(fac_df) < 30:
                print(f"sweep: skip {facility_name}: only {len(fac_df)} rows")
                continue

            feature_columns = select_per_model_feature_columns(fac_df)
            matrix_df = names = weights = None
            if family == "equivalent":
                matrix_df, names, weights = load_subtarget_targets(facility_name, args.cases_dir)
                if matrix_df.empty:
                    continue
                joined = fac_df.merge(matrix_df, on="case_name", how="inner")
                if len(joined) < 30:
                    continue
                fac_df = joined

            result = _eval_facility(
                cfg, family, fac_df, matrix_df, names, weights,
                feature_columns, args.seed, args.test_size,
                holdout_only=args.holdout_only,
            )
            rows[facility_name] = {
                "holdout": float(result["holdout_grade_accuracy"]),
                "cv": result["cv_grade_accuracy"],
                "n": int(len(fac_df)),
            }
        results["configs"][label] = rows
        n = len(rows)
        ok_h = sum(1 for r in rows.values() if r["holdout"] >= 0.95)
        ok_c = sum(1 for r in rows.values() if r["cv"] is not None and r["cv"] >= 0.95)
        ok_b = sum(1 for r in rows.values()
                   if r["holdout"] >= 0.95 and r["cv"] is not None and r["cv"] >= 0.95)
        print(f"sweep {label:16s} hold>=.95 {ok_h}/{n} cv>=.95 {ok_c}/{n} "
              f"both {ok_b}/{n}  ({time.time()-t1:.1f}s)")

        failed = {f: r for f, r in rows.items() if f in FAILING_11}
        if failed:
            fh = sum(1 for r in failed.values() if r["holdout"] >= 0.95)
            fc = sum(1 for r in failed.values()
                     if r["cv"] is not None and r["cv"] >= 0.95)
            print(f"sweep-fail11 {label:14s} hold>=.95 {fh}/{len(failed)} "
                  f"cv>=.95 {fc}/{len(failed)}")

    results["meta"] = {
        "base_hp": BASE_HP, "seed": args.seed, "test_size": args.test_size,
        "failing_11": FAILING_11, "healthy_controls": HEALTHY_CONTROLS,
    }
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"\nresults written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
