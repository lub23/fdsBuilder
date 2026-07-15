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
    facility_type_index,
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
    validation_accuracy: float | None = None
    overall_validation_accuracy: float | None = None
    used_observed_result: bool = False


class ExperimentalDkPredictor:
    def __init__(
        self,
        model: Any,
        feature_columns: tuple[str, ...] = EXPERIMENT_FEATURE_COLUMNS,
        dk_thresholds: tuple[float, float, float] = DK_THRESHOLDS,
        dk_grade_names: tuple[str, str, str, str] = DK_GRADE_NAMES,
        facility_index_map: Mapping[str, int] | None = None,
        facility_onehot_columns: tuple[str, ...] = (),
        facility_alias_map: Mapping[str, str] | None = None,
        facility_feature_profiles: Mapping[str, Mapping[str, float]] | None = None,
        observed_case_dk: Mapping[tuple[str, float, float, float, float, float], float] | None = None,
        validation_grade_accuracy: float | None = None,
        facility_validation_accuracy: Mapping[str, float] | None = None,
        model_name: str = "",
    ) -> None:
        self.model = model
        self.model_name = str(model_name)
        self.feature_columns = tuple(feature_columns)
        self.dk_thresholds = tuple(dk_thresholds)
        self.dk_grade_names = tuple(dk_grade_names)
        self.facility_index_map = dict(facility_index_map or {})
        self.facility_onehot_columns = tuple(facility_onehot_columns)
        self.facility_alias_map = dict(facility_alias_map or {})
        self.facility_feature_profiles = {
            str(name): dict(features)
            for name, features in (facility_feature_profiles or {}).items()
        }
        self.observed_case_dk = dict(observed_case_dk or {})
        self.validation_grade_accuracy = (
            float(validation_grade_accuracy)
            if validation_grade_accuracy is not None
            else None
        )
        self.facility_validation_accuracy = {
            str(name): float(value)
            for name, value in (facility_validation_accuracy or {}).items()
        }
        self._known_facilities = {col.replace("facility_oh_", "", 1) for col in self.facility_onehot_columns}

    def _facility_onehot(self, facility_name: str) -> dict[str, float]:
        target_col = "facility_oh_" + str(facility_name).replace("-", "_")
        return {col: 1.0 if col == target_col else 0.0 for col in self.facility_onehot_columns}

    def _canonical_facility(self, case_facility: str, fds_path: Path) -> str:
        if case_facility in self.facility_alias_map:
            return self.facility_alias_map[case_facility]
        # A cases/<facility>/<reference>.fds path is a reliable fallback for
        # artifacts produced before facility aliases were persisted.
        parent_name = fds_path.parent.name
        if parent_name in self.facility_index_map or parent_name in self._known_facilities:
            return parent_name
        return case_facility

    @staticmethod
    def _condition_key(
        facility_name: str,
        heat_flux: float,
        azimuth: float,
        elevation: float,
        duration_ms: float,
        t_end_s: float,
    ) -> tuple[str, float, float, float, float, float]:
        """Return a stable key shared by training artifacts and UI inference."""
        return (
            str(facility_name),
            round(float(heat_flux), 6),
            round(float(azimuth) % 360.0, 6),
            round(float(elevation), 6),
            round(float(duration_ms), 6),
            round(float(t_end_s), 6),
        )

    def _feature_row(
        self,
        fds_path: Path,
        case_name: str,
    ) -> np.ndarray:
        case = parse_case_name(case_name)
        facility_name = self._canonical_facility(case.facility, fds_path)
        # Training parses one fixed reference FDS per facility. A freshly
        # generated UI FDS also contains the azimuth-dependent radiation
        # boundary VENT, so parsing it directly changes apparent wall-opening
        # features and can turn an exact training condition into a different
        # feature row. Persisted reference profiles keep inference identical to
        # training; old artifacts continue to fall back to the supplied FDS.
        fds_features = self.facility_feature_profiles.get(facility_name)
        if fds_features is None:
            fds_features = parse_fds_features(fds_path)
        features = {
            **fds_features,
            **case_condition_features(case),
            **directional_case_features(fds_features, case),
            "facility_index": float(self.facility_index_map.get(facility_name, -1)),
            "facility_type_index": facility_type_index(facility_name, default=-1.0),
        }
        features = {**features, **compact_experimental_features(features)}
        onehot = self._facility_onehot(facility_name)
        for column, value in onehot.items():
            features[column] = value
        row = [float(features.get(column, 0.0)) for column in self.feature_columns]
        return np.asarray(row, dtype=float).reshape(1, -1)

    def predict(self, fds_path: Path, case_name: str) -> DkPrediction:
        fds_path = Path(fds_path)
        case = parse_case_name(case_name)
        facility_name = self._canonical_facility(case.facility, fds_path)
        lookup_key = self._condition_key(
            facility_name,
            case.heat_flux_kw_m2,
            case.heat_azimuth_deg,
            case.heat_elevation_deg,
            case.radiation_duration_ms,
            case.case_t_end_s,
        )
        observed_dk = self.observed_case_dk.get(lookup_key)
        used_observed_result = observed_dk is not None
        if used_observed_result:
            # A surrogate must not approximate a condition whose authoritative
            # simulation result is already in the artifact.
            predicted_dk = float(np.clip(observed_dk, 0.0, 1.0))
        else:
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
            validation_accuracy=self.facility_validation_accuracy.get(
                facility_name, self.validation_grade_accuracy
            ),
            overall_validation_accuracy=self.validation_grade_accuracy,
            used_observed_result=used_observed_result,
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
        facility_alias_map=artifact.get("facility_alias_map", {}),
        facility_feature_profiles=artifact.get("facility_feature_profiles", {}),
        observed_case_dk=artifact.get("observed_case_dk", {}),
        validation_grade_accuracy=artifact.get("validation_grade_accuracy"),
        facility_validation_accuracy=artifact.get("facility_validation_accuracy", {}),
        model_name=artifact.get("model_name", ""),
    )
