#!/usr/bin/env python3
"""Evaluate the production surrogate by facility family and plot local importance.

The independent-test evaluator is fitted only on the persisted train+validation
splits. Family-specific importance uses grouped permutation on each held-out
family subset, so it describes how the unified model uses factors for that
family without leaking independent-test labels into fitting.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import accuracy_score, mean_absolute_error, mean_squared_error

from agent_damage.scripts.train_experimental import _candidate_models
from agent_damage.src.data.experimental import (
    DK_THRESHOLDS,
    FACILITY_TO_TYPE,
    FACILITY_TYPE_NAMES,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
FIGURE_DIR = OUTPUT_DIR / "experimental_figures"
MODEL_PATH = ROOT / "checkpoints" / "experimental_dk_regressor.pkl"

FAMILY_LABELS = {
    "aerospace": "航空航天设施",
    "airport_hangar": "机场机库设施",
    "machinery_manufacturing": "机械制造设施",
    "metallurgical": "冶金设施",
    "aerospace_and_airport_hangar": "航空航天与机场机库设施",
}

REPORT_COMBINATIONS = {
    "aerospace_and_airport_hangar": ("aerospace", "airport_hangar"),
}

FEATURE_LABELS = {
    "heat_flux_log10": "热通量",
    "duration_s": "辐射持续时间（秒）",
    "heat_dose_log10": "热剂量",
    "elevation_sin": "俯仰角正弦项",
    "azimuth_sin": "方位角正弦项",
    "azimuth_cos": "方位角余弦项",
    "heat_elevation_deg": "俯仰角",
    "radiation_duration_ms": "辐射持续时间（离散工况）",
    "log_floor_area": "建筑平面面积",
    "log_volume": "建筑体积",
    "height": "建筑高度",
    "incident_wall_area_log": "迎火侧墙面面积",
    "incident_door_window_count": "迎火侧门窗数量",
    "incident_door_window_ratio": "迎火侧门窗面积比",
    "incident_total_opening_ratio": "迎火侧总开口比例",
    "combustible_target_density": "可燃物/敏感目标密度",
    "incident_combustible_target_ratio": "迎火侧可燃物/敏感目标比例",
}

GROUP_LABELS = {
    "heat_source": "热源特征",
    "building": "建筑特征（含设施类别）",
    "combustible": "可燃物与敏感目标特征",
}


def _feature_groups(feature_columns: list[str]) -> dict[str, list[str]]:
    return {
        "heat_source": [
            "heat_flux_log10",
            "duration_s",
            "heat_dose_log10",
            "elevation_sin",
            "azimuth_sin",
            "azimuth_cos",
            "heat_elevation_deg",
            "radiation_duration_ms",
        ],
        "building": [
            "log_floor_area",
            "log_volume",
            "height",
            "incident_wall_area_log",
            "incident_door_window_count",
            "incident_door_window_ratio",
            "incident_total_opening_ratio",
            "facility_type_index",
            "facility_type_oh_aerospace",
            "facility_type_oh_airport_hangar",
            "facility_type_oh_machinery_manufacturing",
            "facility_type_oh_metallurgical",
            *[name for name in feature_columns if name.startswith("facility_oh_")],
        ],
        "combustible": [
            "combustible_target_density",
            "incident_combustible_target_ratio",
        ],
    }


def _fit_independent_test_model(feature_columns: list[str]) -> Any:
    train = pd.read_csv(DATA_DIR / "experimental_train.csv")
    val = pd.read_csv(DATA_DIR / "experimental_val.csv")
    train_val = pd.concat([train, val], ignore_index=True)
    model = clone(_candidate_models(42)["grade_constrained_extra_trees"])
    model.fit(
        train_val[feature_columns].to_numpy(dtype=float),
        train_val["Dk"].to_numpy(dtype=float),
    )
    return model


def _scores(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    true_grade = np.digitize(y_true, DK_THRESHOLDS)
    predicted_grade = np.digitize(y_pred, DK_THRESHOLDS)
    return {
        "accuracy": float(accuracy_score(true_grade, predicted_grade)),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(mean_squared_error(y_true, y_pred) ** 0.5),
    }


def _permutation_rows(
    model: Any,
    X: np.ndarray,
    y: np.ndarray,
    feature_columns: list[str],
    groups: dict[str, list[str]],
    *,
    group_repeats: int,
    feature_repeats: int,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    column_index = {name: index for index, name in enumerate(feature_columns)}
    baseline_prediction = model.predict(X)
    baseline = _scores(y, baseline_prediction)
    rng = np.random.default_rng(seed)

    def evaluate(columns: list[str], repeats: int) -> dict[str, float]:
        indices = [column_index[name] for name in columns]
        accuracy_decreases: list[float] = []
        mae_increases: list[float] = []
        for _ in range(repeats):
            permutation = rng.permutation(len(y))
            permuted = X.copy()
            permuted[:, indices] = X[permutation][:, indices]
            scores = _scores(y, model.predict(permuted))
            accuracy_decreases.append(baseline["accuracy"] - scores["accuracy"])
            mae_increases.append(scores["mae"] - baseline["mae"])
        return {
            "accuracy_decrease_mean": float(np.mean(accuracy_decreases)),
            "accuracy_decrease_std": float(np.std(accuracy_decreases)),
            "mae_increase_mean": float(np.mean(mae_increases)),
            "mae_increase_std": float(np.std(mae_increases)),
        }

    group_rows = [
        {
            "factor": name,
            "factor_zh": GROUP_LABELS[name],
            "feature_count": len(columns),
            **evaluate(columns, group_repeats),
        }
        for name, columns in groups.items()
    ]

    engineering_features = [
        name
        for name in groups["heat_source"] + groups["building"] + groups["combustible"]
        if name in FEATURE_LABELS
    ]
    feature_rows = [
        {
            "factor": name,
            "factor_zh": FEATURE_LABELS[name],
            "feature_count": 1,
            **evaluate([name], feature_repeats),
        }
        for name in engineering_features
    ]
    return group_rows, feature_rows


def _plot_importance(
    family: str,
    group_rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    path: Path,
) -> None:
    plt.rcParams.update({
        "font.sans-serif": ["Noto Sans CJK SC", "Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
    })
    colors = ["#2F6B9A", "#D17A22", "#4E8B57", "#8B5AA5"]
    fig, axes = plt.subplots(1, 2, figsize=(15.2, 7.2), gridspec_kw={"width_ratios": [0.9, 1.35]})

    group_sorted = sorted(group_rows, key=lambda row: row["mae_increase_mean"])
    group_values = [max(0.0, row["mae_increase_mean"]) for row in group_sorted]
    group_errors = [row["mae_increase_std"] for row in group_sorted]
    axes[0].barh(
        [row["factor_zh"] for row in group_sorted],
        group_values,
        xerr=group_errors,
        color=[colors[list(GROUP_LABELS).index(row["factor"])] for row in group_sorted],
        alpha=0.9,
        capsize=3,
    )
    axes[0].set_title("特征组重要性", fontsize=15, weight="bold")
    axes[0].set_xlabel("置换后 MAE 增量（越大表示影响越显著）")
    axes[0].grid(axis="x", alpha=0.25)

    top = sorted(feature_rows, key=lambda row: row["mae_increase_mean"], reverse=True)[:10]
    top = list(reversed(top))
    values = [max(0.0, row["mae_increase_mean"]) for row in top]
    errors = [row["mae_increase_std"] for row in top]
    axes[1].barh(
        [row["factor_zh"] for row in top],
        values,
        xerr=errors,
        color="#2F6B9A",
        alpha=0.9,
        capsize=3,
    )
    axes[1].set_title("主要工程因素", fontsize=15, weight="bold")
    axes[1].set_xlabel("置换后 MAE 增量（越大表示影响越显著）")
    axes[1].grid(axis="x", alpha=0.25)

    fig.suptitle(
        f"{FAMILY_LABELS[family]}专项置换重要性",
        fontsize=20,
        weight="bold",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "基于独立测试子集；误差线为重复置换的标准差。相关因素之间可能共享贡献，数值不作加和解释。",
        ha="center",
        fontsize=10.5,
        color="#444444",
    )
    fig.tight_layout(rect=(0.02, 0.05, 0.99, 0.94))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group-repeats", type=int, default=50)
    parser.add_argument("--feature-repeats", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()

    artifact = joblib.load(MODEL_PATH)
    feature_columns = list(artifact["feature_columns"])
    groups = _feature_groups(feature_columns)
    model = _fit_independent_test_model(feature_columns)
    test = pd.read_csv(DATA_DIR / "experimental_test.csv")
    cv = pd.read_csv(OUTPUT_DIR / "experimental_cv_predictions.csv")

    metric_rows: list[dict[str, Any]] = []
    importance_rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for family_number, family in enumerate(FACILITY_TYPE_NAMES):
        test_family = test[test["facility_name"].map(FACILITY_TO_TYPE).eq(family)].copy()
        cv_family = cv[cv["facility_name"].map(FACILITY_TO_TYPE).eq(family)].copy()
        X = test_family[feature_columns].to_numpy(dtype=float)
        y = test_family["Dk"].to_numpy(dtype=float)
        test_scores = _scores(y, model.predict(X))
        cv_scores = _scores(
            cv_family["Dk"].to_numpy(dtype=float),
            cv_family["predicted_Dk"].to_numpy(dtype=float),
        )
        metric_rows.append({
            "facility_type": family,
            "facility_type_zh": FAMILY_LABELS[family],
            "facility_count": int(test_family["facility_name"].nunique()),
            "cv_rows": int(len(cv_family)),
            "cv_accuracy": cv_scores["accuracy"],
            "cv_mae": cv_scores["mae"],
            "cv_rmse": cv_scores["rmse"],
            "test_rows": int(len(test_family)),
            "test_accuracy": test_scores["accuracy"],
            "test_mae": test_scores["mae"],
            "test_rmse": test_scores["rmse"],
        })
        group_rows, feature_rows = _permutation_rows(
            model,
            X,
            y,
            feature_columns,
            groups,
            group_repeats=args.group_repeats,
            feature_repeats=args.feature_repeats,
            seed=args.seed + family_number * 1000,
        )
        for level, rows in (("group", group_rows), ("feature", feature_rows)):
            for row in rows:
                importance_rows.append({
                    "facility_type": family,
                    "facility_type_zh": FAMILY_LABELS[family],
                    "level": level,
                    **row,
                })
        figure_path = FIGURE_DIR / f"facility_type_importance_{family}.png"
        _plot_importance(family, group_rows, feature_rows, figure_path)
        details[family] = {
            "metrics": metric_rows[-1],
            "group_importance": group_rows,
            "feature_importance": feature_rows,
            "figure_path": str(figure_path),
        }

    for combination_number, (family, members) in enumerate(REPORT_COMBINATIONS.items(), start=1):
        test_family = test[test["facility_name"].map(FACILITY_TO_TYPE).isin(members)].copy()
        cv_family = cv[cv["facility_name"].map(FACILITY_TO_TYPE).isin(members)].copy()
        X = test_family[feature_columns].to_numpy(dtype=float)
        y = test_family["Dk"].to_numpy(dtype=float)
        test_scores = _scores(y, model.predict(X))
        cv_scores = _scores(
            cv_family["Dk"].to_numpy(dtype=float),
            cv_family["predicted_Dk"].to_numpy(dtype=float),
        )
        metric_rows.append({
            "facility_type": family,
            "facility_type_zh": FAMILY_LABELS[family],
            "facility_count": int(test_family["facility_name"].nunique()),
            "cv_rows": int(len(cv_family)),
            "cv_accuracy": cv_scores["accuracy"],
            "cv_mae": cv_scores["mae"],
            "cv_rmse": cv_scores["rmse"],
            "test_rows": int(len(test_family)),
            "test_accuracy": test_scores["accuracy"],
            "test_mae": test_scores["mae"],
            "test_rmse": test_scores["rmse"],
        })
        group_rows, feature_rows = _permutation_rows(
            model,
            X,
            y,
            feature_columns,
            groups,
            group_repeats=args.group_repeats,
            feature_repeats=args.feature_repeats,
            seed=args.seed + 10000 * combination_number,
        )
        for level, rows in (("group", group_rows), ("feature", feature_rows)):
            for row in rows:
                importance_rows.append({
                    "facility_type": family,
                    "facility_type_zh": FAMILY_LABELS[family],
                    "level": level,
                    **row,
                })
        figure_path = FIGURE_DIR / f"facility_type_importance_{family}.png"
        _plot_importance(family, group_rows, feature_rows, figure_path)
        details[family] = {
            "metrics": metric_rows[-1],
            "group_importance": group_rows,
            "feature_importance": feature_rows,
            "figure_path": str(figure_path),
            "member_types": list(members),
        }

    metrics = pd.DataFrame(metric_rows)
    importances = pd.DataFrame(importance_rows)
    metrics_path = OUTPUT_DIR / "facility_type_evaluation.csv"
    importance_path = OUTPUT_DIR / "facility_type_feature_importance.csv"
    summary_path = OUTPUT_DIR / "facility_type_evaluation.json"
    metrics.to_csv(metrics_path, index=False)
    importances.to_csv(importance_path, index=False)
    summary = {
        "criterion": "all four facility types must reach >=95% in both CV and independent test",
        "all_types_above_95": bool(
            (
                (metrics.loc[metrics["facility_type"].isin(FACILITY_TYPE_NAMES), "cv_accuracy"] >= 0.95)
                & (metrics.loc[metrics["facility_type"].isin(FACILITY_TYPE_NAMES), "test_accuracy"] >= 0.95)
            ).all()
        ),
        "feature_columns": feature_columns,
        "details": details,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(metrics.to_string(index=False))
    print(f"all_types_above_95={summary['all_types_above_95']}")
    print(f"metrics={metrics_path}")
    print(f"importance={importance_path}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
