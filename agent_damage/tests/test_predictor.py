import numpy as np
import pandas as pd
import pytest

from agent_damage.src.data.dataset import DamageDataset, fit_scaler
from agent_damage.src.data.generator import generate_balanced_dataset
from agent_damage.src.inference.predictor import EnsemblePredictor
from agent_damage.src.inference.results import (
    BuildingDamageResult,
    FacilityDamageResult,
)
from agent_damage.src.models.rf_model import RFDamageModel
from agent_damage.src.processing.enums import DamageLevel
from agent_damage.src.processing.facility_loader import load_core_facilities
from agent_damage.src.processing.heat_source import HeatSourceParams


@pytest.fixture(scope="module")
def trained_predictor():
    train_df = generate_balanced_dataset(n_samples=150, seed=11)
    scaler = fit_scaler(train_df)
    train_ds = DamageDataset(train_df, scaler=scaler)
    X, y = train_ds.as_numpy()
    rf = RFDamageModel().fit(X, y)
    predictor = EnsemblePredictor(
        models={"rf": rf},
        weights={"rf": 1.0},
        scaler=scaler,
    )
    return predictor


def test_predict_building_returns_result(trained_predictor):
    facility = load_core_facilities()[0]
    building = facility.buildings[0]
    hs = HeatSourceParams(elevation=30, azimuth=0, duration=2.1, heat_flux=5.0)
    result = trained_predictor.predict_building(facility, building, hs)
    assert isinstance(result, BuildingDamageResult)
    assert result.damage_level in set(DamageLevel)
    assert 0.0 <= result.probability <= 1.0
    assert result.uncertainty >= 0.0


def test_predict_facility_aggregates_buildings(trained_predictor):
    facility = load_core_facilities()[0]
    hs = HeatSourceParams(elevation=30, azimuth=0, duration=2.1, heat_flux=5.0)
    result = trained_predictor.predict_facility(facility, hs)
    assert isinstance(result, FacilityDamageResult)
    assert len(result.building_results) == facility.num_buildings
    overall = result.get_overall_level()
    assert overall in set(DamageLevel)


def test_predict_facility_max_algorithm(trained_predictor):
    facility = load_core_facilities()[0]
    hs = HeatSourceParams(elevation=0, azimuth=0, duration=7.5, heat_flux=20.0)
    result = trained_predictor.predict_facility(facility, hs)
    worst = max(r.damage_level.numeric for r in result.building_results)
    assert result.get_overall_level(algorithm="max").numeric == worst


def test_predict_facility_weighted_algorithm(trained_predictor):
    facility = load_core_facilities()[0]
    hs = HeatSourceParams(elevation=0, azimuth=0, duration=1.36, heat_flux=0.05)
    result = trained_predictor.predict_facility(facility, hs)
    lv = result.get_overall_level(algorithm="weighted")
    assert lv in set(DamageLevel)


def test_predict_facility_threshold_algorithm(trained_predictor):
    facility = load_core_facilities()[0]
    hs = HeatSourceParams(elevation=0, azimuth=90, duration=2.1, heat_flux=7.0)
    result = trained_predictor.predict_facility(facility, hs)
    lv = result.get_overall_level(algorithm="threshold")
    assert lv in set(DamageLevel)
