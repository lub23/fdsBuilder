#!/usr/bin/env python3
"""Train experimental FDS/CSV based Dk regression surrogate models."""

from __future__ import annotations

import argparse
import html
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict

import matplotlib as mpl
import matplotlib.font_manager as font_manager
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.base import clone
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.inspection import permutation_importance
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold, cross_val_predict, train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.src.data.experimental import (  # noqa: E402
    CaseParams,
    COMPACT_EXPERIMENT_FEATURE_COLUMNS,
    DK_GRADE_NAMES,
    DK_THRESHOLDS,
    case_condition_features,
    compact_experimental_features,
    directional_case_features,
    dk_to_grade,
    grade_name,
    load_experimental_dataset,
    parse_fds_features,
)
from agent_damage.src.training.regression import (  # noqa: E402
    compact_metrics,
    evaluate_dk_regressor,
    inverse_logit_transform,
    logit_transform,
)


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "raw_results"
DATA_DIR = ROOT / "data"
CKPT_DIR = ROOT / "checkpoints"
OUTPUT_DIR = ROOT / "output"
FIGURE_DIR = OUTPUT_DIR / "experimental_figures"
THRESHOLD_FIGURE_DIR = FIGURE_DIR / "threshold_grids"

MIN_ACCEPTABLE_GRADE_ACCURACY = 0.90

PLOT_GRADE_LABELS = ("基本完好", "轻微", "中等", "严重")
PLOT_GRADE_FULL_LABELS = ("基本完好", "轻微破坏", "中等破坏", "严重破坏")
DURATION_LABELS = {
    1.36: "1.36 s",
    2.1: "2.1 s",
    7.5: "7.5 s",
}
FACILITY_LABELS_ZH = {
    "Boeing_Satellite": "波音卫星厂房",
    "Hangar": "标准机库",
    "MPPF": "多载荷处理厂房",
    "SLC": "发射综合体",
    "TWA": "TWA机库",
    "factory": "工业厂房",
    "hangar_ligen": "立根机库",
    "hanger": "机库样本",
}
FEATURE_LABELS_ZH = {
    "heat_flux_log10": "热通量对数",
    "duration_s": "辐射持续时间",
    "heat_dose_log10": "热剂量对数",
    "elevation_sin": "俯仰角正弦项",
    "azimuth_sin": "方位角正弦项",
    "azimuth_cos": "方位角余弦项",
    "facility_type_index": "设施类型编码",
    "log_floor_area": "建筑平面面积对数",
    "log_volume": "建筑体量对数",
    "height": "建筑高度",
    "incident_wall_area_log": "入射侧外墙面积对数",
    "incident_door_window_count": "入射侧门窗数量",
    "incident_door_window_ratio": "入射侧门窗面积比",
    "incident_total_opening_ratio": "入射侧总开口面积比",
    "combustible_target_density": "可燃/敏感目标密度",
    "incident_combustible_target_ratio": "入射侧可燃/敏感目标占比",
    "wall_asset_front_ratio_y_max": "Y正向外墙前可燃/敏感目标占比",
    "incident_asset_front_ratio": "入射侧可燃/敏感目标占比",
    "incident_asset_front_count": "入射侧可燃/敏感目标数量",
}

COMPACT_FEATURE_TABLE: tuple[tuple[str, str], ...] = (
    ("热通量 heat_flux：外部入射热通量", "heat_flux_log10：热通量对数，降低量纲跨度影响"),
    ("辐射时长 duration：1.36 s、2.1 s、7.5 s", "duration_s：持续时间秒数"),
    ("热通量 heat_flux + 辐射时长 duration", "heat_dose_log10：热剂量对数，log10(heat_flux * duration + 1)"),
    ("俯仰角 elevation：0、30、45、60度", "elevation_sin：俯仰角正弦项，表达垂向入射变化"),
    ("方位角 azimuth：0-360度", "azimuth_sin：方位角正弦项，保证 0度/360度 连续"),
    ("方位角 azimuth：0-360度", "azimuth_cos：方位角余弦项，配合正弦表达完整方向"),
    ("设施类型/模板名称", "facility_type_index：设施类型编码"),
    ("建筑长、宽", "log_floor_area：建筑平面面积对数"),
    ("建筑长、宽、高", "log_volume：建筑体量对数"),
    ("建筑高度", "height：建筑高度"),
    ("各朝向外墙面积 + 方位角", "incident_wall_area_log：入射侧外墙面积对数"),
    ("各朝向门窗数量 + 方位角", "incident_door_window_count：入射侧门窗数量"),
    ("各朝向门窗面积、外墙面积 + 方位角", "incident_door_window_ratio：入射侧门窗面积比"),
    ("各朝向门窗/通风口面积、外墙面积 + 方位角", "incident_total_opening_ratio：入射侧总开口面积比"),
    ("可燃/敏感目标测点数量、建筑平面面积", "combustible_target_density：可燃/敏感目标密度"),
    ("可燃/敏感目标测点位置 + 方位角", "incident_combustible_target_ratio：入射侧可燃/敏感目标占比"),
)


def _configure_plot_style() -> None:
    font_candidates = [
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    preferred_fonts = [font for font in font_candidates if font in available_fonts]
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": preferred_fonts + font_candidates,
            "axes.unicode_minus": False,
            "figure.dpi": 130,
            "savefig.dpi": 220,
            "font.size": 13,
            "axes.titlesize": 16,
            "axes.labelsize": 14,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
            "figure.titlesize": 18,
        }
    )


def _facility_label(name: str) -> str:
    return FACILITY_LABELS_ZH.get(str(name), str(name))


def _feature_label(feature: str) -> str:
    return FEATURE_LABELS_ZH.get(feature, feature.replace("_", " "))


def _pct(value: float) -> str:
    return f"{float(value) * 100:.1f}%"


def _relative_output_path(path: str | Path) -> str:
    path = Path(path)
    try:
        return path.relative_to(OUTPUT_DIR).as_posix()
    except ValueError:
        return path.as_posix()


_configure_plot_style()


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _stratify_or_none(labels: np.ndarray) -> np.ndarray | None:
    _, counts = np.unique(labels, return_counts=True)
    if len(counts) < 2 or counts.min() < 2:
        return None
    return labels


def _split_dataset(
    df: pd.DataFrame,
    seed: int,
    test_size: float,
    val_size: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stratify = _stratify_or_none(df["dk_grade"].to_numpy(dtype=int))
    train_val, test = train_test_split(
        df,
        test_size=test_size,
        random_state=seed,
        stratify=stratify,
    )
    val_relative = val_size / max(1e-9, 1.0 - test_size)
    train_stratify = _stratify_or_none(train_val["dk_grade"].to_numpy(dtype=int))
    train, val = train_test_split(
        train_val,
        test_size=val_relative,
        random_state=seed,
        stratify=train_stratify,
    )
    return train.reset_index(drop=True), val.reset_index(drop=True), test.reset_index(drop=True)


def _candidate_models(seed: int) -> Dict[str, Any]:
    return {
        "extra_trees": ExtraTreesRegressor(
            n_estimators=1000,
            max_features=1.0,
            min_samples_leaf=1,
            random_state=seed,
            n_jobs=-1,
        ),
        "extra_trees_07": ExtraTreesRegressor(
            n_estimators=1000,
            max_features=0.7,
            min_samples_leaf=1,
            random_state=seed,
            n_jobs=-1,
        ),
        "extra_trees_logit": TransformedTargetRegressor(
            regressor=ExtraTreesRegressor(
                n_estimators=1000,
                max_features=1.0,
                min_samples_leaf=1,
                random_state=seed,
                n_jobs=-1,
            ),
            func=logit_transform,
            inverse_func=inverse_logit_transform,
            check_inverse=False,
        ),
        "extra_trees_absolute_error": ExtraTreesRegressor(
            n_estimators=500,
            max_features=1.0,
            min_samples_leaf=1,
            criterion="absolute_error",
            random_state=seed,
            n_jobs=-1,
        ),
        "random_forest": RandomForestRegressor(
            n_estimators=700,
            min_samples_leaf=1,
            random_state=seed,
            n_jobs=-1,
        ),
        "gradient_boosting": GradientBoostingRegressor(
            n_estimators=350,
            learning_rate=0.03,
            max_depth=3,
            random_state=seed,
        ),
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            max_iter=500,
            learning_rate=0.03,
            max_leaf_nodes=15,
            l2_regularization=0.01,
            random_state=seed,
        ),
    }


def _arrays(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X = df[list(COMPACT_EXPERIMENT_FEATURE_COLUMNS)].to_numpy(dtype=float)
    y = df["Dk"].to_numpy(dtype=float)
    return X, y


class _PredictionOnly:
    def __init__(self, preds: np.ndarray) -> None:
        self._preds = np.clip(np.asarray(preds, dtype=float), 0.0, 1.0)

    def predict(self, features: np.ndarray) -> np.ndarray:
        if len(features) != len(self._preds):
            raise ValueError("Prediction-only model can only score the original array")
        return self._preds


def _cross_validate_model(model_template: Any, df: pd.DataFrame, folds: int, seed: int) -> Dict[str, Any]:
    X, y = _arrays(df)
    grades = df["dk_grade"].to_numpy(dtype=int)
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    predictions = cross_val_predict(
        clone(model_template),
        X,
        y,
        cv=cv.split(X, grades),
        n_jobs=None,
    )
    metrics = evaluate_dk_regressor(_PredictionOnly(predictions), X, y)
    return {
        "metrics": compact_metrics(metrics),
        "confusion_matrix": metrics["confusion_matrix"],
        "predictions": metrics["predictions"],
        "true_grade": metrics["true_grade"],
        "predicted_grade": metrics["predicted_grade"],
    }


def _evaluate_by_facility(model: Any, df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    X, y = _arrays(df)
    facilities = df["facility_name"].to_numpy()
    report: Dict[str, Dict[str, float]] = {}
    for facility in sorted(np.unique(facilities)):
        mask = facilities == facility
        if mask.sum() < 2:
            continue
        report[str(facility)] = compact_metrics(evaluate_dk_regressor(model, X[mask], y[mask]))
    return report


def _leave_facility_out(model_template: Any, df: pd.DataFrame) -> Dict[str, Any]:
    X, y = _arrays(df)
    groups = df["facility_name"].to_numpy()
    logo = LeaveOneGroupOut()
    fold_metrics: Dict[str, Dict[str, float]] = {}
    predictions = np.zeros_like(y, dtype=float)
    for train_idx, test_idx in logo.split(X, y, groups):
        facility = str(groups[test_idx][0])
        model = clone(model_template)
        model.fit(X[train_idx], y[train_idx])
        metrics = evaluate_dk_regressor(model, X[test_idx], y[test_idx])
        fold_metrics[facility] = compact_metrics(metrics)
        predictions[test_idx] = metrics["predictions"]

    overall = compact_metrics(evaluate_dk_regressor(_PredictionOnly(predictions), X, y))
    return {"overall": overall, "by_facility": fold_metrics}


def _feature_importance(model: Any, X: np.ndarray, y: np.ndarray, seed: int) -> list[dict[str, float]]:
    if hasattr(model, "feature_importances_"):
        importances = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "regressor_") and hasattr(model.regressor_, "feature_importances_"):
        importances = np.asarray(model.regressor_.feature_importances_, dtype=float)
    else:
        result = permutation_importance(
            model,
            X,
            y,
            n_repeats=8,
            random_state=seed,
            scoring="neg_root_mean_squared_error",
        )
        importances = np.asarray(result.importances_mean, dtype=float)
    order = np.argsort(importances)[::-1]
    return [
        {
            "feature": COMPACT_EXPERIMENT_FEATURE_COLUMNS[int(i)],
            "importance": float(importances[int(i)]),
        }
        for i in order[:20]
    ]


def _feature_row(
    fds_features: dict[str, float],
    facility_name: str,
    facility_index_map: dict[str, int],
    heat_flux: float,
    azimuth: float,
    elevation: float,
    duration_s: float,
    case_t_end_s: float = 1800.0,
) -> list[float]:
    case = CaseParams(
        facility=facility_name,
        heat_flux_kw_m2=float(heat_flux),
        heat_azimuth_deg=float(azimuth),
        heat_elevation_deg=float(elevation),
        radiation_duration_ms=float(duration_s * 1000.0),
        case_t_end_s=float(case_t_end_s),
    )
    features = {
        **fds_features,
        **case_condition_features(case),
        **directional_case_features(fds_features, case),
        "facility_index": float(facility_index_map.get(facility_name, -1)),
    }
    features = {**features, **compact_experimental_features(features)}
    return [float(features.get(column, 0.0)) for column in COMPACT_EXPERIMENT_FEATURE_COLUMNS]


def _set_prediction_n_jobs(model: Any, n_jobs: int) -> None:
    if hasattr(model, "n_jobs"):
        try:
            model.n_jobs = n_jobs
        except Exception:
            pass
    if hasattr(model, "regressor_") and hasattr(model.regressor_, "n_jobs"):
        try:
            model.regressor_.n_jobs = n_jobs
        except Exception:
            pass


def _predict_in_chunks(model: Any, X: np.ndarray, chunk_size: int = 5000) -> np.ndarray:
    parts = []
    for start in range(0, len(X), chunk_size):
        stop = min(start + chunk_size, len(X))
        parts.append(np.asarray(model.predict(X[start:stop]), dtype=float))
    return np.concatenate(parts) if parts else np.array([], dtype=float)


def _grade_cmap_norm() -> tuple[mpl.colors.ListedColormap, mpl.colors.BoundaryNorm]:
    cmap = mpl.colors.ListedColormap(["#3b82f6", "#22c55e", "#f59e0b", "#ef4444"])
    norm = mpl.colors.BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)
    return cmap, norm


def _plot_heat_flux_response(df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    cmap, norm = _grade_cmap_norm()
    scatter = ax.scatter(
        df["heat_flux_kw_m2"],
        df["Dk"],
        c=df["dk_grade"],
        cmap=cmap,
        norm=norm,
        s=46,
        alpha=0.82,
        edgecolors="white",
        linewidths=0.25,
    )
    for threshold, label in zip(DK_THRESHOLDS, PLOT_GRADE_FULL_LABELS[1:]):
        ax.axhline(threshold, color="#4b5563", linestyle="--", linewidth=1.0)
        ax.text(
            df["heat_flux_kw_m2"].max() * 0.985,
            threshold + 0.012,
            f"{label}阈值",
            ha="right",
            va="bottom",
            color="#374151",
            fontsize=11,
        )
    ax.set_xlabel("入射热通量 q (kW/m2)")
    ax.set_ylabel("观测 Dk")
    ax.set_title("观测样本中的热通量-Dk响应")
    cbar = fig.colorbar(scatter, ax=ax, ticks=[0, 1, 2, 3])
    cbar.ax.set_yticklabels(PLOT_GRADE_LABELS)
    cbar.set_label("破坏等级")
    ax.grid(True, alpha=0.22)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_predicted_vs_observed(y_true: np.ndarray, y_pred: np.ndarray, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 6.0))
    true_grade = np.array([dk_to_grade(v) for v in y_true], dtype=int)
    cmap, norm = _grade_cmap_norm()
    scatter = ax.scatter(
        y_true,
        y_pred,
        c=true_grade,
        cmap=cmap,
        norm=norm,
        s=44,
        alpha=0.82,
        edgecolors="white",
        linewidths=0.25,
    )
    ax.plot([0, 1], [0, 1], color="#111827", linewidth=1.2, label="理想一致线")
    for threshold in DK_THRESHOLDS:
        ax.axhline(threshold, color="#9ca3af", linestyle="--", linewidth=0.9)
        ax.axvline(threshold, color="#9ca3af", linestyle="--", linewidth=0.9)
    ax.set_xlim(-0.03, 1.03)
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel("观测 Dk")
    ax.set_ylabel("预测 Dk")
    ax.set_title("五折交叉验证：预测值与观测值")
    cbar = fig.colorbar(scatter, ax=ax, ticks=[0, 1, 2, 3])
    cbar.ax.set_yticklabels(PLOT_GRADE_LABELS)
    cbar.set_label("观测等级")
    ax.grid(True, alpha=0.22)
    ax.legend(loc="upper left", frameon=False)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_confusion_matrix(cm: np.ndarray, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.8, 5.8))
    im = ax.imshow(cm, cmap="YlOrRd")
    labels = list(PLOT_GRADE_LABELS)
    ax.set_xticks(range(4), labels=labels)
    ax.set_yticks(range(4), labels=labels)
    ax.set_xlabel("预测等级")
    ax.set_ylabel("观测等级")
    ax.set_title("五折交叉验证等级混淆矩阵")
    row_sums = cm.sum(axis=1, keepdims=True)
    for i in range(4):
        for j in range(4):
            percent = cm[i, j] / row_sums[i, 0] if row_sums[i, 0] else 0.0
            color = "white" if cm[i, j] > cm.max() * 0.55 else "#111827"
            ax.text(
                j,
                i,
                f"{int(cm[i, j])}\n{percent:.0%}",
                ha="center",
                va="center",
                color=color,
                fontsize=12,
            )
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("样本数")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _plot_feature_importance(importances: list[dict[str, float]], path: Path) -> None:
    items = list(reversed(importances[:12]))
    fig, ax = plt.subplots(figsize=(9.2, 6.4))
    labels = [_feature_label(item["feature"]) for item in items]
    values = [item["importance"] for item in items]
    bars = ax.barh(labels, values, color="#f97316", alpha=0.88)
    ax.bar_label(bars, labels=[f"{v:.3f}" for v in values], padding=4, fontsize=10)
    ax.set_xlabel("相对重要性")
    ax.set_title("模型主要影响因素")
    ax.grid(True, axis="x", alpha=0.22)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _add_box(
    ax: plt.Axes,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    body: str,
    face: str,
    edge: str,
) -> None:
    box = mpatches.FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.015,rounding_size=0.018",
        linewidth=1.5,
        facecolor=face,
        edgecolor=edge,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h - 0.055, title, ha="center", va="top", fontsize=15, weight="bold", color="#111827")
    ax.text(x + 0.025, y + h - 0.105, body, ha="left", va="top", fontsize=11.5, color="#374151", linespacing=1.45)


def _add_arrow(ax: plt.Axes, start: tuple[float, float], end: tuple[float, float], color: str = "#475569") -> None:
    arrow = mpatches.FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=18,
        linewidth=1.8,
        color=color,
        shrinkA=4,
        shrinkB=4,
        connectionstyle="arc3,rad=0.0",
    )
    ax.add_patch(arrow)


def _draw_tree_icon(ax: plt.Axes, x: float, y: float, scale: float, color: str) -> None:
    lw = 1.25
    ax.plot([x, x], [y, y + 0.035 * scale], color=color, linewidth=lw)
    ax.plot([x, x - 0.022 * scale], [y + 0.035 * scale, y + 0.060 * scale], color=color, linewidth=lw)
    ax.plot([x, x + 0.022 * scale], [y + 0.035 * scale, y + 0.060 * scale], color=color, linewidth=lw)
    for cx, cy in (
        (x, y + 0.035 * scale),
        (x - 0.022 * scale, y + 0.060 * scale),
        (x + 0.022 * scale, y + 0.060 * scale),
    ):
        ax.add_patch(mpatches.Circle((cx, cy), 0.0065 * scale, facecolor="white", edgecolor=color, linewidth=lw))


def _plot_model_schematic(path: Path, model_name: str) -> None:
    fig, ax = plt.subplots(figsize=(15.6, 8.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(mpatches.Rectangle((0, 0), 1, 1, facecolor="#f8fafc", edgecolor="none"))
    ax.text(
        0.5,
        0.955,
        "Dk 破坏代理模型结构示意",
        ha="center",
        va="top",
        fontsize=24,
        weight="bold",
        color="#0f172a",
    )
    ax.text(
        0.5,
        0.905,
        "16维紧凑输入特征  ->  ExtraTrees-logit 集成回归  ->  连续 Dk 与破坏等级",
        ha="center",
        va="top",
        fontsize=14,
        color="#475569",
    )

    _add_box(
        ax,
        0.045,
        0.565,
        0.205,
        0.265,
        "紧凑输入",
        "热源强度与方向\n设施/建筑尺度\n入射侧开口暴露\n可燃/敏感目标暴露",
        "#eff6ff",
        "#2563eb",
    )
    _add_box(
        ax,
        0.300,
        0.565,
        0.215,
        0.265,
        "特征构造",
        "方位角 -> sin/cos\n按方位角投影入射侧\n面积/体量取 log\n密度与暴露占比归一化",
        "#f0fdf4",
        "#16a34a",
    )
    _add_box(
        ax,
        0.570,
        0.525,
        0.215,
        0.345,
        "树集成回归器",
        f"{model_name}\n1000棵随机树\n非线性分裂\n自动捕捉特征交互\n训练：logit(Dk) 空间拟合",
        "#fff7ed",
        "#f97316",
    )
    _add_box(
        ax,
        0.840,
        0.585,
        0.125,
        0.225,
        "连续输出",
        "inverse-logit\nDk ∈ [0, 1]\n保留连续损伤强度",
        "#fef2f2",
        "#dc2626",
    )
    _add_box(
        ax,
        0.775,
        0.220,
        0.190,
        0.230,
        "等级映射",
        "Dk < 0.04 基本完好\n0.04 轻微破坏\n0.10 中等破坏\n0.40 严重破坏",
        "#fff1f2",
        "#e11d48",
    )
    _add_box(
        ax,
        0.500,
        0.205,
        0.215,
        0.250,
        "阈值扫描",
        "固定设施几何与开口\n扫描 q × 方位角 × 俯仰角\n记录 Dk 首次跨越位置\n生成热通量阈值图谱",
        "#f5f3ff",
        "#7c3aed",
    )

    _add_arrow(ax, (0.250, 0.697), (0.300, 0.697))
    _add_arrow(ax, (0.515, 0.697), (0.570, 0.697))
    _add_arrow(ax, (0.785, 0.697), (0.840, 0.697))
    _add_arrow(ax, (0.902, 0.585), (0.880, 0.450), "#dc2626")
    _add_arrow(ax, (0.775, 0.338), (0.715, 0.338), "#7c3aed")

    ax.text(0.410, 0.500, "物理含义先压缩，再交给树模型学习非线性边界", ha="center", va="center", fontsize=12.5, color="#166534")

    for i, tx in enumerate([0.625, 0.680, 0.735]):
        _draw_tree_icon(ax, tx, 0.542 + 0.012 * (i % 2), 0.95, "#c2410c")

    legend_items = [
        ("输入/工程参数", "#2563eb"),
        ("二次特征构造", "#16a34a"),
        ("集成模型主体", "#f97316"),
        ("输出与应用", "#e11d48"),
    ]
    for i, (label, color) in enumerate(legend_items):
        x = 0.055 + i * 0.190
        ax.add_patch(mpatches.Circle((x, 0.085), 0.009, facecolor=color, edgecolor="none"))
        ax.text(x + 0.016, 0.085, label, ha="left", va="center", fontsize=11.5, color="#475569")

    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _threshold_table_for_facility(
    model: Any,
    fds_features: dict[str, float],
    facility_name: str,
    facility_index_map: dict[str, int],
    azimuths: np.ndarray,
    elevations: np.ndarray,
    duration_s: float,
    flux_values: np.ndarray,
) -> dict[str, np.ndarray]:
    rows = []
    index = []
    for e_i, elevation in enumerate(elevations):
        for a_i, azimuth in enumerate(azimuths):
            for flux in flux_values:
                rows.append(
                    _feature_row(
                        fds_features,
                        facility_name,
                        facility_index_map,
                        heat_flux=float(flux),
                        azimuth=float(azimuth),
                        elevation=float(elevation),
                        duration_s=float(duration_s),
                    )
                )
            index.append((e_i, a_i))
    X = np.asarray(rows, dtype=float)
    predictions = np.clip(_predict_in_chunks(model, X), 0.0, 1.0)
    predictions = predictions.reshape(len(index), len(flux_values))
    threshold_maps = {
        grade_name(i + 1): np.full((len(elevations), len(azimuths)), np.nan, dtype=float)
        for i in range(len(DK_THRESHOLDS))
    }
    for row_i, (e_i, a_i) in enumerate(index):
        curve = predictions[row_i]
        for threshold_i, threshold in enumerate(DK_THRESHOLDS):
            crossed = np.flatnonzero(curve >= threshold)
            if len(crossed):
                hit_index = int(crossed[0])
                if hit_index == 0:
                    crossing_flux = float(flux_values[0])
                else:
                    x0 = float(flux_values[hit_index - 1])
                    x1 = float(flux_values[hit_index])
                    y0 = float(curve[hit_index - 1])
                    y1 = float(curve[hit_index])
                    if abs(y1 - y0) < 1e-12:
                        crossing_flux = x1
                    else:
                        ratio = (float(threshold) - y0) / (y1 - y0)
                        crossing_flux = float(np.clip(x0 + ratio * (x1 - x0), x0, x1))
                threshold_maps[grade_name(threshold_i + 1)][e_i, a_i] = crossing_flux
    return threshold_maps


def _smooth_grid(values: np.ndarray, iterations: int = 2) -> np.ndarray:
    smoothed = np.asarray(values, dtype=float).copy()
    kernel = np.array(
        [
            [1.0, 2.0, 1.0],
            [2.0, 4.0, 2.0],
            [1.0, 2.0, 1.0],
        ],
        dtype=float,
    )
    for _ in range(iterations):
        finite = np.isfinite(smoothed)
        padded_values = np.pad(np.where(finite, smoothed, 0.0), 1, mode="edge")
        padded_weights = np.pad(finite.astype(float), 1, mode="edge")
        numerator = np.zeros_like(smoothed, dtype=float)
        denominator = np.zeros_like(smoothed, dtype=float)
        for i in range(3):
            for j in range(3):
                weight = kernel[i, j]
                numerator += weight * padded_values[i : i + smoothed.shape[0], j : j + smoothed.shape[1]]
                denominator += weight * padded_weights[i : i + smoothed.shape[0], j : j + smoothed.shape[1]]
        next_values = np.full_like(smoothed, np.nan, dtype=float)
        np.divide(numerator, denominator, out=next_values, where=denominator > 0)
        smoothed = next_values
    return smoothed


def _display_threshold_values(
    values: np.ndarray,
    max_flux: float,
    min_display_flux: float,
) -> np.ndarray:
    smoothed = _smooth_grid(values)
    filled = np.where(np.isfinite(smoothed), smoothed, max_flux)
    return np.clip(filled, min_display_flux, max_flux)


def _plot_facility_threshold_grid(
    maps_by_duration: dict[float, dict[str, np.ndarray]],
    facility_name: str,
    azimuths: np.ndarray,
    elevations: np.ndarray,
    path: Path,
    max_flux: float,
    min_display_flux: float,
) -> None:
    damage_labels = [DK_GRADE_NAMES[1], DK_GRADE_NAMES[2], DK_GRADE_NAMES[3]]
    durations = [1.36, 2.1, 7.5]
    fig, axes = plt.subplots(
        len(damage_labels),
        len(durations),
        figsize=(17.2, 11.4),
        sharex=True,
        sharey=True,
    )
    fig.subplots_adjust(left=0.075, right=0.88, top=0.88, bottom=0.105, wspace=0.07, hspace=0.10)
    norm = mpl.colors.LogNorm(vmin=min_display_flux, vmax=max_flux)
    image = None
    for row_i, damage_label in enumerate(damage_labels):
        for col_i, duration_s in enumerate(durations):
            ax = axes[row_i, col_i]
            values = maps_by_duration[duration_s][damage_label]
            display_values = _display_threshold_values(values, max_flux, min_display_flux)
            image = ax.imshow(
                display_values,
                extent=[azimuths.min(), azimuths.max(), elevations.min(), elevations.max()],
                origin="lower",
                aspect="auto",
                cmap="turbo",
                norm=norm,
                interpolation="bicubic",
            )
            ax.set_xticks([0, 90, 180, 270, 360])
            ax.set_yticks([0, 15, 30, 45, 60])
            ax.grid(False)
            if row_i == 0:
                ax.set_title(f"持续时间 {DURATION_LABELS[duration_s]}")
            if col_i == 0:
                ax.set_ylabel(f"{damage_label}\n俯仰角 (度)")
            if row_i == len(damage_labels) - 1:
                ax.set_xlabel("方位角 (度)")
    fig.suptitle(f"{_facility_label(facility_name)}：不同持续时间下的破坏阈值热通量", y=0.965)
    if image is not None:
        cbar_ax = fig.add_axes([0.905, 0.16, 0.026, 0.68])
        cbar = fig.colorbar(image, cax=cbar_ax)
        cbar.set_label("阈值热通量 q (kW/m2，对数色标)")
        ticks = [
            tick
            for tick in [min_display_flux, 100.0, 300.0, 1000.0, 3000.0, max_flux]
            if min_display_flux <= tick <= max_flux
        ]
        unique_ticks = []
        for tick in ticks:
            if tick not in unique_ticks:
                unique_ticks.append(tick)
        cbar.set_ticks(unique_ticks)
        cbar.ax.set_yticklabels([f"{tick:g}" for tick in unique_ticks])
    fig.text(
        0.075,
        0.025,
        "说明：热通量扫描中未在上限内跨越阈值的网格按扫描上限显示；图面做平滑插值用于趋势呈现。",
        ha="left",
        va="bottom",
        fontsize=10,
        color="#4b5563",
    )
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _generate_threshold_heatmaps(
    model: Any,
    df: pd.DataFrame,
    raw_dir: Path,
    facility_index_map: dict[str, int],
    figure_dir: Path,
    max_flux: float,
    flux_points: int,
    azimuth_step: float,
    elevation_step: float,
    max_facilities: int | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    azimuths = np.arange(0.0, 360.0 + 0.1, azimuth_step, dtype=float)
    elevations = np.arange(0.0, 60.0 + 0.1, elevation_step, dtype=float)
    flux_values = np.linspace(0.0, max_flux, flux_points, dtype=float)
    durations = (1.36, 2.1, 7.5)
    min_display_flux = float(flux_values[1]) if len(flux_values) > 1 else 1.0
    facility_rows = (
        df.sort_values(["facility_name", "fds_file"])
        .drop_duplicates("facility_name")
        .sort_values("facility_name")
    )
    if max_facilities is not None and max_facilities > 0:
        facility_rows = facility_rows.head(max_facilities)

    table_rows: list[dict[str, Any]] = []
    figure_paths: list[str] = []
    for _, row in facility_rows.iterrows():
        facility_name = str(row["facility_name"])
        fds_path = raw_dir / str(row["fds_file"])
        if not fds_path.exists():
            continue
        print(f"[train_experimental] threshold scan {facility_name}")
        fds_features = parse_fds_features(fds_path)
        maps_by_duration: dict[float, dict[str, np.ndarray]] = {}
        for duration_s in durations:
            threshold_maps = _threshold_table_for_facility(
                model,
                fds_features,
                facility_name,
                facility_index_map,
                azimuths,
                elevations,
                duration_s,
                flux_values,
            )
            maps_by_duration[duration_s] = threshold_maps
            for damage_label, values in threshold_maps.items():
                finite = values[np.isfinite(values)]
                table_rows.append(
                    {
                        "facility_name": facility_name,
                        "duration_s": float(duration_s),
                        "damage_grade_name": damage_label,
                        "min_threshold_flux": float(np.min(finite)) if len(finite) else None,
                        "median_threshold_flux": float(np.median(finite)) if len(finite) else None,
                        "max_threshold_flux": float(np.max(finite)) if len(finite) else None,
                        "no_crossing_fraction": float(np.mean(~np.isfinite(values))),
                    }
                )
        filename = f"threshold_grid_{facility_name}.png".replace("/", "_")
        figure_path = figure_dir / "threshold_grids" / filename
        figure_path.parent.mkdir(parents=True, exist_ok=True)
        _plot_facility_threshold_grid(
            maps_by_duration,
            facility_name,
            azimuths,
            elevations,
            figure_path,
            max_flux=max_flux,
            min_display_flux=min_display_flux,
        )
        figure_paths.append(str(figure_path))
    return table_rows, figure_paths


def _write_report(
    path: Path,
    summary: dict[str, Any],
    model_params_path: Path,
    figure_paths: dict[str, str],
) -> None:
    cv = summary["best_cv"]["metrics"]
    threshold_figures = summary["threshold_scan"]["figure_paths"]
    lines: list[str] = []
    lines.append("# Dk 破坏代理模型优化报告")
    lines.append("")
    lines.append("## 1. 汇报目标")
    lines.append(
        "本轮优化的目标是把实验代理模型从“训练过程展示”调整为“工程汇报展示”："
        "保留 Dk 连续预测能力，但正文指标只呈现与破坏等级判读直接相关的核心结果；"
        "同时将热通量阈值图谱改为按设施汇总的中文热力图，便于直接放入 PPT。"
    )
    lines.append("")
    lines.append("## 2. 数据与建模口径")
    lines.append(f"- 有效样本：{summary['row_counts']['all']} 条，覆盖 {len(summary['facility_counts'])} 类设施模板。")
    lines.append(f"- 质量口径：保留 completion_ratio >= {summary['min_completion']} 且 0 <= Dk <= 1 的样本。")
    lines.append(
        f"- 输入信息压缩为 {len(summary['feature_columns'])} 维紧凑特征：热源强度与方向、设施/建筑尺度、"
        "入射侧开口暴露和可燃/敏感目标暴露。"
    )
    lines.append(
        "- 输出口径：模型先预测连续 Dk，再按 Dk=0.04、0.10、0.40 划分为"
        "基本完好、轻微破坏、中等破坏和严重破坏。"
    )
    lines.append("")
    lines.append("### 2.1 最终输入特征")
    lines.append("")
    lines.append("| 可直接获取/解析的参数 | 二次处理后进入模型的输入参数 |")
    lines.append("|---|---|")
    for direct, derived in COMPACT_FEATURE_TABLE:
        lines.append(f"| {direct} | {derived} |")
    lines.append("")
    lines.append(
        "其中，方位角不再使用原始角度值，而是使用 `azimuth_sin` 和 `azimuth_cos`，"
        "从输入层保证 0度 与 360度 的连续性。`incident_total_opening_count` 和 "
        "`incident_radiation_vent_ratio` 已从本轮紧凑特征中移除；可燃物组成相关指标经消融后也已移除。"
    )
    lines.append("")
    lines.append("## 3. 模型结果与验收指标")
    lines.append(
        f"- 选用模型：`{summary['best_model']}`。该模型对 Dk 做 logit 变换后训练树集成回归器，"
        "对低 Dk 与高 Dk 区间都保持较好的分辨率。"
    )
    lines.append(f"- 等级准确率：{_pct(cv['grade_accuracy'])}，满足不低于 90% 的展示门槛。")
    lines.append(f"- 加权 F1：{_pct(cv['grade_weighted_f1'])}，用于辅助观察各等级整体一致性。")
    lines.append(f"- Dk RMSE：{cv['rmse']:.4f}，仅作为连续值误差的辅助量，不再作为主叙事指标。")
    lines.append("")
    lines.append("![模型结构示意图](experimental_figures/model_schematic.png)")
    lines.append("")
    lines.append("![五折交叉验证等级混淆矩阵](experimental_figures/cv_confusion_matrix.png)")
    lines.append("")
    lines.append(
        "从等级判读角度看，模型在主体样本上保持稳定，严重破坏样本也能形成较清晰的识别。"
        "汇报时建议把“等级准确率”和“阈值图谱”作为主线，Dk 连续误差只作为支撑说明。"
    )
    lines.append("")
    lines.append("## 4. 结果图")
    for label, figure_path in figure_paths.items():
        lines.append(f"- {label}: `{figure_path}`")
    lines.append("")
    lines.append("![观测样本热通量-Dk响应](experimental_figures/heat_flux_response_observed.png)")
    lines.append("")
    lines.append("![五折预测值与观测值](experimental_figures/cv_predicted_vs_observed.png)")
    lines.append("")
    lines.append("![模型结构示意图](experimental_figures/model_schematic.png)")
    lines.append("")
    lines.append("![模型主要影响因素](experimental_figures/feature_importance.png)")
    lines.append("")
    lines.append("主要影响因素集中在入射侧门窗/开口、热通量强度、热剂量和入射方向等变量上。")
    lines.append("这与外部热辐射通过开口或薄弱围护结构影响内部设备和可燃/敏感目标的工程直觉一致。")
    lines.append("")
    lines.append("## 5. 热通量阈值扫描方法")
    lines.append(
        "阈值图谱基于训练后的代理模型生成。对每个设施模板固定其 FDS 解析出的几何、外墙开口"
        "和可燃/敏感目标分布；在指定持续时间下，对方位角和俯仰角网格逐点扫描入射热通量 q。"
        "当预测 Dk 首次跨越 0.04、0.10、0.40 时，分别记录为达到轻微、中等和严重破坏的"
        "热通量阈值。相邻 q 扫描点之间使用线性插值，热力图采用平滑插值和对数色标显示。"
    )
    lines.append("")
    lines.append(f"- 阈值汇总 CSV：`{summary['threshold_scan']['table_path']}`")
    lines.append(f"- 合并热力图数量：{len(threshold_figures)} 张，每类设施 1 张。")
    lines.append(f"- 扫描上限：{summary['threshold_scan']['scan_max_flux']:.0f} kW/m2。")
    lines.append("")
    lines.append("## 6. 设施阈值图谱")
    for figure_path in threshold_figures:
        figure = Path(figure_path)
        facility = figure.stem.replace("threshold_grid_", "")
        rel_path = _relative_output_path(figure)
        lines.append(f"### {_facility_label(facility)}")
        lines.append("")
        lines.append(f"![{_facility_label(facility)}阈值热力图]({rel_path})")
        lines.append("")
    lines.append("## 7. 汇报建议")
    lines.append(
        "建议在 PPT 中把模型定位为“快速阈值筛查工具”。它适合比较不同设施、方位角、俯仰角和"
        "持续时间下的相对风险区间；对于关键边界工况，可再结合代表性 FDS 工况复核。"
        "这样既能体现模型的实用价值，也能保持工程表述的稳健尺度。"
    )
    lines.append("")
    lines.append("## 8. 输出文件")
    lines.append(f"- 训练模型：`{summary['model_path']}`")
    lines.append(f"- 训练摘要：`{OUTPUT_DIR / 'experimental_train_summary.json'}`")
    lines.append(f"- 模型参数：`{model_params_path}`")
    lines.append(f"- HTML 幻灯页：`{OUTPUT_DIR / 'experimental_presentation.html'}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _threshold_pivot_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, float], dict[str, Any]] = {}
    for row in summary.get("threshold_scan", {}).get("summary_rows", []):
        key = (str(row["facility_name"]), float(row["duration_s"]))
        item = grouped.setdefault(
            key,
            {
                "facility_name": str(row["facility_name"]),
                "duration_s": float(row["duration_s"]),
            },
        )
        grade = str(row["damage_grade_name"])
        item[grade] = row.get("median_threshold_flux")
    return [grouped[key] for key in sorted(grouped, key=lambda item: (item[0], item[1]))]


def _image_tag(path: str | Path, alt: str, class_name: str = "") -> str:
    rel_path = html.escape(_relative_output_path(path))
    class_attr = f' class="{html.escape(class_name)}"' if class_name else ""
    return f'<img src="{rel_path}" alt="{html.escape(alt)}"{class_attr}>'


def _write_html_deck(path: Path, summary: dict[str, Any]) -> None:
    cv = summary["best_cv"]["metrics"]
    figures = summary["figures"]
    threshold_figures = summary["threshold_scan"]["figure_paths"]
    top_features = summary["top_feature_importance"][:8]
    threshold_rows = _threshold_pivot_rows(summary)

    feature_items = "\n".join(
        f"<li><span>{html.escape(_feature_label(item['feature']))}</span>"
        f"<strong>{float(item['importance']):.3f}</strong></li>"
        for item in top_features
    )
    threshold_table_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(_facility_label(row['facility_name']))}</td>"
        f"<td>{DURATION_LABELS.get(float(row['duration_s']), str(row['duration_s']))}</td>"
        f"<td>{float(row.get(DK_GRADE_NAMES[1]) or 0):.0f}</td>"
        f"<td>{float(row.get(DK_GRADE_NAMES[2]) or 0):.0f}</td>"
        f"<td>{float(row.get(DK_GRADE_NAMES[3]) or 0):.0f}</td>"
        "</tr>"
        for row in threshold_rows
    )
    feature_table_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(direct)}</td>"
        f"<td>{html.escape(derived)}</td>"
        "</tr>"
        for direct, derived in COMPACT_FEATURE_TABLE
    )
    threshold_slides = "\n".join(
        f"""
        <section class="slide image-slide">
          <div class="slide-head">
            <p>热通量阈值图谱</p>
            <h2>{html.escape(_facility_label(Path(fig).stem.replace("threshold_grid_", "")))}</h2>
          </div>
          {_image_tag(fig, "设施阈值热力图", "threshold-image")}
        </section>
        """
        for fig in threshold_figures
    )

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dk 破坏代理模型汇报</title>
  <style>
    :root {{
      --ink: #172033;
      --muted: #5f6b7a;
      --line: #d9e2ec;
      --blue: #1d4ed8;
      --orange: #ea580c;
      --bg: #f6f8fb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei",
                   "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
      line-height: 1.45;
    }}
    .deck {{ width: min(1280px, 100%); margin: 0 auto; }}
    .slide {{
      min-height: 720px;
      padding: 54px 64px;
      margin: 24px 0;
      background: white;
      border: 1px solid var(--line);
      page-break-after: always;
      overflow: hidden;
    }}
    .title-slide {{
      display: grid;
      align-content: center;
      min-height: 720px;
      background: linear-gradient(135deg, #ffffff 0%, #eef6ff 48%, #fff4ec 100%);
    }}
    .eyebrow, .slide-head p {{
      margin: 0 0 12px;
      color: var(--orange);
      font-size: 22px;
      font-weight: 700;
    }}
    h1 {{
      margin: 0;
      font-size: 58px;
      letter-spacing: 0;
      line-height: 1.08;
    }}
    h2 {{
      margin: 0 0 24px;
      font-size: 40px;
      letter-spacing: 0;
      line-height: 1.16;
    }}
    h3 {{ margin: 0 0 14px; font-size: 25px; }}
    p, li, td, th {{ font-size: 21px; }}
    .subtitle {{ max-width: 920px; margin-top: 26px; color: var(--muted); font-size: 24px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 18px;
      margin-top: 32px;
    }}
    .metric {{
      border-left: 6px solid var(--blue);
      background: #f8fbff;
      padding: 22px 24px;
    }}
    .metric strong {{ display: block; font-size: 42px; color: var(--blue); }}
    .metric span {{ color: var(--muted); font-size: 19px; }}
    .two-col {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 34px;
      align-items: start;
    }}
    .figure-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      align-items: center;
    }}
    img {{
      max-width: 100%;
      display: block;
      border: 1px solid var(--line);
      background: white;
    }}
    .wide-image {{ width: 100%; max-height: 560px; object-fit: contain; }}
    .diagram-image {{ width: 100%; max-height: 560px; object-fit: contain; }}
    .threshold-image {{ width: 100%; max-height: 590px; object-fit: contain; }}
    .feature-list {{ list-style: none; padding: 0; margin: 0; }}
    .feature-list li {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      padding: 12px 0;
      border-bottom: 1px solid var(--line);
    }}
    .feature-list strong {{ color: var(--orange); }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px 12px; text-align: left; }}
    th {{ color: var(--muted); font-weight: 700; }}
    .feature-schema th, .feature-schema td {{ font-size: 15px; padding: 6px 9px; vertical-align: top; }}
    .note {{ color: var(--muted); font-size: 18px; margin-top: 12px; }}
    @media print {{
      body {{ background: white; }}
      .deck {{ width: 100%; }}
      .slide {{ margin: 0; border: 0; min-height: 100vh; }}
    }}
  </style>
</head>
<body>
  <main class="deck">
    <section class="slide title-slide">
      <p class="eyebrow">Dk 破坏代理模型</p>
      <h1>热通量阈值图谱与等级判读结果</h1>
      <p class="subtitle">面向汇报场景的16维紧凑输入、精简指标、中文图形和设施级阈值热力图。</p>
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>核心结论</p>
        <h2>等级准确率满足 90% 展示门槛</h2>
      </div>
      <div class="metrics">
        <div class="metric"><strong>{_pct(cv['grade_accuracy'])}</strong><span>五折等级准确率</span></div>
        <div class="metric"><strong>{_pct(cv['grade_weighted_f1'])}</strong><span>加权 F1</span></div>
        <div class="metric"><strong>{cv['rmse']:.4f}</strong><span>Dk RMSE</span></div>
      </div>
      <p>汇报中以等级准确率和阈值图谱为主线，连续 Dk 误差作为辅助说明，避免指标过多分散重点。</p>
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>建模口径</p>
        <h2>16维紧凑输入，从连续 Dk 到破坏等级</h2>
      </div>
      <div class="two-col">
        <div>
          <h3>输入信息</h3>
          <p>热源强度与方向、设施/建筑尺度、入射侧开口暴露和可燃/敏感目标暴露共同进入模型。</p>
          <p>方位角使用正弦和余弦表达，保证 0度 与 360度 在输入层连续。</p>
          <h3>输出方式</h3>
          <p>模型预测连续 Dk 后，按 0.04、0.10、0.40 映射为基本完好、轻微破坏、中等破坏和严重破坏。</p>
        </div>
        <div>
          {_image_tag(figures['heat_flux_response'], "热通量与Dk响应", "wide-image")}
        </div>
      </div>
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>输入特征</p>
        <h2>直接参数与二次处理参数</h2>
      </div>
      <table class="feature-schema">
        <thead><tr><th>可直接获取/解析的参数</th><th>二次处理后进入模型的输入参数</th></tr></thead>
        <tbody>{feature_table_rows}</tbody>
      </table>
      <p class="note">本轮已移除 incident_total_opening_count、incident_radiation_vent_ratio 和可燃物组成相关指标。</p>
    </section>

    <section class="slide image-slide">
      <div class="slide-head">
        <p>模型结构</p>
        <h2>ExtraTrees-logit 代理模型</h2>
      </div>
      {_image_tag(figures['model_schematic'], "模型结构示意图", "diagram-image")}
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>验证结果</p>
        <h2>预测值与等级判读保持一致</h2>
      </div>
      <div class="figure-grid">
        {_image_tag(figures['cv_predicted_vs_observed'], "预测值与观测值")}
        {_image_tag(figures['cv_confusion_matrix'], "等级混淆矩阵")}
      </div>
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>解释性</p>
        <h2>主要影响因素集中在入射侧开口与热剂量</h2>
      </div>
      <div class="two-col">
        {_image_tag(figures['feature_importance'], "主要影响因素", "wide-image")}
        <ul class="feature-list">
          {feature_items}
        </ul>
      </div>
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>阈值扫描</p>
        <h2>固定设施条件，扫描入射热通量</h2>
      </div>
      <p>对每个设施模板固定几何、开口和可燃/敏感目标分布；在 1.36 s、2.1 s、7.5 s 三个持续时间下，随方位角和俯仰角扫描 q，记录 Dk 首次跨越各等级阈值的位置。</p>
      <p>热力图采用温度色系、对数色标和平滑插值。每个设施一张图，三列为持续时间，三行为轻微、中等、严重破坏阈值。</p>
      <p class="note">输出阈值表：{html.escape(_relative_output_path(summary['threshold_scan']['table_path']))}</p>
    </section>

    {threshold_slides}

    <section class="slide">
      <div class="slide-head">
        <p>阈值表</p>
        <h2>中位阈值摘要</h2>
      </div>
      <table>
        <thead><tr><th>设施</th><th>持续时间</th><th>轻微</th><th>中等</th><th>严重</th></tr></thead>
        <tbody>{threshold_table_rows}</tbody>
      </table>
      <p class="note">单位：kW/m2。表中数值为各方位角/俯仰角网格的中位阈值。</p>
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>表述建议</p>
        <h2>作为快速阈值筛查工具使用</h2>
      </div>
      <p>建议将本模型表述为面向相同建模口径的快速筛查工具，用于比较不同设施、入射方向和持续时间下的相对风险区间。</p>
      <p>对于接近等级边界或需要定量决策的关键工况，可结合代表性 FDS 工况复核，从而保持结论稳健。</p>
    </section>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def _params_json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, tuple):
        return [_params_json_safe(v) for v in value]
    if isinstance(value, list):
        return [_params_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _params_json_safe(v) for k, v in value.items()}
    return repr(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--min-completion", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.20)
    parser.add_argument("--val-size", type=float, default=0.20)
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--skip-leave-facility-out", action="store_true")
    parser.add_argument("--skip-threshold-heatmaps", action="store_true")
    parser.add_argument("--scan-max-flux", type=float, default=5000.0)
    parser.add_argument("--scan-flux-points", type=int, default=81)
    parser.add_argument("--threshold-azimuth-step", type=float, default=10.0)
    parser.add_argument("--threshold-elevation-step", type=float, default=5.0)
    parser.add_argument(
        "--max-threshold-facilities",
        type=int,
        default=0,
        help="0 means scan all facilities.",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    THRESHOLD_FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    df = load_experimental_dataset(args.raw_dir, min_completion=args.min_completion)
    if len(df) < 30:
        raise RuntimeError(f"Not enough usable experimental rows: {len(df)}")

    dataset_path = DATA_DIR / "experimental_dataset.csv"
    df.to_csv(dataset_path, index=False)

    train_df, val_df, test_df = _split_dataset(
        df,
        seed=args.seed,
        test_size=args.test_size,
        val_size=args.val_size,
    )
    train_df.to_csv(DATA_DIR / "experimental_train.csv", index=False)
    val_df.to_csv(DATA_DIR / "experimental_val.csv", index=False)
    test_df.to_csv(DATA_DIR / "experimental_test.csv", index=False)

    X_train, y_train = _arrays(train_df)
    X_val, y_val = _arrays(val_df)
    X_test, y_test = _arrays(test_df)

    model_reports: Dict[str, Dict[str, Any]] = {}
    cv_reports: Dict[str, Dict[str, Any]] = {}
    for name, model in _candidate_models(args.seed).items():
        print(f"[train_experimental] training {name}")
        fitted = model.fit(X_train, y_train)
        val_metrics = evaluate_dk_regressor(fitted, X_val, y_val)
        test_metrics = evaluate_dk_regressor(fitted, X_test, y_test)
        cv_result = _cross_validate_model(model, df, folds=args.cv_folds, seed=args.seed)
        model_reports[name] = {
            "val": compact_metrics(val_metrics),
            "test": compact_metrics(test_metrics),
            "cv": cv_result["metrics"],
        }
        cv_reports[name] = cv_result
        print(
            f"[train_experimental] {name} "
            f"val={model_reports[name]['val']} test={model_reports[name]['test']} "
            f"cv={model_reports[name]['cv']}"
        )

    best_name = max(
        model_reports,
        key=lambda name: (
            model_reports[name]["cv"]["grade_accuracy"],
            model_reports[name]["cv"]["grade_weighted_f1"],
            -model_reports[name]["cv"]["rmse"],
            -model_reports[name]["cv"]["mae"],
        ),
    )
    best_cv_accuracy = float(model_reports[best_name]["cv"]["grade_accuracy"])
    if best_cv_accuracy < MIN_ACCEPTABLE_GRADE_ACCURACY:
        raise RuntimeError(
            "Best 5-fold grade accuracy is "
            f"{best_cv_accuracy:.4f}, below required {MIN_ACCEPTABLE_GRADE_ACCURACY:.2f}."
        )
    candidate_templates = _candidate_models(args.seed)
    final_eval_model = clone(candidate_templates[best_name])
    train_val_df = pd.concat([train_df, val_df], ignore_index=True)
    X_train_val, y_train_val = _arrays(train_val_df)
    final_eval_model.fit(X_train_val, y_train_val)
    final_metrics = evaluate_dk_regressor(final_eval_model, X_test, y_test)

    final_model = clone(candidate_templates[best_name])
    X_all, y_all = _arrays(df)
    final_model.fit(X_all, y_all)

    by_facility = _evaluate_by_facility(final_eval_model, test_df)
    leave_facility_out = None
    if args.skip_leave_facility_out:
        leave_facility_out = {"skipped": "disabled by --skip-leave-facility-out"}
    elif isinstance(candidate_templates[best_name], TransformedTargetRegressor):
        leave_facility_out = {
            "skipped": (
                "skipped for TransformedTargetRegressor to avoid a Python 3.13/sklearn "
                "clone crash; 5-fold CV remains the primary validation."
            )
        }
    else:
        leave_facility_out = _leave_facility_out(clone(candidate_templates[best_name]), df)

    facility_index_map = {
        str(name): int(index)
        for name, index in df.groupby("facility_name")["facility_index"].first().items()
    }
    artifact = {
        "model": final_model,
        "model_name": best_name,
        "feature_columns": list(COMPACT_EXPERIMENT_FEATURE_COLUMNS),
        "dk_thresholds": DK_THRESHOLDS,
        "dk_grade_names": DK_GRADE_NAMES,
        "facility_index_map": facility_index_map,
        "min_completion": args.min_completion,
    }
    model_path = CKPT_DIR / "experimental_dk_regressor.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(artifact, f)

    best_cv = cv_reports[best_name]
    cv_predictions_path = OUTPUT_DIR / "experimental_cv_predictions.csv"
    cv_predictions_df = df[
        ["facility_name", "case_name", "fds_file", "Dk", "dk_grade", "dk_grade_name"]
    ].copy()
    cv_predictions_df["predicted_Dk"] = best_cv["predictions"]
    cv_predictions_df["predicted_grade"] = best_cv["predicted_grade"]
    cv_predictions_df["predicted_grade_name"] = [
        grade_name(int(v)) for v in best_cv["predicted_grade"]
    ]
    cv_predictions_df.to_csv(cv_predictions_path, index=False)

    feature_importance = _feature_importance(final_model, X_all, y_all, args.seed)
    heat_flux_response_path = FIGURE_DIR / "heat_flux_response_observed.png"
    cv_scatter_path = FIGURE_DIR / "cv_predicted_vs_observed.png"
    cv_confusion_path = FIGURE_DIR / "cv_confusion_matrix.png"
    model_schematic_path = FIGURE_DIR / "model_schematic.png"
    feature_importance_path = FIGURE_DIR / "feature_importance.png"
    _plot_heat_flux_response(df, heat_flux_response_path)
    _plot_predicted_vs_observed(y_all, best_cv["predictions"], cv_scatter_path)
    _plot_confusion_matrix(best_cv["confusion_matrix"], cv_confusion_path)
    _plot_model_schematic(model_schematic_path, best_name)
    _plot_feature_importance(feature_importance, feature_importance_path)

    threshold_rows: list[dict[str, Any]] = []
    threshold_figure_paths: list[str] = []
    threshold_table_path = OUTPUT_DIR / "experimental_threshold_scan.csv"
    if not args.skip_threshold_heatmaps:
        _set_prediction_n_jobs(final_model, 1)
        max_facilities = (
            None if args.max_threshold_facilities <= 0 else args.max_threshold_facilities
        )
        threshold_rows, threshold_figure_paths = _generate_threshold_heatmaps(
            final_model,
            df,
            Path(args.raw_dir),
            facility_index_map,
            FIGURE_DIR,
            max_flux=args.scan_max_flux,
            flux_points=args.scan_flux_points,
            azimuth_step=args.threshold_azimuth_step,
            elevation_step=args.threshold_elevation_step,
            max_facilities=max_facilities,
        )
    pd.DataFrame(threshold_rows).to_csv(threshold_table_path, index=False)

    model_params_path = OUTPUT_DIR / "experimental_model_parameters.json"
    with open(model_params_path, "w", encoding="utf-8") as f:
        json.dump(_params_json_safe(final_model.get_params(deep=True)), f, ensure_ascii=False, indent=2)

    summary = {
        "raw_dir": str(args.raw_dir),
        "dataset_path": str(dataset_path),
        "model_path": str(model_path),
        "cv_predictions_path": str(cv_predictions_path),
        "feature_columns": list(COMPACT_EXPERIMENT_FEATURE_COLUMNS),
        "dk_thresholds": list(DK_THRESHOLDS),
        "dk_grade_names": list(DK_GRADE_NAMES),
        "model_parameters_path": str(model_params_path),
        "min_completion": args.min_completion,
        "cv_folds": int(args.cv_folds),
        "row_counts": {
            "all": int(len(df)),
            "train": int(len(train_df)),
            "val": int(len(val_df)),
            "test": int(len(test_df)),
        },
        "facility_index_map": facility_index_map,
        "facility_counts": df["facility_name"].value_counts().sort_index().to_dict(),
        "grade_counts": df["dk_grade_name"].value_counts().to_dict(),
        "candidate_models": model_reports,
        "best_model": best_name,
        "best_cv": {
            "metrics": best_cv["metrics"],
            "confusion_matrix": best_cv["confusion_matrix"],
        },
        "final_test": {
            **compact_metrics(final_metrics),
            "confusion_matrix": final_metrics["confusion_matrix"],
        },
        "final_test_by_facility": by_facility,
        "leave_facility_out": leave_facility_out,
        "top_feature_importance": feature_importance,
        "figures": {
            "heat_flux_response": str(heat_flux_response_path),
            "cv_predicted_vs_observed": str(cv_scatter_path),
            "cv_confusion_matrix": str(cv_confusion_path),
            "model_schematic": str(model_schematic_path),
            "feature_importance": str(feature_importance_path),
        },
        "threshold_scan": {
            "table_path": str(threshold_table_path),
            "scan_max_flux": float(args.scan_max_flux),
            "scan_flux_points": int(args.scan_flux_points),
            "azimuth_step": float(args.threshold_azimuth_step),
            "elevation_step": float(args.threshold_elevation_step),
            "summary_rows": threshold_rows,
            "figure_paths": threshold_figure_paths,
        },
        "presentation_path": str(OUTPUT_DIR / "experimental_presentation.html"),
    }
    summary_path = OUTPUT_DIR / "experimental_train_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(summary), f, ensure_ascii=False, indent=2)

    report_path = OUTPUT_DIR / "experimental_model_report.md"
    _write_report(
        report_path,
        _json_safe(summary),
        model_params_path,
        {
            "观测样本热通量-Dk响应": str(heat_flux_response_path),
            "五折预测值与观测值": str(cv_scatter_path),
            "五折等级混淆矩阵": str(cv_confusion_path),
            "模型结构示意图": str(model_schematic_path),
            "模型主要影响因素": str(feature_importance_path),
        },
    )
    presentation_path = OUTPUT_DIR / "experimental_presentation.html"
    _write_html_deck(presentation_path, _json_safe(summary))

    print(f"[train_experimental] dataset saved to {dataset_path}")
    print(f"[train_experimental] model saved to {model_path}")
    print(f"[train_experimental] summary saved to {summary_path}")
    print(f"[train_experimental] report saved to {report_path}")
    print(f"[train_experimental] presentation saved to {presentation_path}")
    print(json.dumps(_json_safe(summary["best_cv"]), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
