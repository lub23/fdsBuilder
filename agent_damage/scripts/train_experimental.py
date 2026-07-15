#!/usr/bin/env python3
"""Train experimental FDS/CSV based Dk regression surrogate models."""

from __future__ import annotations

import argparse
import html
import json
import logging
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import matplotlib as mpl
import matplotlib.font_manager as font_manager
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor
from sklearn.inspection import permutation_importance
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold, cross_val_predict, train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.src.data.experimental import (  # noqa: E402
    CaseParams,
    COMPACT_EXPERIMENT_FEATURE_COLUMNS,
    DK_GRADE_NAMES,
    DK_THRESHOLDS,
    FACILITY_CLASSIFICATION_ZH,
    case_condition_features,
    compact_experimental_features,
    directional_case_features,
    dk_to_grade,
    grade_name,
    facility_type_index,
    load_experimental_dataset,
    parse_case_name,
    parse_fds_features,
)
from agent_damage.src.data.cases_loader import (  # noqa: E402
    facility_first_fds,
    find_zero_dk_facilities,
    iter_facilities,
)
from agent_damage.src.data.zero_dk_diagnostic import (  # noqa: E402
    build_facility_diagnostic,
    write_zero_dk_report,
)
from agent_damage.src.training.regression import (  # noqa: E402
    GradeConstrainedRegressor,
    compact_metrics,
    evaluate_dk_regressor,
)

LOG = logging.getLogger(__name__)


ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "cases"
DATA_DIR = ROOT / "data"
CKPT_DIR = ROOT / "checkpoints"
OUTPUT_DIR = ROOT / "output"
FIGURE_DIR = OUTPUT_DIR / "experimental_figures"
THRESHOLD_FIGURE_DIR = FIGURE_DIR / "threshold_grids"

MIN_ACCEPTABLE_GRADE_ACCURACY = 0.95

PLOT_GRADE_LABELS = ("基本完好", "轻微", "中等", "严重")
PLOT_GRADE_FULL_LABELS = ("基本完好", "轻微破坏", "中等破坏", "严重破坏")
DURATION_LABELS = {
    1.36: "1.36 s",
    2.1: "2.1 s",
    7.5: "7.5 s",
}
FACILITY_LABELS_ZH = {
    "Boeing_Satellite": "波音卫星制造厂",
    "Hangar": "埃格林空军基地一号机库",
    "MPPF": "多载荷处理厂房（MPPF）",
    "SLC": "SLC3发射塔与移动发射台",
    "TWA": "费城国际机场TWA维修机库",
    "factory": "沃斯堡空军4号飞机工厂",
    "hangar_ligen": "立根机库",
    "hanger": "机库样本",
    "hanger1and2": "40号发射场机库",
    "ligen": "华盛顿里根国家机场机库",
    "lcc": "发射控制中心（LCC）",
    "maf": "加工厂房（MAF）",
    "ocb": "操作测试大楼（O&C Building）",
    "sspf": "空间系统处理设施（SSPF）",
    "vab": "总装大楼（VAB）",
    "boeing": "波音飞机主厂房及相邻机身辅助厂",
    "aerospace_large": "大型航空航天等效设施",
    "aerospace_medium": "中型航空航天等效设施",
    "aerospace_small": "小型航空航天等效设施",
    "airport_hangar_large": "大型机场机库等效设施",
    "airport_hangar_medium": "中型机场机库等效设施",
    "airport_hangar_small": "小型机场机库等效设施",
    "alcoa": "美铝电解设施",
    "frymaster_corporation": "弗莱马斯特总装设施",
    "gleason_cutting_tools_corporation": "格里森切削工具设施",
    "harbison_fischer": "哈比森-费希尔部装设施",
    "lob": "SLC3发射操作楼",
    "machinery_manufacturing_large": "大型机械制造等效设施",
    "machinery_manufacturing_medium": "中型机械制造等效设施",
    "machinery_manufacturing_small": "小型机械制造等效设施",
    "materion_buffalo": "马特里昂布法罗金精炼设施",
    "materion_newton": "马特里昂牛顿钽精炼设施",
    "metallurgical_facilities_large": "大型冶金等效设施",
    "metallurgical_facilities_medium": "中型冶金等效设施",
    "metallurgical_facilities_small": "小型冶金等效设施",
    "warrick_power_plant": "沃里克专用电厂",
    "yjc": "冶金钢铁厂",
    "tesla": "特斯拉机械制造设施",
}
FEATURE_LABELS_ZH = {
    "heat_flux_kw_m2": "热通量",
    "heat_flux_log10": "热通量对数",
    "heat_azimuth_deg": "方位角",
    "heat_elevation_deg": "俯仰角",
    "radiation_duration_ms": "辐射持续时间（毫秒）",
    "duration_s": "辐射持续时间",
    "heat_dose_log10": "热剂量对数",
    "elevation_sin": "俯仰角正弦项",
    "azimuth_sin": "方位角正弦项",
    "azimuth_cos": "方位角余弦项",
    "facility_type_index": "设施四大类稳定编码",
    "facility_type_oh_aerospace": "航空航天类别",
    "facility_type_oh_airport_hangar": "机场机库类别",
    "facility_type_oh_machinery_manufacturing": "机械制造类别",
    "facility_type_oh_metallurgical": "冶金类别",
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
    ("俯仰角 elevation：0、30、45、60度", "heat_elevation_deg：原始俯仰角，增强离散工况辨识"),
    ("辐射时长 duration", "radiation_duration_ms：原始毫秒时长，增强离散工况辨识"),
    ("辐射时长 duration：1.36 s、2.1 s、7.5 s", "duration_s：持续时间秒数"),
    ("热通量 heat_flux + 辐射时长 duration", "heat_dose_log10：热剂量对数，log10(heat_flux * duration + 1)"),
    ("俯仰角 elevation：0、30、45、60度", "elevation_sin：俯仰角正弦项，表达垂向入射变化"),
    ("方位角 azimuth：0-360度", "azimuth_sin：方位角正弦项，保证 0度/360度 连续"),
    ("方位角 azimuth：0-360度", "azimuth_cos：方位角余弦项，配合正弦表达完整方向"),
    ("设施所属四大类", "facility_type_index：稳定编码 0/1/2/3"),
    ("设施所属四大类", "4 个 facility_type_oh_*：共享类别特征，学习同类共性"),
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
    """Return the sole production model; retained mapping keeps report schema stable."""
    return {
        "grade_constrained_extra_trees": GradeConstrainedRegressor(
            regressor=ExtraTreesRegressor(
                n_estimators=75,
                max_features=1.0,
                min_samples_leaf=1,
                random_state=seed,
                n_jobs=-1,
            ),
            classifier=ExtraTreesClassifier(
                n_estimators=75,
                max_features=1.0,
                min_samples_leaf=1,
                criterion="entropy",
                class_weight="balanced",
                random_state=seed,
                n_jobs=-1,
            ),
            thresholds=DK_THRESHOLDS,
        )
    }


def _arrays(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    columns = list(COMPACT_EXPERIMENT_FEATURE_COLUMNS) + list(
        df.attrs.get("facility_onehot_columns", ())
    )
    X = df[columns].to_numpy(dtype=float)
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


def _feature_importance(
    model: Any,
    X: np.ndarray,
    y: np.ndarray,
    seed: int,
    feature_names: tuple[str, ...],
) -> list[dict[str, float]]:
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
            "feature": feature_names[int(i)],
            "importance": float(importances[int(i)]),
        }
        for i in order
    ]


def _is_facility_identity_feature(feature: str) -> bool:
    """Whether a feature identifies the facility rather than a physical driver."""
    name = str(feature)
    return (
        name == "facility_type_index"
        or name.startswith("facility_type_oh_")
        or name.startswith("facility_oh_")
    )


def _engineering_feature_importance(
    importances: list[dict[str, float]],
) -> list[dict[str, float]]:
    """Return physical/operational importances normalized within that subset.

    Facility/family one-hot columns and ``facility_type_index`` remain in the fitted
    model as fixed-effect controls, but are intentionally excluded from the
    engineering interpretation ranking.  Feature importance is associative,
    not causal; separating the controls prevents a facility name from being
    presented as if it were a physical damage mechanism.
    """
    engineering = [
        {"feature": str(item["feature"]), "raw_importance": float(item["importance"])}
        for item in importances
        if not _is_facility_identity_feature(str(item["feature"]))
    ]
    total = sum(max(0.0, item["raw_importance"]) for item in engineering)
    for item in engineering:
        item["importance"] = item["raw_importance"] / total if total > 0 else 0.0
    return sorted(engineering, key=lambda item: item["importance"], reverse=True)


def _feature_row(
    fds_features: dict[str, float],
    facility_name: str,
    facility_index_map: dict[str, int],
    facility_onehot_columns: tuple[str, ...],
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
        "facility_type_index": facility_type_index(facility_name, default=-1.0),
    }
    features = {**features, **compact_experimental_features(features)}
    onehot_target = "facility_oh_" + str(facility_name).replace("-", "_")
    for column in facility_onehot_columns:
        features[column] = 1.0 if column == onehot_target else 0.0
    columns = list(COMPACT_EXPERIMENT_FEATURE_COLUMNS) + list(facility_onehot_columns)
    return [float(features.get(column, 0.0)) for column in columns]


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
    if hasattr(model, "classifier_") and hasattr(model.classifier_, "n_jobs"):
        try:
            model.classifier_.n_jobs = n_jobs
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
    fig, ax = plt.subplots(figsize=(9.6, 7.0))
    labels = [_feature_label(item["feature"]) for item in items]
    values = [item["importance"] for item in items]
    bars = ax.barh(labels, values, color="#f97316", alpha=0.88)
    ax.bar_label(bars, labels=[f"{v:.3f}" for v in values], padding=4, fontsize=10)
    ax.set_xlabel("工程因素内归一化重要性")
    ax.set_title("非设施类型工程因素的重要性")
    ax.grid(True, axis="x", alpha=0.22)
    ax.set_axisbelow(True)
    fig.text(
        0.01,
        0.012,
        "注：设施模板 one-hot 与设施类型编码作为模型控制变量保留，但不参与本图排序。重要性表示关联贡献，不代表因果。",
        ha="left",
        va="bottom",
        fontsize=9.5,
        color="#4b5563",
    )
    fig.tight_layout(rect=[0, 0.055, 1, 1])
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


def _plot_model_schematic(
    path: Path, model_name: str, n_estimators: int | None = None
) -> None:
    """Draw a spacious two-row model workflow without text/icon overlap."""
    uses_logit = model_name.endswith("_logit")
    uses_grade_constraint = model_name.startswith("grade_constrained")
    tree_text = f"每个任务头 {n_estimators} 棵树" if n_estimators else "ExtraTrees 集成"

    fig, ax = plt.subplots(figsize=(16.0, 9.0))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(mpatches.Rectangle((0, 0), 1, 1, facecolor="#f8fafc", edgecolor="none"))

    ax.text(0.5, 0.955, "Dk 破坏代理模型结构示意", ha="center", va="top",
            fontsize=24, weight="bold", color="#0f172a")
    ax.text(
        0.5, 0.905,
        f"{len(COMPACT_EXPERIMENT_FEATURE_COLUMNS)} 维紧凑工程特征 + 设施编码  →  连续 Dk 与四级破坏结果",
        ha="center", va="top", fontsize=14, color="#475569",
    )

    # Upper row: data preparation and model fitting.
    _add_box(ax, 0.045, 0.565, 0.205, 0.245, "① 工况输入",
             "热通量与辐射时长\n方位角与俯仰角\n建筑尺度及开口\n可燃/敏感目标分布",
             "#eff6ff", "#2563eb")
    _add_box(ax, 0.300, 0.565, 0.215, 0.245, "② 特征构造",
             "热通量与热剂量取对数\n方位角转换为 sin/cos\n按入射方向投影暴露面\n面积、密度和占比归一化",
             "#f0fdf4", "#16a34a")
    _add_box(ax, 0.565, 0.535, 0.250, 0.305,
             "③ 双任务 ExtraTrees" if uses_grade_constraint else "③ ExtraTrees 回归",
             (
                 f"{tree_text}\n"
                 "回归头：学习连续 Dk\n"
                 + ("分类头：学习四个破坏等级\n等级约束保证输出一致"
                    if uses_grade_constraint else
                    "非线性分裂与特征交互\n输出连续损伤强度")
             ),
             "#fff7ed", "#f97316")
    _add_box(ax, 0.865, 0.565, 0.105, 0.245, "④ 连续 Dk",
             ("inverse-logit\n" if uses_logit else "范围裁剪\n") + "0 ≤ Dk ≤ 1\n保留损伤强度",
             "#fef2f2", "#dc2626")

    _add_arrow(ax, (0.250, 0.688), (0.300, 0.688))
    _add_arrow(ax, (0.515, 0.688), (0.565, 0.688))
    _add_arrow(ax, (0.815, 0.688), (0.865, 0.688))

    # Lower row: two clearly separated applications of the model output.
    _add_box(ax, 0.565, 0.205, 0.195, 0.225, "⑤ 四级结果",
             "Dk < 0.04：基本完好\n0.04 ≤ Dk < 0.10：轻微\n0.10 ≤ Dk < 0.40：中等\nDk ≥ 0.40：严重",
             "#fff1f2", "#e11d48")
    _add_box(ax, 0.800, 0.205, 0.170, 0.225, "⑥ 阈值图谱",
             "扫描热通量 q\n组合方位角与俯仰角\n记录等级首次跨越点\n标注左/右删失边界",
             "#f5f3ff", "#7c3aed")

    _add_arrow(ax, (0.918, 0.565), (0.662, 0.430), "#e11d48")
    _add_arrow(ax, (0.918, 0.565), (0.885, 0.430), "#7c3aed")

    ax.text(
        0.285, 0.335,
        "模型学习已知设施模板内的非线性响应；\n等级分类头与连续回归头共同输出，\n阈值扫描再将结果转换为工程图谱。",
        ha="center", va="center", fontsize=13, color="#334155", linespacing=1.55,
        bbox={"boxstyle": "round,pad=0.8", "facecolor": "#ffffff", "edgecolor": "#cbd5e1"},
    )

    legend_items = [
        ("输入参数", "#2563eb"), ("特征处理", "#16a34a"),
        ("模型主体", "#f97316"), ("等级输出", "#e11d48"), ("阈值应用", "#7c3aed"),
    ]
    for i, (label, color) in enumerate(legend_items):
        x = 0.075 + i * 0.180
        ax.add_patch(mpatches.Circle((x, 0.085), 0.009, facecolor=color, edgecolor="none"))
        ax.text(x + 0.016, 0.085, label, ha="left", va="center", fontsize=11.5, color="#475569")

    fig.savefig(path, bbox_inches="tight", dpi=180)
    plt.close(fig)


def _plot_extra_trees_architecture(
    path: Path, n_estimators: int, feature_count: int
) -> None:
    """Draw a spacious five-stage view of the dual-head ExtraTrees model."""
    fig, ax = plt.subplots(figsize=(17.5, 9.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(mpatches.Rectangle((0, 0), 1, 1, facecolor="#f8fafc", edgecolor="none"))

    ax.text(
        0.5,
        0.965,
        "等级约束 ExtraTrees 双任务代理模型",
        ha="center",
        va="top",
        fontsize=25,
        weight="bold",
        color="#0f172a",
    )
    ax.text(
        0.5,
        0.915,
        "连续 Dk 回归与四级毁伤分类并行计算，最终通过等级区间约束形成一致输出",
        ha="center",
        va="top",
        fontsize=14,
        color="#475569",
    )

    # Stage 1: keep report-facing feature groups visible while retaining the
    # exact numeric width used by the fitted estimator.
    _add_box(
        ax,
        0.025,
        0.31,
        0.175,
        0.47,
        f"① 输入特征（内部 {feature_count} 列）",
        "热源特征（8项）\n"
        "建筑特征（含设施类别，8项）\n"
        "可燃物与敏感目标（2项）\n\n"
        "单个工况形成一行输入",
        "#eff6ff",
        "#2563eb",
    )

    # Stage 2: the two objectives are displayed as parallel, equally weighted
    # lanes so the classifier is not mistaken for a post-processing heuristic.
    _add_box(
        ax,
        0.245,
        0.625,
        0.145,
        0.18,
        "② 连续值任务",
        "目标：设施级 Dk\n分裂准则：平方误差",
        "#fff7ed",
        "#f97316",
    )
    _add_box(
        ax,
        0.245,
        0.275,
        0.145,
        0.18,
        "② 等级任务",
        "目标：四级毁伤\nentropy + 类别平衡",
        "#fff1f2",
        "#e11d48",
    )
    _add_arrow(ax, (0.200, 0.565), (0.245, 0.715), "#f97316")
    _add_arrow(ax, (0.200, 0.525), (0.245, 0.365), "#e11d48")

    # Stage 3: dedicated forest boxes prevent tree icons and annotations from
    # colliding with arrows or aggregation formulas.
    for y, color, face, title in (
        (0.595, "#c2410c", "#fffaf5", f"③ {n_estimators} 棵回归树"),
        (0.245, "#be123c", "#fff7f9", f"③ {n_estimators} 棵分类树"),
    ):
        ax.add_patch(
            mpatches.FancyBboxPatch(
                (0.435, y),
                0.19,
                0.23,
                boxstyle="round,pad=0.012,rounding_size=0.018",
                facecolor=face,
                edgecolor=color,
                linewidth=2.0,
            )
        )
        ax.text(0.53, y + 0.197, title, ha="center", va="center", fontsize=14, weight="bold", color=color)
        for x in (0.472, 0.512, 0.552, 0.592):
            _draw_tree_icon(ax, x, y + 0.085, 0.92, color)
        ax.text(
            0.53,
            y + 0.027,
            "全样本建树 · 随机候选切分 · 树间并行",
            ha="center",
            va="center",
            fontsize=10.3,
            color="#64748b",
        )
    _add_arrow(ax, (0.390, 0.715), (0.435, 0.715), "#f97316")
    _add_arrow(ax, (0.390, 0.365), (0.435, 0.365), "#e11d48")

    # Stage 4: formulas make the aggregation semantics explicit.
    _add_box(
        ax,
        0.67,
        0.615,
        0.135,
        0.20,
        "④ 回归聚合",
        r"$\hat{D}_k^{(R)}=\frac{1}{T}\sum f_t$" "\n树输出取均值并裁剪至 [0, 1]",
        "#fffbeb",
        "#d97706",
    )
    _add_box(
        ax,
        0.67,
        0.265,
        0.135,
        0.20,
        "④ 分类聚合",
        r"$N_c=\sum I(h_t=c)$" "\n" r"$\hat{g}=\arg\max_c N_c$",
        "#fdf2f8",
        "#db2777",
    )
    _add_arrow(ax, (0.625, 0.715), (0.670, 0.715), "#d97706")
    _add_arrow(ax, (0.625, 0.365), (0.670, 0.365), "#db2777")

    # Stage 5: give the consistency rule enough room to show all intervals and
    # the final clip operation; this was the cramped part of the old figure.
    ax.add_patch(
        mpatches.FancyBboxPatch(
            (0.845, 0.245),
            0.135,
            0.59,
            boxstyle="round,pad=0.014,rounding_size=0.02",
            facecolor="#f5f3ff",
            edgecolor="#7c3aed",
            linewidth=2.2,
        )
    )
    ax.text(0.9125, 0.795, "⑤ 等级一致性约束", ha="center", va="center", fontsize=14, weight="bold", color="#6d28d9")
    ax.text(
        0.9125,
        0.685,
        "等级区间\n"
        "基本完好：[0, 0.04)\n"
        "轻微：[0.04, 0.10)\n"
        "中等：[0.10, 0.40)\n"
        "严重：[0.40, 1]",
        ha="center",
        va="center",
        fontsize=11.5,
        linespacing=1.45,
        color="#312e81",
    )
    ax.text(
        0.9125,
        0.485,
        r"$D_k=\mathrm{clip}($" "\n" r"$\hat{D}_k^{(R)},L_g,U_g)$",
        ha="center",
        va="center",
        fontsize=12.5,
        color="#312e81",
    )
    ax.text(
        0.9125,
        0.355,
        "最终输出\n连续 Dk\n+\n四级毁伤结果",
        ha="center",
        va="center",
        fontsize=13,
        weight="bold",
        linespacing=1.25,
        color="#4c1d95",
    )
    _add_arrow(ax, (0.805, 0.715), (0.845, 0.665), "#7c3aed")
    _add_arrow(ax, (0.805, 0.365), (0.845, 0.415), "#7c3aed")

    ax.text(
        0.5,
        0.105,
        "训练阶段：两个森林使用同一批输入分别学习 Dk 与等级；预测阶段：分类等级给出合法区间，回归结果提供区间内连续量级。",
        ha="center",
        va="center",
        fontsize=13.2,
        color="#334155",
        bbox={"boxstyle": "round,pad=0.7", "facecolor": "#ffffff", "edgecolor": "#cbd5e1"},
    )
    fig.savefig(path, bbox_inches="tight", dpi=180)
    plt.close(fig)


def _threshold_table_for_facility(
    model: Any,
    fds_features: dict[str, float],
    facility_name: str,
    facility_index_map: dict[str, int],
    facility_onehot_columns: tuple[str, ...],
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
                        facility_onehot_columns,
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
) -> np.ma.MaskedArray:
    """Prepare finite threshold values without disguising right-censored cells.

    A NaN means that Dk did not cross the requested damage threshold anywhere
    in the scan interval.  Filling it with ``max_flux`` made a genuinely
    right-censored result visually identical to a threshold exactly at the
    scan limit.  Keep those cells masked so the plot can show them with a
    dedicated grey/hatch encoding.
    """
    smoothed = _smooth_grid(values)
    finite = np.isfinite(values)
    clipped = np.clip(smoothed, min_display_flux, max_flux)
    return np.ma.array(clipped, mask=~finite)


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
    fig.subplots_adjust(left=0.075, right=0.88, top=0.88, bottom=0.165, wspace=0.07, hspace=0.10)
    norm = mpl.colors.LogNorm(vmin=min_display_flux, vmax=max_flux)
    threshold_cmap = mpl.colormaps["turbo"].copy()
    threshold_cmap.set_bad("#d1d5db")
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
                cmap=threshold_cmap,
                norm=norm,
                interpolation="bilinear",
            )
            no_crossing = ~np.isfinite(values)
            if np.any(no_crossing):
                # Hatching is deliberately separate from the colour scale:
                # these cells mean threshold > scan limit, not threshold=max.
                ax.contourf(
                    azimuths,
                    elevations,
                    no_crossing.astype(float),
                    levels=[0.5, 1.5],
                    colors=["none"],
                    hatches=["////"],
                )
            left_censored = np.isfinite(values) & np.isclose(values, min_display_flux)
            if np.any(left_censored):
                # A crossing at the scan lower bound is left-censored. Mark
                # it as an upper bound instead of displaying a fabricated zero.
                ax.contourf(
                    azimuths,
                    elevations,
                    left_censored.astype(float),
                    levels=[0.5, 1.5],
                    colors=["none"],
                    hatches=["...."],
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
        cbar.set_label("已跨越阈值的 q (kW/m²，对数色标)")
        ticks = [
            tick
            for tick in [min_display_flux, 500.0, 1000.0, 3000.0, 5000.0, 10000.0, max_flux]
            if min_display_flux <= tick <= max_flux
        ]
        unique_ticks = []
        for tick in ticks:
            if tick not in unique_ticks:
                unique_ticks.append(tick)
        cbar.set_ticks(unique_ticks)
        cbar.ax.set_yticklabels([f"{tick:g}" for tick in unique_ticks])
        hatch_patch = mpatches.Patch(
            facecolor="#d1d5db",
            edgecolor="#4b5563",
            hatch="////",
            label=f"> {max_flux / 1000:g} MW/m²（扫描上限仍未跨越）",
        )
        left_patch = mpatches.Patch(
            facecolor="none",
            edgecolor="#111827",
            hatch="....",
            label=f"≤ {min_display_flux:g} kW/m²（扫描下限已跨越）",
        )
        fig.legend(
            handles=[hatch_patch, left_patch],
            loc="lower center",
            bbox_to_anchor=(0.5, 0.025),
            ncol=2,
            frameon=False,
            fontsize=10,
            columnspacing=2.5,
            handlelength=2.8,
        )
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _generate_threshold_heatmaps(
    model: Any,
    df: pd.DataFrame,
    cases_dir: Path,
    facility_index_map: dict[str, int],
    facility_onehot_columns: tuple[str, ...],
    figure_dir: Path,
    max_flux: float,
    flux_points: int,
    azimuth_step: float,
    elevation_step: float,
    max_facilities: int | None,
    min_flux: float = 100.0,
    cleanup_stale: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    if min_flux <= 0.0 or min_flux >= max_flux:
        raise ValueError("Threshold scan requires 0 < min_flux < max_flux")
    azimuths = np.arange(0.0, 360.0 + 0.1, azimuth_step, dtype=float)
    elevations = np.arange(0.0, 60.0 + 0.1, elevation_step, dtype=float)
    durations = (1.36, 2.1, 7.5)
    facility_rows = (
        df.sort_values(["facility_name", "fds_file"])
        .drop_duplicates("facility_name")
        .sort_values("facility_name")
    )
    if max_facilities is not None and max_facilities > 0:
        facility_rows = facility_rows.head(max_facilities)

    threshold_dir = figure_dir / "threshold_grids"
    threshold_dir.mkdir(parents=True, exist_ok=True)
    observed_damage_facilities = set(
        df.groupby("facility_name")["Dk"]
        .max()
        .loc[lambda values: values >= DK_THRESHOLDS[0]]
        .index.astype(str)
    )
    expected_names = {
        f"threshold_grid_{str(name)}.png".replace("/", "_")
        for name in facility_rows["facility_name"]
        if str(name) in observed_damage_facilities
    }
    # Remove only stale files produced by this generator (for example the old
    # alias names hangar_ligen/hanger); otherwise they look like current maps.
    if max_facilities is None and cleanup_stale:
        for old_path in threshold_dir.glob("threshold_grid_*.png"):
            if old_path.name not in expected_names:
                old_path.unlink()

    table_rows: list[dict[str, Any]] = []
    figure_paths: list[str] = []
    for _, row in facility_rows.iterrows():
        facility_name = str(row["facility_name"])
        facility_root = cases_dir / facility_name
        fds_path = facility_root / str(row["fds_file"])
        if not fds_path.exists():
            candidates = sorted(facility_root.glob("*.fds"))
            if candidates:
                fds_path = candidates[0]
            else:
                continue
        print(f"[train_experimental] threshold scan {facility_name}")
        facility_observations = df[df["facility_name"].eq(facility_name)]
        plot_omitted_no_observed_damage = facility_name not in observed_damage_facilities
        # Product requirement: every threshold chart and audit scan uses the
        # same explicit 100..20,000 kW/m² scale. Values crossing at the first
        # point are lower-bound censored; the surrogate is not claimed to be a
        # physical extrapolator below the observed facility-specific range.
        min_display_flux = float(min_flux)
        filename = f"threshold_grid_{facility_name}.png".replace("/", "_")
        figure_path = threshold_dir / filename
        if plot_omitted_no_observed_damage:
            # All observed conditions stayed below the first damage threshold.
            # Do not ask the surrogate to invent a surface unsupported by any
            # damaged observation. Keep explicit right-censored audit rows.
            for duration_s in durations:
                for damage_label in DK_GRADE_NAMES[1:]:
                    table_rows.append(
                        {
                            "facility_name": facility_name,
                            "duration_s": float(duration_s),
                            "damage_grade_name": damage_label,
                            "min_threshold_flux": None,
                            "median_threshold_flux": None,
                            "max_threshold_flux": None,
                            "no_crossing_fraction": 1.0,
                            "crossing_fraction": 0.0,
                            "left_censored_fraction": 0.0,
                            "left_censoring_status": "none",
                            "scan_min_flux": min_display_flux,
                            "censoring_status": "all_right_censored",
                            "scan_limit_flux": float(max_flux),
                            "plot_omitted_no_observed_damage": True,
                        }
                    )
            if figure_path.exists():
                figure_path.unlink()
            print(
                f"[train_experimental] omit threshold figure {facility_name}: "
                "all observed cases are below Dk=0.04"
            )
            continue
        flux_values = np.linspace(min_display_flux, max_flux, flux_points, dtype=float)
        fds_features = parse_fds_features(fds_path)
        maps_by_duration: dict[float, dict[str, np.ndarray]] = {}
        for duration_s in durations:
            threshold_maps = _threshold_table_for_facility(
                model,
                fds_features,
                facility_name,
                facility_index_map,
                facility_onehot_columns,
                azimuths,
                elevations,
                duration_s,
                flux_values,
            )
            maps_by_duration[duration_s] = threshold_maps
            for damage_label, values in threshold_maps.items():
                finite = values[np.isfinite(values)]
                left_censored = np.isfinite(values) & np.isclose(values, min_display_flux)
                table_rows.append(
                    {
                        "facility_name": facility_name,
                        "duration_s": float(duration_s),
                        "damage_grade_name": damage_label,
                        "min_threshold_flux": float(np.min(finite)) if len(finite) else None,
                        "median_threshold_flux": float(np.median(finite)) if len(finite) else None,
                        "max_threshold_flux": float(np.max(finite)) if len(finite) else None,
                        "no_crossing_fraction": float(np.mean(~np.isfinite(values))),
                        "crossing_fraction": float(np.mean(np.isfinite(values))),
                        "left_censored_fraction": float(np.mean(left_censored)),
                        "left_censoring_status": (
                            "all_left_censored"
                            if np.all(left_censored)
                            else "partly_left_censored"
                            if np.any(left_censored)
                            else "none"
                        ),
                        "scan_min_flux": min_display_flux,
                        "censoring_status": (
                            "all_right_censored"
                            if not len(finite)
                            else "partly_right_censored"
                            if np.any(~np.isfinite(values))
                            else "fully_observed"
                        ),
                        "scan_limit_flux": float(max_flux),
                        "plot_omitted_no_observed_damage": bool(
                            plot_omitted_no_observed_damage
                        ),
                    }
                )
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


RESISTANCE_REASON_ZH: dict[str, str] = {
    "aerospace_large": (
        "设施体量和资产价值基数很大，损伤集中在少量局部资产；设施级 Dk 采用价值加权后被显著稀释。"
    ),
    "alcoa": (
        "15 MW/m² 观测中仅少量资产产生修复费用，相对于全设施资产基数仍属局部损伤，价值加权 Dk 很低。"
    ),
    "frymaster_corporation": (
        "资产侧峰值辐射远低于名义入射热通量，虽出现局部温升/修复，损伤未扩展到足以跨越设施级阈值。"
    ),
    "gleason_cutting_tools_corporation": (
        "资产侧最高温度约 61 °C、峰值辐射约 39 kW/m²，显示围护、距离和遮挡对 15 MW/m² 名义入射有强衰减。"
    ),
    "harbison_fischer": (
        "资产侧最高温度约 56 °C、峰值辐射约 69 kW/m²，绝大多数目标未形成有效热损伤。"
    ),
    "lob": (
        "现有工况最高资产温度约 191 °C，低于约 292 °C 的记录着火阈值，未触发资产损伤。"
    ),
    "machinery_manufacturing_large": (
        "大尺度厂房内损伤仍以局部资产为主；截至 15 MW/m² 的最大 Dk=0.0377，接近但尚未跨越轻微阈值。"
    ),
}


def _observed_resistance_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for facility_name, group in df.groupby("facility_name", sort=True):
        if int(group["dk_grade"].max()) > 0:
            continue
        rows.append(
            {
                "facility_name": str(facility_name),
                "case_count": int(len(group)),
                "max_observed_flux": float(group["heat_flux_kw_m2"].max()),
                "max_observed_dk": float(group["Dk"].max()),
                "reason": RESISTANCE_REASON_ZH.get(
                    str(facility_name),
                    "现有观测只支持设施级 Dk 未跨越 0.04；应结合资产温度、辐射暴露和价值权重进一步复核。",
                ),
            }
        )
    return rows


def _active_fds_cases() -> list[str]:
    """Return unique active FDS input names for a report-time progress note."""
    names: set[str] = set()
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    for proc_dir in proc_root.iterdir():
        if not proc_dir.name.isdigit():
            continue
        try:
            parts = (proc_dir / "cmdline").read_bytes().split(b"\0")
        except (OSError, PermissionError):
            continue
        decoded = [part.decode("utf-8", errors="ignore") for part in parts if part]
        if not decoded or not any(Path(part).name == "fds" for part in decoded):
            continue
        names.update(Path(part).name for part in decoded if part.lower().endswith(".fds"))
    return sorted(names)


def _threshold_cell_text(item: dict[str, Any] | None, max_flux: float) -> str:
    if not item or item.get("median_threshold_flux") is None:
        return f">{max_flux:,.0f}*"
    value = float(item["median_threshold_flux"])
    censored = float(item.get("no_crossing_fraction", 0.0) or 0.0)
    left_censored = float(item.get("left_censored_fraction", 0.0) or 0.0)
    suffix_parts = []
    if censored > 0:
        suffix_parts.append(f"{censored:.0%}右删失*")
    if left_censored > 0:
        suffix_parts.append(f"{left_censored:.0%}左删失†")
    suffix = f" ({'，'.join(suffix_parts)})" if suffix_parts else ""
    return f"{value:,.0f}{suffix}"


def _write_report(
    path: Path,
    summary: dict[str, Any],
    model_params_path: Path,
    figure_paths: dict[str, str],
) -> None:
    cv = summary["best_cv"]["metrics"]
    test = summary["final_test"]
    threshold_scan = summary["threshold_scan"]
    threshold_figures = threshold_scan["figure_paths"]
    min_flux = float(threshold_scan.get("scan_min_flux", 100.0))
    max_flux = float(threshold_scan["scan_max_flux"])
    omitted_threshold_figures = threshold_scan.get(
        "plot_omitted_no_observed_damage", []
    )
    resistant_rows = summary.get("observed_resistant_facilities", [])
    active_cases = summary.get("run_status", {}).get("active_fds_cases", [])
    lines: list[str] = []
    lines.append("# Dk 破坏代理模型优化与完整阈值报告")
    lines.append("")
    lines.append(f"> 报告生成时间：{summary.get('generated_at', '—')}（Asia/Shanghai）")
    lines.append("")
    lines.append("## 1. 当前进展与数据冻结状态")
    lines.append(
        f"- 模型训练已完成：权威快照为 **{summary['row_counts']['all']} 条唯一工况 / "
        f"{len(summary['facility_counts'])} 个设施**，最终模型为 `{summary['best_model']}`。"
    )
    lines.append(
        f"- 五折行级交叉验证等级准确率 **{_pct(cv['grade_accuracy'])}**、macro F1 "
        f"**{_pct(cv['grade_macro_f1'])}**；独立测试等级准确率 **{_pct(test['grade_accuracy'])}**。"
    )
    lines.append(
        f"- 阈值数值扫描已覆盖 {len(summary['facility_counts'])} 个设施；按规则绘制 "
        f"{len(threshold_figures)} 张图，另有 {len(omitted_threshold_figures)} 个设施因所有观测工况均未损伤而不绘图。"
        f"扫描范围为 **{min_flux:g}–{max_flux:,.0f} kW/m²**。"
    )
    if active_cases:
        lines.append(
            "- 报告生成时仍检测到后台 FDS 补跑："
            + "、".join(f"`{name}`" for name in active_cases)
            + "。这些正在运行且尚未形成损伤 CSV 的工况**未进入本次训练快照**，完成后需重新汇总并再训练。"
        )
    else:
        lines.append(
            "- 报告生成时未检测到活跃 FDS 进程；但是否已完成损伤后处理，仍以 `agent_damage/cases/` 中的汇总 CSV 为准。"
        )
    lines.append("")
    lines.append(
        "> 适用范围：当前验证为同一设施模板内的随机行级划分，且使用设施 one-hot；它衡量“已知设施的新工况”能力，"
        "不能直接解释为对全新设施的泛化精度。"
    )
    lines.append("")
    lines.append("## 2. 数据与建模口径")
    lines.append(
        f"- 质量口径：保留 `completion_ratio >= {summary['min_completion']}`、"
        f"仅删除 `simulation_time_s < {summary.get('min_simulation_time_s', 50):g}` 且为基本完好的短时样本；已出现损伤的短时样本保留，并要求 `0 <= Dk <= 1`。"
    )
    excluded_short = summary.get("data_quality", {}).get("excluded_short_run_count", 0)
    cutoff = summary.get("min_simulation_time_s", 50)
    lines.append(
        f"- 因实际运行时间小于 {cutoff:g} s 且仍基本完好而排除：**{excluded_short} 条**；"
        "短时但已达到损伤等级的工况均保留。"
    )
    lines.append(
        "- 本轮工况增量审计：`experimental_case_inventory_audit.md` / "
        "`experimental_case_inventory_delta.csv`。"
    )
    lines.append(
        f"- 模型输入共 {len(summary['feature_columns'])} 维：{len(COMPACT_EXPERIMENT_FEATURE_COLUMNS)} 个紧凑特征（含稳定四类索引及 4 个类别 one-hot）+ "
        f"{len(summary['facility_onehot_columns'])} 个设施模板编码。"
    )
    lines.append(
        "- 输出口径：连续 Dk 按 0.04、0.10、0.40 划分为基本完好、轻微破坏、中等破坏和严重破坏。"
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
        "方位角使用 `sin/cos` 保证 0° 与 360° 连续；设施 one-hot 只用于已见过的 36 个设施模板。"
    )
    lines.append("")
    lines.append("### 2.2 设施与分类口径")
    lines.append("")
    lines.append("| 设施 | 分类 | 工况数 |")
    lines.append("|---|---|---:|")
    classifications = summary.get("facility_classifications", {})
    for facility, count in sorted(summary["facility_counts"].items()):
        lines.append(
            f"| {_facility_label(facility)} (`{facility}`) | "
            f"{classifications.get(facility, facility)} | {count} |"
        )
    lines.append("")
    lines.append("## 3. 模型结果")
    model_parameters = summary.get("model_parameters", {})
    if str(summary["best_model"]).startswith("grade_constrained"):
        reg_trees = model_parameters.get("regressor__n_estimators", "—")
        clf_trees = model_parameters.get("classifier__n_estimators", "—")
        lines.append(
            f"- 最终模型：`{summary['best_model']}`（{reg_trees} 棵 ExtraTrees 连续 Dk 回归 + "
            f"{clf_trees} 棵 ExtraTrees 四等级分类约束）。"
        )
    else:
        tree_count = model_parameters.get("n_estimators", model_parameters.get("regressor__n_estimators", "—"))
        target_space = "logit(Dk) 目标空间" if str(summary["best_model"]).endswith("_logit") else "原始 Dk 目标空间"
        lines.append(
            f"- 最终模型：`{summary['best_model']}`（{tree_count} 棵 ExtraTrees，{target_space}）。"
        )
    lines.append(f"- 五折：accuracy {_pct(cv['grade_accuracy'])}，macro F1 {_pct(cv['grade_macro_f1'])}，weighted F1 {_pct(cv['grade_weighted_f1'])}。")
    lines.append(f"- 连续值辅助指标：MAE {cv['mae']:.4f}，RMSE {cv['rmse']:.4f}，R² {cv['r2']:.4f}。")
    lines.append("")
    lines.append("![五折交叉验证等级混淆矩阵](experimental_figures/cv_confusion_matrix.png)")
    lines.append("")
    lines.append("轻微破坏样本最少、召回率相对最低；总体准确率超过 95% 不代表每个设施均超过 95%。")
    lines.append("")
    lines.append("## 4. 结果图")
    for label, figure_path in figure_paths.items():
        lines.append(f"- {label}: `{figure_path}`")
    lines.extend([
        "",
        "![观测样本热通量-Dk响应](experimental_figures/heat_flux_response_observed.png)",
        "",
        "![五折预测值与观测值](experimental_figures/cv_predicted_vs_observed.png)",
        "",
        "![模型结构示意图](experimental_figures/model_schematic.png)",
        "",
        "![ExtraTrees双任务架构图](experimental_figures/extra_trees_architecture.png)",
        "",
        "![非设施类型工程因素重要性](experimental_figures/feature_importance.png)",
        "",
    ])
    lines.append(
        "主要影响因素图只排序可解释的工程变量。四大类共享 one-hot、稳定类型编码和设施个体 one-hot "
        "同时作为控制变量保留在模型中，以兼顾同类共性与单设施差异；这些身份控制项从工程因素榜单中排除。"
    )
    lines.append("")
    lines.append("## 5. 完整热通量阈值扫描方法与 20 MW/m² 表示")
    lines.append(
        "对每个设施固定 FDS 几何、开口和目标分布，在 1.36 s、2.1 s、7.5 s 下扫描方位角 0–360°、"
        "俯仰角 0–60°及热通量 q；首次跨越 Dk=0.04/0.10/0.40 的 q 记为等级阈值。"
    )
    lines.append(
        f"扫描上限为 {max_flux:,.0f} kW/m²（{max_flux / 1000:g} MW/m²）。若到达上限仍未跨越，"
        f"该网格是**右删失**结果，图中用**灰色斜线**表示，表中写作 `>{max_flux:,.0f}*`；"
        "它绝不能填成 20,000 的普通彩色值，否则会误解成阈值恰好等于上限。"
    )
    lines.append(
        f"扫描下限统一固定为 {min_flux:g} kW/m²。若扫描首点已经跨越，"
        "该网格按左删失处理（点状网格、表中 `†`），含义是实际阈值不高于该扫描下限。"
        "部分网格未跨越时，中位数仅对已跨越网格计算，并在括号中给出左右删失比例。"
    )
    lines.append(f"- 阈值汇总 CSV：`{threshold_scan['table_path']}`")
    lines.append(
        f"- 热力图：{len(threshold_figures)} 张（有观测损伤的设施每设施 1 张，3 个持续时间 × 3 个损伤等级）。"
    )
    if omitted_threshold_figures:
        lines.append(
            "- 未绘图设施（所有观测工况 Dk<0.04）："
            + "、".join(f"`{name}`" for name in omitted_threshold_figures)
            + "。这些设施仍保留阈值扫描 CSV 行用于审计。"
        )
    lines.append("")
    lines.append("## 6. 高热通量下仍未达到设施级损伤的原因")
    lines.append(
        "这里的“未损伤”指设施级价值加权 Dk 未跨越 0.04，不等于每一件资产都没有温升、燃烧或修复费用。"
        "下表为训练观测中始终处于基本完好的设施；原因来自现有资产明细、几何特征和 Dk 定义。"
    )
    lines.append("")
    lines.append("| 设施 | 已观测最高 q | 最大 Dk | 数据支持的主要解释 |")
    lines.append("|---|---:|---:|---|")
    for row in resistant_rows:
        lines.append(
            f"| {_facility_label(row['facility_name'])} | {row['max_observed_flux']/1000:g} MW/m² | "
            f"{row['max_observed_dk']:.6f} | {row['reason']} |"
        )
    lines.append("")
    lines.append("共同机制包括：")
    lines.append("1. **入射与资产暴露并不等价**：围护结构、距离、遮挡和开口方向可把名义热通量大幅衰减到资产侧。")
    lines.append("2. **短时脉冲与热惯性**：1.36–7.5 s 的高峰值未必能让厚重或耐热设备达到损伤温度/持续时间条件。")
    lines.append("3. **局部损伤被价值权重稀释**：Dk=总修复成本/设施资产价值基数，少量低价值部件损坏仍可能保持 Dk<0.04。")
    lines.append("4. **库存和判据效应**：非可燃/高阈值资产、低敏感目标密度，或资产未达到记录的着火/参考温度，都会限制 Dk。")
    lines.append(
        f"5. **模型边界而非物理不可毁**：树模型不具备可靠的区间外外推能力；"
        f"`>{max_flux / 1000:g} MW/m²` 只表示本次模型扫描未跨越，不能宣称设施物理上不可破坏。"
    )
    lines.append("")
    lines.append("## 7. 设施阈值图谱")
    for figure_path in threshold_figures:
        figure = Path(figure_path)
        facility = figure.stem.replace("threshold_grid_", "")
        rel_path = _relative_output_path(figure)
        lines.extend([
            f"### {_facility_label(facility)}",
            "",
            f"![{_facility_label(facility)}阈值热力图]({rel_path})",
            "",
        ])
    lines.append("## 8. 工程使用建议")
    lines.append(
        "将模型作为已知设施的快速阈值筛查工具；对灰色斜线区、等级边界附近和决策关键工况，"
        "应回到代表性 FDS 计算复核。待当前补跑完成并生成损伤 CSV 后，应重新加载、训练和刷新本报告。"
    )
    lines.append("")
    lines.append("## 9. 输出文件")
    lines.append(f"- 训练模型：`{summary['model_path']}`")
    lines.append(f"- 训练摘要：`{OUTPUT_DIR / 'experimental_train_summary.json'}`")
    lines.append(f"- 阈值汇总：`{threshold_scan['table_path']}`")
    lines.append(f"- 模型参数：`{model_params_path}`")
    lines.append(f"- HTML 报告：`{OUTPUT_DIR / 'experimental_presentation.html'}`")
    lines.append(f"- 工况增量审计：`{OUTPUT_DIR / 'experimental_case_inventory_audit.md'}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _threshold_pivot_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, float], dict[str, Any]] = {}
    for row in summary.get("threshold_scan", {}).get("summary_rows", []):
        key = (str(row["facility_name"]), float(row["duration_s"]))
        item = grouped.setdefault(
            key,
            {"facility_name": str(row["facility_name"]), "duration_s": float(row["duration_s"])},
        )
        item[str(row["damage_grade_name"])] = row
    return [grouped[key] for key in sorted(grouped, key=lambda item: (item[0], item[1]))]


def _image_tag(path: str | Path, alt: str, class_name: str = "") -> str:
    rel_path = html.escape(_relative_output_path(path))
    class_attr = f' class="{html.escape(class_name)}"' if class_name else ""
    return f'<img src="{rel_path}" alt="{html.escape(alt)}"{class_attr}>'


def _write_html_deck(path: Path, summary: dict[str, Any]) -> None:
    cv = summary["best_cv"]["metrics"]
    test = summary["final_test"]
    figures = summary["figures"]
    threshold_figures = summary["threshold_scan"]["figure_paths"]
    min_flux = float(summary["threshold_scan"].get("scan_min_flux", 100.0))
    max_flux = float(summary["threshold_scan"]["scan_max_flux"])
    top_features = summary.get("engineering_feature_importance") or _engineering_feature_importance(
        summary["top_feature_importance"]
    )
    top_features = top_features[:8]
    threshold_rows = _threshold_pivot_rows(summary)
    active_cases = summary.get("run_status", {}).get("active_fds_cases", [])
    resistant_rows = summary.get("observed_resistant_facilities", [])
    omitted_threshold_figures = summary.get("threshold_scan", {}).get(
        "plot_omitted_no_observed_damage", []
    )

    feature_items = "\n".join(
        f"<li><span>{html.escape(_feature_label(item['feature']))}</span>"
        f"<strong>{float(item['importance']):.3f}</strong></li>"
        for item in top_features
    )
    def threshold_row_html(row: dict[str, Any]) -> str:
        return (
            "<tr>"
            f"<td>{html.escape(_facility_label(row['facility_name']))}</td>"
            f"<td>{DURATION_LABELS.get(float(row['duration_s']), str(row['duration_s']))}</td>"
            f"<td>{html.escape(_threshold_cell_text(row.get(DK_GRADE_NAMES[1]), max_flux))}</td>"
            f"<td>{html.escape(_threshold_cell_text(row.get(DK_GRADE_NAMES[2]), max_flux))}</td>"
            f"<td>{html.escape(_threshold_cell_text(row.get(DK_GRADE_NAMES[3]), max_flux))}</td>"
            "</tr>"
        )

    threshold_table_slides = "\n".join(
        f"""
        <section class="slide compact-table-slide">
          <div class="slide-head">
            <p>阈值表</p>
            <h2>中位阈值摘要（{page_i + 1}/{max(1, (len(threshold_rows) + 11) // 12)}）</h2>
          </div>
          <table>
            <thead><tr><th>设施</th><th>持续时间</th><th>轻微</th><th>中等</th><th>严重</th></tr></thead>
            <tbody>{''.join(threshold_row_html(row) for row in threshold_rows[start:start + 12])}</tbody>
          </table>
          <p class="note">单位：kW/m²。&gt;{max_flux:,.0f}* 表示达到 {max_flux / 1000:g} MW/m² 仍未跨越；括号百分比为右删失网格占比。</p>
        </section>
        """
        for page_i, start in enumerate(range(0, len(threshold_rows), 12))
    )
    resistance_slides = "\n".join(
        f"""
        <section class="slide resistance-slide">
          <div class="slide-head">
            <p>高通量下仍为基本完好</p>
            <h2>原因与数据边界（{page_i + 1}/{max(1, (len(resistant_rows) + 3) // 4)}）</h2>
          </div>
          <table>
            <thead><tr><th>设施</th><th>最高观测 q</th><th>最大 Dk</th><th>数据支持的解释</th></tr></thead>
            <tbody>{''.join(
                '<tr>'
                f'<td>{html.escape(_facility_label(row["facility_name"]))}</td>'
                f'<td>{float(row["max_observed_flux"])/1000:g} MW/m²</td>'
                f'<td>{float(row["max_observed_dk"]):.6f}</td>'
                f'<td>{html.escape(str(row["reason"]))}</td>'
                '</tr>'
                for row in resistant_rows[start:start + 4]
            )}</tbody>
          </table>
          <p class="note">“基本完好”是设施级价值加权 Dk&lt;0.04，不等于每一件资产都无温升或无局部修复。</p>
        </section>
        """
        for page_i, start in enumerate(range(0, len(resistant_rows), 4))
    )
    active_status_html = (
        "报告生成时仍有后台 FDS 工况运行："
        + "、".join(f"<code>{html.escape(name)}</code>" for name in active_cases)
        + "。尚未形成损伤 CSV 的结果未进入本次训练。"
        if active_cases
        else "报告生成时未检测到活跃 FDS 进程；是否完成损伤后处理仍以 cases/ 汇总 CSV 为准。"
    )
    feature_table_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(direct)}</td>"
        f"<td>{html.escape(derived)}</td>"
        "</tr>"
        for direct, derived in COMPACT_FEATURE_TABLE
    )
    facility_items = sorted(summary["facility_counts"].items())
    classifications = summary.get("facility_classifications", {})
    facility_classification_slides = "\n".join(
        f"""
        <section class="slide compact-table-slide">
          <div class="slide-head">
            <p>设施分类</p>
            <h2>训练设施与分类（{page_i + 1}/{max(1, (len(facility_items) + 11) // 12)}）</h2>
          </div>
          <table>
            <thead><tr><th>设施</th><th>简称</th><th>分类</th><th>工况数</th></tr></thead>
            <tbody>{''.join(
                '<tr>'
                f'<td>{html.escape(_facility_label(facility))}</td>'
                f'<td><code>{html.escape(facility)}</code></td>'
                f'<td>{html.escape(str(classifications.get(facility, facility)))}</td>'
                f'<td>{int(count)}</td>'
                '</tr>'
                for facility, count in facility_items[start:start + 12]
            )}</tbody>
          </table>
        </section>
        """
        for page_i, start in enumerate(range(0, len(facility_items), 12))
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
    .compact-table-slide th, .compact-table-slide td {{ font-size: 15px; padding: 5px 8px; }}
    .resistance-slide th, .resistance-slide td {{ font-size: 17px; padding: 8px 9px; vertical-align: top; }}
    code {{ background: #f1f5f9; padding: 2px 5px; border-radius: 4px; font-size: 0.85em; }}
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
      <p class="subtitle">{summary['row_counts']['all']} 条工况、{len(summary['facility_counts'])} 个设施、{min_flux:g}–{max_flux:,.0f} kW/m² 完整阈值扫描；灰色斜线专门表示扫描上限仍未跨越。</p>
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>当前进展</p>
        <h2>模型已完成，补跑结果按快照管理</h2>
      </div>
      <div class="metrics">
        <div class="metric"><strong>{summary['row_counts']['all']}</strong><span>训练工况</span></div>
        <div class="metric"><strong>{len(summary['facility_counts'])}</strong><span>设施模板</span></div>
        <div class="metric"><strong>{len(threshold_figures)}</strong><span>按规则生成阈值图</span></div>
      </div>
      <p>{active_status_html}</p>
      <p class="note">快照生成时间：{html.escape(str(summary.get('generated_at', '—')))}（Asia/Shanghai）。新补跑需完成损伤后处理、进入 cases/ 后再训练才会影响本报告。</p>
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>核心结论</p>
        <h2>等级准确率达到 95% 优化目标</h2>
      </div>
      <div class="metrics">
        <div class="metric"><strong>{_pct(cv['grade_accuracy'])}</strong><span>五折等级准确率</span></div>
        <div class="metric"><strong>{_pct(cv['grade_weighted_f1'])}</strong><span>加权 F1</span></div>
        <div class="metric"><strong>{_pct(test['grade_accuracy'])}</strong><span>独立测试准确率</span></div>
      </div>
      <p>汇报中以等级准确率和阈值图谱为主线，连续 Dk 误差作为辅助说明，避免指标过多分散重点。</p>
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>建模口径</p>
        <h2>{len(COMPACT_EXPERIMENT_FEATURE_COLUMNS)}维紧凑输入，从连续 Dk 到破坏等级</h2>
      </div>
      <div class="two-col">
        <div>
          <h3>输入信息</h3>
          <p>热源强度与方向、设施/建筑尺度、入射侧开口暴露和可燃/敏感目标暴露共同进入模型。</p>
          <p>方位角使用正弦和余弦表达，保证 0度 与 360度 在输入层连续。</p>
          <h3>输出方式</h3>
          <p>连续回归头预测 Dk，等级分类头进行一致性约束，再按 0.04、0.10、0.40 输出基本完好、轻微破坏、中等破坏和严重破坏。</p>
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

    {facility_classification_slides}

    <section class="slide image-slide">
      <div class="slide-head">
        <p>模型结构</p>
        <h2>{html.escape(str(summary['best_model']))} 代理模型</h2>
      </div>
      {_image_tag(figures['model_schematic'], "模型结构示意图", "diagram-image")}
    </section>

    <section class="slide image-slide">
      <div class="slide-head">
        <p>随机树内部架构</p>
        <h2>75棵回归树 + 75棵分类树并行聚合</h2>
      </div>
      {_image_tag(figures['extra_trees_architecture'], "ExtraTrees双任务架构图", "diagram-image")}
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
        <h2>排除设施类型后，主要工程因素集中在入射方向、热通量与热剂量</h2>
      </div>
      <div class="two-col">
        {_image_tag(figures['feature_importance'], "非设施类型工程因素重要性", "wide-image")}
        <ul class="feature-list">
          {feature_items}
        </ul>
      </div>
      <p class="note">设施模板 one-hot 和设施类型编码仍作为模型控制变量保留，但不参与本页排名；工程因素重要性已在该子集内重新归一化。</p>
    </section>

    <section class="slide">
      <div class="slide-head">
        <p>阈值扫描</p>
        <h2>固定设施条件，扫描入射热通量</h2>
      </div>
      <p>对每个设施模板固定几何、开口和可燃/敏感目标分布；在 1.36 s、2.1 s、7.5 s 三个持续时间下，随方位角和俯仰角扫描 q，记录 Dk 首次跨越各等级阈值的位置。</p>
      <p>扫描范围为 {min_flux:g}–{max_flux:,.0f} kW/m²。彩色区域表示已跨越阈值；<strong>灰色斜线</strong>表示到达上限仍未跨越，是右删失结果（真实阈值若存在则更高），不是“阈值恰好等于 {max_flux / 1000:g} MW/m²”。</p>
      <p>有观测损伤的设施每设施一张图，三列为持续时间，三行为轻微、中等、严重破坏阈值。所有观测工况均为基本完好的 {len(omitted_threshold_figures)} 个设施按规则不绘图：{html.escape('、'.join(omitted_threshold_figures) or '无')}。</p>
      <p class="note">输出阈值表：{html.escape(_relative_output_path(summary['threshold_scan']['table_path']))}</p>
    </section>

    {threshold_slides}

    {threshold_table_slides}

    {resistance_slides}

    <section class="slide">
      <div class="slide-head">
        <p>物理解释与边界</p>
        <h2>高热通量不必然转化为设施级高 Dk</h2>
      </div>
      <ol>
        <li>围护结构、距离、遮挡和开口方向使资产侧暴露显著低于名义入射。</li>
        <li>1.36–7.5 s 短时脉冲受热惯性限制，未必满足温度与持续时间损伤条件。</li>
        <li>局部低价值资产损伤会被全设施资产价值分母稀释。</li>
        <li>非可燃/高阈值资产及低敏感目标密度限制损伤扩展。</li>
      </ol>
      <p class="note">树模型不能可靠外推；“&gt;{max_flux / 1000:g} MW/m²”是本次扫描的模型右删失，不是物理上不可破坏的证明。</p>
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
    parser.add_argument("--cases-dir", type=Path, default=CASES_DIR)
    parser.add_argument("--min-completion", type=float, default=0.0)
    parser.add_argument(
        "--min-simulation-time",
        type=float,
        default=50.0,
        help=("Exclude only grade-0/basic-intact cases whose actual "
              "simulation_time_s is below this cutoff; keep damaged short runs."),
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.20)
    parser.add_argument("--val-size", type=float, default=0.20)
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--skip-leave-facility-out", action="store_true")
    parser.add_argument("--skip-threshold-heatmaps", action="store_true")
    parser.add_argument("--scan-min-flux", type=float, default=100.0)
    parser.add_argument("--scan-max-flux", type=float, default=20000.0)
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

    df = load_experimental_dataset(
        args.cases_dir,
        min_completion=args.min_completion,
        min_simulation_time_s=args.min_simulation_time,
    )
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
    final_test_accuracy = float(final_metrics["grade_accuracy"])
    if final_test_accuracy < MIN_ACCEPTABLE_GRADE_ACCURACY:
        raise RuntimeError(
            "Independent-test grade accuracy is "
            f"{final_test_accuracy:.4f}, below required {MIN_ACCEPTABLE_GRADE_ACCURACY:.2f}."
        )

    final_model = clone(candidate_templates[best_name])
    X_all, y_all = _arrays(df)
    final_model.fit(X_all, y_all)

    by_facility = _evaluate_by_facility(final_eval_model, test_df)
    leave_facility_out = None
    if args.skip_leave_facility_out:
        leave_facility_out = {"skipped": "disabled by --skip-leave-facility-out"}
    else:
        leave_facility_out = _leave_facility_out(clone(candidate_templates[best_name]), df)

    facility_index_map = {
        str(name): int(index)
        for name, index in df.groupby("facility_name")["facility_index"].first().items()
    }
    facility_onehot_columns = tuple(df.attrs.get("facility_onehot_columns", ()))
    facility_alias_map = dict(df.attrs.get("facility_alias_map", {}))
    best_cv = cv_reports[best_name]

    cv_true_grade = np.asarray(best_cv["true_grade"], dtype=int)
    cv_predicted_grade = np.asarray(best_cv["predicted_grade"], dtype=int)
    facility_validation_accuracy = {
        str(facility): float(np.mean(cv_predicted_grade[mask] == cv_true_grade[mask]))
        for facility in sorted(df["facility_name"].unique())
        if np.any(mask := (df["facility_name"].to_numpy() == facility))
    }
    reference_fds = facility_first_fds(Path(args.cases_dir))
    facility_feature_profiles = {
        facility: parse_fds_features(path)
        for facility, path in reference_fds.items()
        if facility in facility_index_map
    }
    observed_case_dk: dict[tuple[str, float, float, float, float, float], float] = {}
    for row in df[["facility_name", "case_name", "Dk"]].itertuples(index=False):
        case = parse_case_name(row.case_name)
        key = (
            str(row.facility_name),
            round(float(case.heat_flux_kw_m2), 6),
            round(float(case.heat_azimuth_deg) % 360.0, 6),
            round(float(case.heat_elevation_deg), 6),
            round(float(case.radiation_duration_ms), 6),
            round(float(case.case_t_end_s), 6),
        )
        observed_case_dk[key] = float(row.Dk)
    artifact = {
        "model": final_model,
        "model_name": best_name,
        "feature_columns": list(COMPACT_EXPERIMENT_FEATURE_COLUMNS) + list(facility_onehot_columns),
        "dk_thresholds": DK_THRESHOLDS,
        "dk_grade_names": DK_GRADE_NAMES,
        "facility_index_map": facility_index_map,
        "facility_onehot_columns": list(facility_onehot_columns),
        "facility_alias_map": facility_alias_map,
        "facility_classifications": {
            str(name): FACILITY_CLASSIFICATION_ZH.get(str(name), str(name))
            for name in sorted(df["facility_name"].unique())
        },
        "facility_feature_profiles": facility_feature_profiles,
        "observed_case_dk": observed_case_dk,
        "validation_grade_accuracy": float(best_cv["metrics"]["grade_accuracy"]),
        "facility_validation_accuracy": facility_validation_accuracy,
        "min_completion": args.min_completion,
        "min_simulation_time_s": args.min_simulation_time,
    }
    model_path = CKPT_DIR / "experimental_dk_regressor.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(artifact, f)

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

    all_feature_names = tuple(COMPACT_EXPERIMENT_FEATURE_COLUMNS) + facility_onehot_columns
    feature_importance = _feature_importance(
        final_model, X_all, y_all, args.seed, all_feature_names
    )
    engineering_feature_importance = _engineering_feature_importance(feature_importance)
    heat_flux_response_path = FIGURE_DIR / "heat_flux_response_observed.png"
    cv_scatter_path = FIGURE_DIR / "cv_predicted_vs_observed.png"
    cv_confusion_path = FIGURE_DIR / "cv_confusion_matrix.png"
    model_schematic_path = FIGURE_DIR / "model_schematic.png"
    feature_importance_path = FIGURE_DIR / "feature_importance.png"
    extra_trees_architecture_path = FIGURE_DIR / "extra_trees_architecture.png"
    _plot_heat_flux_response(df, heat_flux_response_path)
    _plot_predicted_vs_observed(y_all, best_cv["predictions"], cv_scatter_path)
    _plot_confusion_matrix(best_cv["confusion_matrix"], cv_confusion_path)
    final_params = final_model.get_params(deep=True)
    schematic_tree_count = final_params.get(
        "regressor__n_estimators", final_params.get("n_estimators")
    )
    _plot_model_schematic(
        model_schematic_path,
        best_name,
        int(schematic_tree_count) if schematic_tree_count is not None else None,
    )
    _plot_model_schematic(
        FIGURE_DIR / "experimental_model_schematic.png",
        best_name,
        int(schematic_tree_count) if schematic_tree_count is not None else None,
    )
    _plot_feature_importance(engineering_feature_importance, feature_importance_path)
    _plot_extra_trees_architecture(
        extra_trees_architecture_path,
        int(schematic_tree_count) if schematic_tree_count is not None else 75,
        len(all_feature_names),
    )

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
            Path(args.cases_dir),
            facility_index_map,
            facility_onehot_columns,
            FIGURE_DIR,
            max_flux=args.scan_max_flux,
            min_flux=args.scan_min_flux,
            flux_points=args.scan_flux_points,
            azimuth_step=args.threshold_azimuth_step,
            elevation_step=args.threshold_elevation_step,
            max_facilities=max_facilities,
        )
    pd.DataFrame(threshold_rows).to_csv(threshold_table_path, index=False)
    censoring_counts = (
        pd.Series([row["censoring_status"] for row in threshold_rows], dtype="object")
        .value_counts()
        .to_dict()
    )
    fully_censored_facilities = sorted(
        {
            str(row["facility_name"])
            for row in threshold_rows
            if row["censoring_status"] == "all_right_censored"
        }
    )
    no_observed_damage_facilities = sorted(
        str(name)
        for name, value in df.groupby("facility_name")["Dk"].max().items()
        if float(value) < DK_THRESHOLDS[0]
    )
    expected_threshold_figure_count = int(df["facility_name"].nunique()) - len(
        no_observed_damage_facilities
    )

    model_params_path = OUTPUT_DIR / "experimental_model_parameters.json"
    with open(model_params_path, "w", encoding="utf-8") as f:
        json.dump(_params_json_safe(final_model.get_params(deep=True)), f, ensure_ascii=False, indent=2)

    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "cases_dir": str(args.cases_dir),
        "dataset_path": str(dataset_path),
        "model_path": str(model_path),
        "cv_predictions_path": str(cv_predictions_path),
        "feature_columns": list(COMPACT_EXPERIMENT_FEATURE_COLUMNS) + list(facility_onehot_columns),
        "dk_thresholds": list(DK_THRESHOLDS),
        "dk_grade_names": list(DK_GRADE_NAMES),
        "model_parameters_path": str(model_params_path),
        "min_completion": args.min_completion,
        "min_simulation_time_s": args.min_simulation_time,
        "data_quality": {
            "source_case_count": int(df.attrs.get("source_case_count", len(df))),
            "excluded_short_run_count": int(df.attrs.get("excluded_short_run_count", 0)),
            "actual_runtime_rule": (
                f"exclude only simulation_time_s < {args.min_simulation_time:g} "
                "and damage grade = 基本完好"
            ),
        },
        "cv_folds": int(args.cv_folds),
        "row_counts": {
            "all": int(len(df)),
            "train": int(len(train_df)),
            "val": int(len(val_df)),
            "test": int(len(test_df)),
        },
        "facility_index_map": facility_index_map,
        "facility_onehot_columns": list(facility_onehot_columns),
        "facility_alias_map": facility_alias_map,
        "facility_counts": df["facility_name"].value_counts().sort_index().to_dict(),
        "facility_classifications": {
            str(name): FACILITY_CLASSIFICATION_ZH.get(str(name), str(name))
            for name in sorted(df["facility_name"].unique())
        },
        "grade_counts": df["dk_grade_name"].value_counts().to_dict(),
        "observed_resistant_facilities": _observed_resistance_rows(df),
        "run_status": {"active_fds_cases": _active_fds_cases()},
        "candidate_models": model_reports,
        "best_model": best_name,
        "model_parameters": _params_json_safe(final_model.get_params(deep=True)),
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
        # Keep the user-facing/top list engineering-only. The complete raw
        # model importance (including facility controls) remains available
        # under an explicitly audit-oriented key.
        "top_feature_importance": engineering_feature_importance,
        "feature_importance_all": feature_importance,
        "engineering_feature_importance": engineering_feature_importance,
        "figures": {
            "heat_flux_response": str(heat_flux_response_path),
            "cv_predicted_vs_observed": str(cv_scatter_path),
            "cv_confusion_matrix": str(cv_confusion_path),
            "model_schematic": str(model_schematic_path),
            "extra_trees_architecture": str(extra_trees_architecture_path),
            "feature_importance": str(feature_importance_path),
        },
        "threshold_scan": {
            "table_path": str(threshold_table_path),
            "scan_min_flux": float(args.scan_min_flux),
            "scan_max_flux": float(args.scan_max_flux),
            "scan_flux_points": int(args.scan_flux_points),
            "azimuth_step": float(args.threshold_azimuth_step),
            "elevation_step": float(args.threshold_elevation_step),
            "summary_rows": threshold_rows,
            "figure_paths": threshold_figure_paths,
            "facility_count": int(len(threshold_figure_paths)),
            "expected_facility_count": expected_threshold_figure_count,
            "total_facility_count": int(df["facility_name"].nunique()),
            "plot_omitted_no_observed_damage": no_observed_damage_facilities,
            "is_complete": bool(
                len(threshold_figure_paths) == expected_threshold_figure_count
                and not args.skip_threshold_heatmaps
            ),
            "censoring_counts": censoring_counts,
            "facilities_with_fully_censored_cells": fully_censored_facilities,
        },
        "presentation_path": str(OUTPUT_DIR / "experimental_presentation.html"),
    }
    summary_path = OUTPUT_DIR / "experimental_train_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(summary), f, ensure_ascii=False, indent=2)

    # Generate zero-Dk facility diagnostic report (if any).
    zero_dk_diagnostics: list = []
    facility_summaries_for_diag = list(iter_facilities(Path(args.cases_dir)))
    zero_dk_summaries = find_zero_dk_facilities(facility_summaries_for_diag)
    for facility_summary in zero_dk_summaries:
        if facility_summary.fds_path is None:
            continue
        try:
            fds_features_for_diag = parse_fds_features(facility_summary.fds_path)
        except Exception as exc:
            LOG.warning(
                "diagnostic: failed to parse FDS for %s (%s)",
                facility_summary.facility_name,
                exc,
            )
            continue
        diag = build_facility_diagnostic(
            facility_name=facility_summary.facility_name,
            case_count=len(facility_summary.cases),
            max_observed_dk=facility_summary.max_dk,
            facility_root=(
                Path(args.cases_dir) / facility_summary.facility_name / "damage_results"
            ),
            fds_features=fds_features_for_diag,
        )
        zero_dk_diagnostics.append(diag)
    diagnostic_path = OUTPUT_DIR / "zero_dk_facility_diagnostic.md"
    if zero_dk_diagnostics:
        write_zero_dk_report(zero_dk_diagnostics, diagnostic_path)
        print(f"[train_experimental] zero-Dk diagnostic saved to {diagnostic_path}")

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
            "ExtraTrees双任务架构图": str(extra_trees_architecture_path),
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
