"""Regression training helpers for experimental Dk surrogate models."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

from ..data.experimental import DK_THRESHOLDS, dk_to_grade


class GradeConstrainedRegressor(RegressorMixin, BaseEstimator):
    """Continuous Dk regressor constrained by an auxiliary grade classifier.

    The continuous estimator preserves Dk magnitude for plots and engineering
    diagnostics.  The classifier is trained on the same folds to optimise the
    four user-facing damage grades directly.  Whenever the two heads disagree,
    the returned Dk is clipped into the interval selected by the classifier;
    therefore the public Dk thresholds and the reported grade can never
    contradict each other.
    """

    def __init__(
        self,
        regressor: Any,
        classifier: Any,
        thresholds: tuple[float, float, float] = DK_THRESHOLDS,
    ) -> None:
        self.regressor = regressor
        self.classifier = classifier
        self.thresholds = thresholds

    def fit(self, X: np.ndarray, y: np.ndarray) -> "GradeConstrainedRegressor":
        y_array = np.asarray(y, dtype=float)
        grades = np.asarray(
            [dk_to_grade(value, tuple(self.thresholds)) for value in y_array],
            dtype=int,
        )
        self.regressor_ = clone(self.regressor).fit(X, y_array)
        self.classifier_ = clone(self.classifier).fit(X, grades)
        self.n_features_in_ = int(np.asarray(X).shape[1])
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        continuous = np.clip(
            np.asarray(self.regressor_.predict(X), dtype=float), 0.0, 1.0
        )
        grades = np.asarray(self.classifier_.predict(X), dtype=int)
        thresholds = np.asarray(tuple(self.thresholds), dtype=float)
        lower = np.concatenate(([0.0], thresholds))
        # dk_to_grade uses inclusive lower bounds and exclusive upper bounds.
        upper = np.concatenate((thresholds, [1.0]))
        upper = np.nextafter(upper, -np.inf)
        upper[-1] = 1.0
        return np.clip(continuous, lower[grades], upper[grades])

    @property
    def feature_importances_(self) -> np.ndarray:
        """Average both fitted heads' tree importances for reporting."""
        reg = np.asarray(self.regressor_.feature_importances_, dtype=float)
        clf = np.asarray(self.classifier_.feature_importances_, dtype=float)
        return (reg + clf) / 2.0


class MultiTargetGradeConstrainedRegressor(RegressorMixin, BaseEstimator):
    """Multi-output Dk regressor with per-target grade constraints.

    Fits one ExtraTrees regressor and one ExtraTrees classifier; both heads are
    multi-output so the same forest predicts every sub-target column (one per
    building of an equivalent facility).  Each predicted sub-target Dk is
    clipped into the interval selected by its own grade classifier, so the four
    public thresholds and every reported grade stay consistent per column.
    """

    def __init__(
        self,
        regressor: Any,
        classifier: Any,
        thresholds: tuple[float, float, float] = DK_THRESHOLDS,
    ) -> None:
        self.regressor = regressor
        self.classifier = classifier
        self.thresholds = thresholds

    def fit(self, X: np.ndarray, y: np.ndarray) -> "MultiTargetGradeConstrainedRegressor":
        y_array = np.asarray(y, dtype=float)
        if y_array.ndim == 1:
            y_array = y_array.reshape(-1, 1)
        grades = np.asarray(
            [[dk_to_grade(value, tuple(self.thresholds)) for value in row] for row in y_array],
            dtype=int,
        )
        self.regressor_ = clone(self.regressor).fit(X, y_array)
        self.classifier_ = clone(self.classifier).fit(X, grades)
        self.n_features_in_ = int(np.asarray(X).shape[1])
        self.n_targets_ = int(y_array.shape[1])
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        continuous = np.clip(
            np.asarray(self.regressor_.predict(X), dtype=float), 0.0, 1.0
        )
        if continuous.ndim == 1:
            continuous = continuous.reshape(-1, 1)
        grades = np.asarray(self.classifier_.predict(X), dtype=int)
        if grades.ndim == 1:
            grades = grades.reshape(-1, 1)
        thresholds = np.asarray(tuple(self.thresholds), dtype=float)
        lower = np.concatenate(([0.0], thresholds))
        upper = np.concatenate((thresholds, [1.0]))
        upper = np.nextafter(upper, -np.inf)
        upper[-1] = 1.0
        clipped = np.empty_like(continuous, dtype=float)
        for target in range(continuous.shape[1]):
            clipped[:, target] = np.clip(
                continuous[:, target],
                lower[grades[:, target]],
                upper[grades[:, target]],
            )
        return clipped

    def predict_grades(self, X: np.ndarray) -> np.ndarray:
        grades = np.asarray(self.classifier_.predict(X), dtype=int)
        if grades.ndim == 1:
            grades = grades.reshape(-1, 1)
        return grades

    @property
    def feature_importances_(self) -> np.ndarray:
        """Average both fitted heads' tree importances for reporting."""
        reg = np.asarray(self.regressor_.feature_importances_, dtype=float)
        clf = np.asarray(self.classifier_.feature_importances_, dtype=float)
        return (reg + clf) / 2.0


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
