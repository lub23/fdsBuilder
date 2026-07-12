"""Inference helper for experimental FDS/CSV trained Dk regressors."""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from ..data.experimental import (
    DK_GRADE_NAMES,
    DK_THRESHOLDS,
    EXPERIMENT_FEATURE_COLUMNS,
    case_condition_features,
    compact_experimental_features,
    directional_case_features,
    dk_to_grade,
    grade_name,
    parse_case_name,
    parse_fds_features,
)


DEFAULT_EXPERIMENTAL_MODEL = (
    Path(__file__).resolve().parents[2] / "checkpoints" / "experimental_dk_regressor.pkl"
)


@dataclass(frozen=True)
class DkPrediction:
    case_name: str
    fds_file: str
    predicted_dk: float
    damage_grade: int
    damage_grade_name: str


class ExperimentalDkPredictor:
    def __init__(
        self,
        model: Any,
        feature_columns: tuple[str, ...] = EXPERIMENT_FEATURE_COLUMNS,
        dk_thresholds: tuple[float, float, float] = DK_THRESHOLDS,
        dk_grade_names: tuple[str, str, str, str] = DK_GRADE_NAMES,
        facility_index_map: Mapping[str, int] | None = None,
        facility_onehot_columns: tuple[str, ...] = (),
    ) -> None:
        self.model = model
        self.feature_columns = tuple(feature_columns)
        self.dk_thresholds = tuple(dk_thresholds)
        self.dk_grade_names = tuple(dk_grade_names)
        self.facility_index_map = dict(facility_index_map or {})
        self.facility_onehot_columns = tuple(facility_onehot_columns)
        self._known_facilities = {col.replace("facility_oh_", "", 1) for col in self.facility_onehot_columns}

    def _facility_onehot(self, facility_name: str) -> dict[str, float]:
        target_col = "facility_oh_" + str(facility_name).replace("-", "_")
        return {col: 1.0 if col == target_col else 0.0 for col in self.facility_onehot_columns}

    def _feature_row(self, fds_path: Path, case_name: str) -> np.ndarray:
        case = parse_case_name(case_name)
        fds_features = parse_fds_features(fds_path)
        features = {
            **fds_features,
            **case_condition_features(case),
            **directional_case_features(fds_features, case),
            "facility_index": float(self.facility_index_map.get(case.facility, -1)),
        }
        features = {**features, **compact_experimental_features(features)}
        onehot = self._facility_onehot(case.facility)
        for column, value in onehot.items():
            features[column] = value
        row = [float(features.get(column, 0.0)) for column in self.feature_columns]
        return np.asarray(row, dtype=float).reshape(1, -1)

    def predict(self, fds_path: Path, case_name: str) -> DkPrediction:
        fds_path = Path(fds_path)
        X = self._feature_row(fds_path, case_name)
        predicted_dk = float(np.clip(self.model.predict(X)[0], 0.0, 1.0))
        grade = dk_to_grade(predicted_dk, self.dk_thresholds)
        grade_label = (
            self.dk_grade_names[grade]
            if 0 <= grade < len(self.dk_grade_names)
            else grade_name(grade)
        )
        return DkPrediction(
            case_name=case_name,
            fds_file=fds_path.name,
            predicted_dk=predicted_dk,
            damage_grade=grade,
            damage_grade_name=grade_label,
        )


def load_experimental_dk_predictor(path: Path | None = None) -> ExperimentalDkPredictor:
    model_path = Path(path) if path else DEFAULT_EXPERIMENTAL_MODEL
    with open(model_path, "rb") as f:
        artifact = pickle.load(f)
    return ExperimentalDkPredictor(
        model=artifact["model"],
        feature_columns=tuple(artifact.get("feature_columns", EXPERIMENT_FEATURE_COLUMNS)),
        dk_thresholds=tuple(artifact.get("dk_thresholds", DK_THRESHOLDS)),
        dk_grade_names=tuple(artifact.get("dk_grade_names", DK_GRADE_NAMES)),
        facility_index_map=artifact.get("facility_index_map", {}),
        facility_onehot_columns=tuple(artifact.get("facility_onehot_columns", ())),
    )
