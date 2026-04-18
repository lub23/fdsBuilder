from pathlib import Path

import pandas as pd
import pytest

from agent_damage.src.data.generator import (
    FEATURE_COLUMNS,
    build_sample,
    generate_balanced_dataset,
    write_csv,
)
from agent_damage.src.processing.facility_loader import load_core_facilities
from agent_damage.src.processing.heat_source import HeatSourceParams


def test_feature_columns_are_23():
    assert len(FEATURE_COLUMNS) == 23


def test_build_sample_shape():
    facility = load_core_facilities()[0]
    building = facility.buildings[0]
    hs = HeatSourceParams(elevation=30, azimuth=90, duration=2.1, heat_flux=10.0)
    row = build_sample(facility, building, hs)
    assert len(row["features"]) == 23
    assert row["label"] in {0, 1, 2}
    assert row["facility_name"] == facility.name
    assert row["building_name"] == building.name


def test_generate_balanced_dataset_small():
    df = generate_balanced_dataset(n_samples=300, seed=7)
    assert len(df) == 300
    counts = df["label"].value_counts().to_dict()
    for cls in (0, 1, 2):
        assert counts.get(cls, 0) >= 80


def test_write_csv(tmp_path: Path):
    df = generate_balanced_dataset(n_samples=30, seed=1)
    path = tmp_path / "tiny.csv"
    write_csv(df, path)
    assert path.exists()
    loaded = pd.read_csv(path)
    assert len(loaded) == 30
    assert set(FEATURE_COLUMNS).issubset(loaded.columns)
    assert "label" in loaded.columns
