"""UI adapter for the FDS-trained experimental damage predictor.

The current surrogate is facility-level. It resolves the UI's equivalent-model
scale to the exact facility identity used during training, reuses an
authoritative result for an already simulated condition, and otherwise applies
the model with the reference feature profile persisted at training time.
"""

from __future__ import annotations

import math
import re
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

_TRAINED_FACILITY_ALIASES = {
    "Boeing_Satellite01": "Boeing_Satellite",
}


def _normalised_name(value: str) -> str:
    return sanitize_chid(value).strip("_").lower()


_CONDITION_SUFFIX_RE = re.compile(r"_q\d+_a\d+_e\d+_d\d+_t\d+$")


def default_cases_root() -> Path:
    """Root directory holding per-facility reference case FDS files."""
    return Path(__file__).resolve().parents[1] / "agent_damage" / "cases"


def reference_case_base_name(
    facility_name: str, cases_dir: Path | None = None
) -> str:
    """Return the CHID prefix of a trained facility's reference case FDS.

    Reference case files are named ``{base}_{condition_suffix}.fds`` where
    ``base`` is the facility prefix used in the rendered artifacts (e.g.
    ``hangar_ligen`` for the ``ligen`` code).  Falls back to the facility
    code itself when no cases directory or FDS file is available.
    """
    root = cases_dir or default_cases_root()
    if facility_name == "Boeing_Satellite01":
        facility_name = "Boeing_Satellite"
    fac_dir = root / facility_name
    fds_files = sorted(fac_dir.glob("*.fds")) if fac_dir.is_dir() else []
    if not fds_files:
        return facility_name
    stem = Path(fds_files[0]).stem
    match = _CONDITION_SUFFIX_RE.search(stem)
    return stem[: match.start()] if match else stem


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


def predict_facility_by_name(
    facility_name: str,
    predictor: Any,
    heat_source: dict[str, float] | None = None,
    cases_dir: Path | None = None,
) -> DamagePredictionContext:
    """Predict a facility that has a trained split model but no facilities JSON.

    Facilities without a JSON definition (e.g. ``boeing``, ``hanger``, ``ligen``,
    ``MPPF``, ``SLC`` ...) have no BuildingGroup geometry, so the normal
    ``predict_current_model`` path (FDS generation from buildings) cannot run.
    This uses one of the facility's own training-case FDS files as the feature
    source — the same geometry the model was trained on — and builds the case
    name from the requested heat-source condition.
    """
    cases_root = cases_dir or default_cases_root()
    if facility_name in _TRAINED_FACILITY_ALIASES:
        facility_name = _TRAINED_FACILITY_ALIASES[facility_name]
    known = set(getattr(predictor, "_known_facilities", set()) or set())
    if facility_name not in known:
        raise UnsupportedDamageFacility(
            f"设施“{facility_name}”不在逐设施模型的训练设施中。"
        )
    fac_dir = cases_root / facility_name
    reference_fds: Path | None = None
    if fac_dir.is_dir():
        fds_files = sorted(fac_dir.glob("*.fds"))
        reference_fds = fds_files[0] if fds_files else None
    if reference_fds is None:
        from models.facility import facilities_dir
        from services.fds_parser import resolve_reference_fds

        reference_fds = resolve_reference_fds(facility_name)
    if reference_fds is None:
        raise UnsupportedDamageFacility(
            f"设施“{facility_name}”没有可用的参考工况目录：{fac_dir}"
        )

    hs = dict(heat_source or {})
    suffix = (
        f"q{int(hs.get('heat_flux', 1000))}"
        f"_a{int(hs.get('azimuth', 0))}"
        f"_e{int(hs.get('elevation', 0))}"
        f"_d{int(float(hs.get('duration', 1.36)) * 1000)}"
        f"_t1800"
    )
    case_name = f"{facility_name}_{suffix}"
    prediction = predictor.predict(reference_fds, case_name)
    return DamagePredictionContext(
        prediction=prediction,
        facility_name=facility_name,
        ui_facility_name=facility_name,
        scale_name=None,
    )
