"""Regression training helpers for experimental Dk surrogate models."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

from ..data.experimental import DK_THRESHOLDS, dk_to_grade


def logit_transform(y: np.ndarray) -> np.ndarray:
    eps = 1e-4
    clipped = np.clip(np.asarray(y, dtype=float), eps, 1.0 - eps)
    return np.log(clipped / (1.0 - clipped))


def inverse_logit_transform(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z, dtype=float)
    return 1.0 / (1.0 + np.exp(-z))


def clipped_dk_predictions(model: Any, X: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(model.predict(X), dtype=float), 0.0, 1.0)


def evaluate_dk_regressor(
    model: Any,
    X: np.ndarray,
    y: np.ndarray,
    thresholds: tuple[float, float, float] = DK_THRESHOLDS,
) -> Dict[str, Any]:
    y_true = np.asarray(y, dtype=float)
    y_pred = clipped_dk_predictions(model, X)
    true_grade = np.array([dk_to_grade(v, thresholds) for v in y_true], dtype=int)
    pred_grade = np.array([dk_to_grade(v, thresholds) for v in y_pred], dtype=int)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(mean_squared_error(y_true, y_pred) ** 0.5),
        "r2": float(r2_score(y_true, y_pred)) if len(np.unique(y_true)) > 1 else 0.0,
        "max_abs_error": float(np.max(np.abs(y_true - y_pred))) if len(y_true) else 0.0,
        "grade_accuracy": float(accuracy_score(true_grade, pred_grade)),
        "grade_macro_f1": float(f1_score(true_grade, pred_grade, average="macro", zero_division=0)),
        "grade_weighted_f1": float(
            f1_score(true_grade, pred_grade, average="weighted", zero_division=0)
        ),
        "confusion_matrix": confusion_matrix(true_grade, pred_grade, labels=[0, 1, 2, 3]),
        "predictions": y_pred,
        "true_grade": true_grade,
        "predicted_grade": pred_grade,
    }


def compact_metrics(metrics: Dict[str, Any]) -> Dict[str, float]:
    return {
        "mae": float(metrics["mae"]),
        "rmse": float(metrics["rmse"]),
        "r2": float(metrics["r2"]),
        "max_abs_error": float(metrics["max_abs_error"]),
        "grade_accuracy": float(metrics["grade_accuracy"]),
        "grade_macro_f1": float(metrics["grade_macro_f1"]),
        "grade_weighted_f1": float(metrics["grade_weighted_f1"]),
    }
