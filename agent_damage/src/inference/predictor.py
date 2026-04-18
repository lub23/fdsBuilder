"""Ensemble predictor: two-stage inference across all buildings in a facility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

import numpy as np
import torch
from sklearn.preprocessing import StandardScaler

from ..processing.building import Building
from ..processing.enums import DamageLevel
from ..processing.facility import Facility
from ..processing.heat_source import HeatSourceParams
from ..processing.occlusion import occluding_higher_count
from ..training.ensemble import WeightedEnsemble, prediction_uncertainty
from .results import BuildingDamageResult, FacilityDamageResult


def _predict_proba_single(model: Any, x: np.ndarray) -> np.ndarray:
    """Model-agnostic proba for a single (1, 23) input array."""
    if isinstance(model, torch.nn.Module):
        device = next(model.parameters()).device
        model.eval()
        with torch.no_grad():
            logits = model(torch.from_numpy(x).float().to(device))
            return torch.softmax(logits, dim=1).cpu().numpy()
    return np.asarray(model.predict_proba(x))


@dataclass
class EnsemblePredictor:
    models: Dict[str, Any]
    weights: Dict[str, float]
    scaler: StandardScaler
    ensemble: WeightedEnsemble = field(init=False)

    def __post_init__(self) -> None:
        if set(self.models) != set(self.weights):
            raise ValueError(
                f"Model keys {set(self.models)} do not match weight keys {set(self.weights)}"
            )
        self.ensemble = WeightedEnsemble(weights=self.weights)

    def _build_features(
        self, facility: Facility, building: Building, heat_source: HeatSourceParams
    ) -> np.ndarray:
        occ = occluding_higher_count(facility, building, heat_source.azimuth)
        row = (
            building.to_feature_vector(facility_type_index=facility.facility_type.index)
            + heat_source.to_feature_vector()
            + [float(occ)]
        )
        x_raw = np.asarray(row, dtype=np.float32).reshape(1, -1)
        return self.scaler.transform(x_raw).astype(np.float32)

    def predict_building(
        self, facility: Facility, building: Building, heat_source: HeatSourceParams
    ) -> BuildingDamageResult:
        x = self._build_features(facility, building, heat_source)
        per_model = {name: _predict_proba_single(m, x) for name, m in self.models.items()}
        fused = self.ensemble.fuse(per_model)[0]  # (n_classes,)
        stack = np.stack(list(per_model.values()), axis=0)  # (n_models, 1, 3)
        unc = float(prediction_uncertainty(stack)[0])
        cls = int(np.argmax(fused))
        return BuildingDamageResult(
            building=building,
            damage_level=DamageLevel.from_numeric(cls),
            probability=float(fused[cls]),
            uncertainty=unc,
        )

    def predict_facility(
        self, facility: Facility, heat_source: HeatSourceParams
    ) -> FacilityDamageResult:
        results = [
            self.predict_building(facility, b, heat_source) for b in facility.buildings
        ]
        return FacilityDamageResult(
            facility=facility, heat_source=heat_source, building_results=results
        )
