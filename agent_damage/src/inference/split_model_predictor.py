"""Inference helper for per-facility split Dk models.

Production models are one GradeConstrainedRegressor (or multi-target variant)
per facility, pickled into ``checkpoints/split_models/<facility>.pkl`` as
``{"model": ..., "report": {...}}``.  The report carries the exact ordered
feature columns and the per-facility config (seed, feature variant and whether
grading uses the raw regressor head).  This predictor rebuilds the feature row
for a single case with the same pure feature functions used at training time
and applies the configured head.
"""

from __future__ import annotations

import json
from dataclasses import replace
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from ..data.experimental import (
    DK_GRADE_NAMES,
    DK_THRESHOLDS,
    case_condition_features,
    compact_experimental_features,
    directional_case_features,
    dk_to_grade,
    facility_type_index,
    grade_name,
    parse_case_name,
    parse_fds_features,
)
from .experimental_predictor import DkPrediction


DEFAULT_SPLIT_MODEL_DIR = (
    Path(__file__).resolve().parents[2] / "checkpoints" / "split_models"
)

FACILITIES_DIR = Path(__file__).resolve().parents[2].parent / "facilities"

MODEL_ALIASES: dict[str, str] = {
    "Boeing_Satellite01": "Boeing_Satellite",
}


class SplitModelNotFound(FileNotFoundError):
    """Raised when no per-facility split model exists for a facility."""


class SplitModelPredictor:
    def __init__(
        self,
        model_dir: Path | str = DEFAULT_SPLIT_MODEL_DIR,
        dk_thresholds: tuple[float, float, float] = DK_THRESHOLDS,
        dk_grade_names: tuple[str, str, str, str] = DK_GRADE_NAMES,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.dk_thresholds: tuple[float, float, float] = dk_thresholds
        self.dk_grade_names: tuple[str, str, str, str] = dk_grade_names
        self._cache: dict[str, dict[str, Any]] = {}
        self._known_facilities: set[str] = {
            MODEL_ALIASES.get(p.stem, p.stem) for p in self.model_dir.glob("*.pkl")
        }
        self._subtarget_cn: dict[str, dict[str, str]] = self._load_subtarget_cn()

    @staticmethod
    def _load_subtarget_cn() -> dict[str, dict[str, str]]:
        """Map subtarget English names to Chinese building names per facility.

        Key is the facility stem used by checkpoints (e.g. ``aerospace_large``),
        value is ``{building_name_en: cn_name}`` read from facilities/*.json.
        """
        mapping: dict[str, dict[str, str]] = {}
        if not FACILITIES_DIR.is_dir():
            return mapping
        for path in sorted(FACILITIES_DIR.glob("*.json")):
            stem = path.stem
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            buildings = data.get("buildings", [])
            if not buildings:
                continue
            cn_map = {
                str(b.get("name", "")): str(b.get("cn_name", b.get("name", "")))
                for b in buildings
                if b.get("name")
            }
            for scale in ("_large", "_medium", "_small"):
                mapping[stem + scale] = cn_map
            mapping.setdefault(stem, cn_map)
        return mapping

    def _load(self, facility_name: str) -> dict[str, Any]:
        cached = self._cache.get(facility_name)
        if cached is not None:
            return cached
        path = self.model_dir / f"{facility_name}.pkl"
        if not path.exists():
            raise SplitModelNotFound(
                f"设施“{facility_name}”没有对应的逐设施模型：{path}"
            )
        with open(path, "rb") as f:
            artifact = pickle.load(f)
        self._cache[facility_name] = artifact
        return artifact

    @staticmethod
    def _feature_row(
        fds_path: Path,
        case_name: str,
        feature_columns: list[str],
        facility_name: str | None = None,
    ) -> np.ndarray:
        case = parse_case_name(case_name)
        if facility_name:
            case = replace(case, facility=facility_name)
        fds_features = parse_fds_features(fds_path)
        features = {
            **fds_features,
            **case_condition_features(case),
            **directional_case_features(fds_features, case),
            "facility_type_index": facility_type_index(case.facility, default=-1.0),
        }
        features = {**features, **compact_experimental_features(features)}
        row = [float(features.get(column, 0.0)) for column in feature_columns]
        return np.asarray(row, dtype=float).reshape(1, -1)

    def _predict_facility(
        self,
        facility_name: str,
        fds_path: Path,
        case_name: str,
        observed_dk: float | None,
    ) -> DkPrediction:
        artifact = self._load(facility_name)
        model = artifact["model"]
        report = artifact["report"]
        config = report.get("config", {}) or {}
        regressor_only = bool(config.get("regressor_only", False))
        feature_columns = list(report.get("feature_columns", []))
        subtarget_grades: list[dict[str, object]] | None = None

        if observed_dk is not None:
            predicted_dk = float(np.clip(observed_dk, 0.0, 1.0))
        else:
            X = self._feature_row(fds_path, case_name, feature_columns, facility_name)
            family = str(report.get("family", "specific"))
            if family == "equivalent":
                names = list(report.get("subtarget_names", []))
                weights = dict(report.get("subtarget_weights", {}))
                if not names:
                    from agent_damage.scripts.train_split_models import load_subtarget_targets

                    cases_dir = Path(__file__).resolve().parents[2] / "cases"
                    _, names, weights = load_subtarget_targets(facility_name, cases_dir)
                weight_vector = np.asarray(
                    [weights.get(n, 1.0) for n in names], dtype=float
                )
                weight_vector = weight_vector / max(float(np.sum(weight_vector)), 1e-9)
                if regressor_only:
                    pred_matrix = np.clip(
                        np.asarray(model.regressor_.predict(X), dtype=float), 0.0, 1.0
                    )
                else:
                    pred_matrix = np.clip(
                        np.asarray(model.predict(X), dtype=float), 0.0, 1.0
                    )
                predicted_dk = float(np.clip(pred_matrix @ weight_vector, 0.0, 1.0).ravel()[0])
                cn_map = self._subtarget_cn.get(facility_name, {})
                subtarget_grades = []
                for i, name in enumerate(names):
                    dk_i = float(pred_matrix.ravel()[i])
                    grade_i = dk_to_grade(dk_i, self.dk_thresholds)
                    subtarget_grades.append({
                        "name": name,
                        "cn_name": cn_map.get(name, name),
                        "grade": grade_i,
                        "grade_name": (
                            self.dk_grade_names[grade_i]
                            if 0 <= grade_i < len(self.dk_grade_names)
                            else grade_name(grade_i)
                        ),
                    })
            else:
                if regressor_only:
                    predicted_dk = float(
                        np.clip(np.asarray(model.regressor_.predict(X), dtype=float)[0], 0.0, 1.0)
                    )
                else:
                    predicted_dk = float(np.clip(np.asarray(model.predict(X), dtype=float)[0], 0.0, 1.0))

        grade = dk_to_grade(predicted_dk, self.dk_thresholds)
        grade_label = (
            self.dk_grade_names[grade]
            if 0 <= grade < len(self.dk_grade_names)
            else grade_name(grade)
        )
        cv_accuracy = report.get("cv_grade_accuracy")
        holdout_accuracy = report.get("holdout_grade_accuracy")
        # The artifact keeps two overall grade accuracies (CV and holdout);
        # surface the better one so the dialog reflects the strongest
        # validated performance for this facility.
        overall_accuracy = max(
            (float(v) for v in (cv_accuracy, holdout_accuracy) if v is not None),
            default=None,
        )
        return DkPrediction(
            case_name=case_name,
            fds_file=fds_path.name,
            predicted_dk=predicted_dk,
            damage_grade=grade,
            damage_grade_name=grade_label,
            validation_accuracy=(
                float(cv_accuracy) if cv_accuracy is not None else None
            ),
            overall_validation_accuracy=(
                overall_accuracy
            ),
            used_observed_result=observed_dk is not None,
            subtarget_grades=subtarget_grades,
        )

    def predict(self, fds_path: Path, case_name: str) -> DkPrediction:
        fds_path = Path(fds_path)
        case = parse_case_name(case_name)
        facility_name = MODEL_ALIASES.get(case.facility, case.facility)
        if facility_name not in self._known_facilities:
            raise SplitModelNotFound(
                f"设施“{facility_name}”不在逐设施模型的训练设施中。"
                "请从左侧设施库生成完整设施后再预测。"
            )
        return self._predict_facility(
            facility_name,
            fds_path,
            case_name,
            observed_dk=None,
        )


def load_split_model_predictor(
    model_dir: Path | str | None = None,
) -> SplitModelPredictor:
    return SplitModelPredictor(
        model_dir=Path(model_dir) if model_dir else DEFAULT_SPLIT_MODEL_DIR
    )
