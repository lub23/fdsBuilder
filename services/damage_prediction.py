"""UI adapter for the FDS-trained experimental damage predictor.

The current surrogate is facility-level. It resolves the UI's equivalent-model
scale to the exact facility identity used during training, reuses an
authoritative result for an already simulated condition, and otherwise applies
the model with the reference feature profile persisted at training time.
"""

from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Collection

from generators.fds_generator import FDSGenerator
from models.facility import FacilityManager, SCALE_KEYS
from services.fds_naming import sanitize_chid, simulation_suffix


class UnsupportedDamageFacility(ValueError):
    """Raised when a UI model cannot be mapped to a trained facility."""


@dataclass(frozen=True)
class DamagePredictionContext:
    """Prediction plus the facility identity selected for model inference."""

    prediction: Any
    facility_name: str
    ui_facility_name: str
    scale_name: str | None


# Config files opened from outside the facility picker can carry their old
# human-readable group name.  Normalise the known names before matching the
# artifact's facility identities.
_UI_FACILITY_ALIASES = {
    "aerospace_facilities": "aerospace",
    "airport_hangar": "airport_hangar",
    "alcoa_warrick_operations": "alcoa",
    "frymaster_corporation": "frymaster_corporation",
    "gleason_cutting_tools_corporation": "gleason_cutting_tools_corporation",
    "harbison_fischer": "harbison_fischer",
    "machinery_manufacturing": "machinery_manufacturing",
    "materion_electronic_materials_buffalo": "materion_buffalo",
    "materion_electronic_materials_newton": "materion_newton",
    "metallurgical_facilities": "metallurgical_facilities",
    "warrick_power_plant": "warrick_power_plant",
}


def _normalised_name(value: str) -> str:
    return sanitize_chid(value).strip("_").lower()


def _scale_distance(model: Any, facility_name: str, scale_idx: int) -> float:
    """Return a dimension-based distance to one configured equivalent scale."""
    manager = FacilityManager()
    actual_by_name = {
        str(getattr(building, "name", "")): building
        for building in (getattr(model, "buildings", None) or [])
    }
    distances: list[float] = []
    for building_name in manager.list_buildings(facility_name):
        actual = actual_by_name.get(building_name)
        if actual is None:
            continue
        expected = manager.params_for_scale(facility_name, building_name, scale_idx)
        boundary = list(getattr(actual, "boundary", ()) or ())
        actual_dims = (
            float(boundary[1]) if len(boundary) > 1 else 0.0,
            float(boundary[3]) if len(boundary) > 3 else 0.0,
            float(getattr(actual, "height", 0.0)),
            float(max(len(getattr(actual, "stories", ()) or ()), 1)),
        )
        expected_dims = (
            float(expected["length"]),
            float(expected["width"]),
            float(expected["height"]),
            float(expected["stories"]),
        )
        for actual_value, expected_value in zip(actual_dims, expected_dims):
            if actual_value > 0 and expected_value > 0:
                distances.append(abs(math.log(actual_value / expected_value)))
    return sum(distances) / len(distances) if distances else float("inf")


def resolve_damage_facility(
    model: Any,
    known_facilities: Collection[str],
) -> tuple[str, str | None]:
    """Map a UI BuildingGroup to a facility identity in the trained artifact.

    Specialized facilities map directly.  Equivalent facilities have three
    separately trained identities (``*_small/medium/large``), so the closest
    configured scale is selected from the current building dimensions.
    Unknown/custom facilities are rejected rather than silently using an
    all-zero facility one-hot vector, which would be out-of-distribution.
    """
    known = set(known_facilities)
    raw_name = str(getattr(model, "name", "") or "")
    ui_name = _normalised_name(raw_name)
    base_name = _UI_FACILITY_ALIASES.get(ui_name, ui_name)

    if base_name in known:
        return base_name, None

    candidates = [
        (index, scale, f"{base_name}_{scale}")
        for index, scale in SCALE_KEYS.items()
        if f"{base_name}_{scale}" in known
    ]
    if candidates:
        distances = [
            (_scale_distance(model, base_name, index), scale, facility)
            for index, scale, facility in candidates
        ]
        distance, scale, facility = min(distances, key=lambda item: item[0])
        if math.isfinite(distance):
            return facility, scale

    raise UnsupportedDamageFacility(
        f"设施“{raw_name or '未命名设施'}”不在当前代理模型的训练设施中。"
        "请从左侧设施库生成完整设施后再预测。"
    )


def predict_current_model(model: Any, predictor: Any) -> DamagePredictionContext:
    """Generate the current condition and run one facility-level prediction."""
    known = set(getattr(predictor, "facility_index_map", {}) or {})
    known.update(getattr(predictor, "_known_facilities", set()) or set())
    facility_name, scale_name = resolve_damage_facility(model, known)
    case_name = f"{facility_name}_{simulation_suffix(model)}"
    fds_text = FDSGenerator(model).generate()

    # The temporary FDS remains the compatibility input for old artifacts and
    # unknown profiles. New artifacts use their persisted training reference
    # profile, because a generated FDS contains an azimuth-dependent radiation
    # boundary that must not be mistaken for a physical building opening.
    with tempfile.TemporaryDirectory(prefix="fdsbuilder_damage_") as tmp_dir:
        fds_path = Path(tmp_dir) / f"{case_name}.fds"
        fds_path.write_text(fds_text, encoding="utf-8")
        prediction = predictor.predict(fds_path, case_name)

    return DamagePredictionContext(
        prediction=prediction,
        facility_name=facility_name,
        ui_facility_name=str(getattr(model, "name", "") or ""),
        scale_name=scale_name,
    )
