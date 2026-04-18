"""Balanced rejection-sampling dataset generator for 4 core facilities."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from ..processing.building import Building
from ..processing.facility import Facility
from ..processing.facility_loader import load_core_facilities
from ..processing.heat_source import (
    AZIMUTH_OPTIONS,
    DURATION_OPTIONS,
    ELEVATION_OPTIONS,
    HEAT_FLUX_OPTIONS,
    HeatSourceParams,
)
from ..processing.occlusion import occluding_higher_count
from .labeling import simulate_damage_label


FEATURE_COLUMNS: Tuple[str, ...] = (
    # building (18)
    "length",
    "width",
    "height",
    "door_count",
    "window_count",
    "stories",
    "boundary_x",
    "boundary_y",
    "opening_ratio",
    "facility_type_index",
    "comb_wood_paper",
    "comb_textile",
    "comb_plastic",
    "comb_fuel_oil",
    "comb_electronics",
    "comb_chemical",
    "comb_metal",
    "comb_composite",
    # heat source (4)
    "heat_elevation",
    "heat_azimuth",
    "heat_duration",
    "heat_flux",
    # occlusion (1)
    "occluding_higher_count",
)


def build_sample(
    facility: Facility, building: Building, heat_source: HeatSourceParams
) -> Dict[str, object]:
    occ = occluding_higher_count(facility, building, heat_source.azimuth)
    features = (
        building.to_feature_vector(facility_type_index=facility.facility_type.index)
        + heat_source.to_feature_vector()
        + [float(occ)]
    )
    label = simulate_damage_label(building, heat_source, occ)
    return {
        "features": features,
        "label": label.numeric,
        "facility_name": facility.name,
        "building_name": building.name,
    }


def _sample_heat_source(rng: random.Random) -> HeatSourceParams:
    return HeatSourceParams(
        elevation=rng.choice(ELEVATION_OPTIONS),
        azimuth=rng.choice(AZIMUTH_OPTIONS),
        duration=rng.choice(DURATION_OPTIONS),
        heat_flux=rng.choice(HEAT_FLUX_OPTIONS),
    )


def generate_balanced_dataset(n_samples: int, seed: int = 42) -> pd.DataFrame:
    """Rejection sample until each class reaches ~n_samples/3."""
    rng = random.Random(seed)
    facilities = list(load_core_facilities())
    target_per_class = n_samples // 3
    remainder = n_samples - target_per_class * 3
    quotas = {0: target_per_class, 1: target_per_class, 2: target_per_class + remainder}
    accepted: List[Dict[str, object]] = []
    class_counts = {0: 0, 1: 0, 2: 0}

    max_attempts = n_samples * 100
    attempts = 0
    while sum(class_counts.values()) < n_samples:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError(
                f"Rejection sampling failed to reach balance in {max_attempts} attempts"
            )
        facility = rng.choice(facilities)
        building = rng.choice(facility.buildings)
        heat_source = _sample_heat_source(rng)
        sample = build_sample(facility, building, heat_source)
        cls = sample["label"]
        if class_counts[cls] >= quotas[cls]:
            continue
        class_counts[cls] += 1
        accepted.append(sample)

    rows = []
    for s in accepted:
        row = dict(zip(FEATURE_COLUMNS, s["features"]))
        row["label"] = s["label"]
        row["facility_name"] = s["facility_name"]
        row["building_name"] = s["building_name"]
        rows.append(row)
    rng.shuffle(rows)
    return pd.DataFrame(rows)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def generate_splits(
    n_train: int = 5000,
    n_val: int = 1000,
    n_test: int = 1000,
    seed: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        generate_balanced_dataset(n_train, seed=seed),
        generate_balanced_dataset(n_val, seed=seed + 1),
        generate_balanced_dataset(n_test, seed=seed + 2),
    )
