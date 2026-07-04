from pathlib import Path

import numpy as np
import pandas as pd
import torch

from agent_damage.src.data.dataset import DamageDataset, fit_scaler
from agent_damage.src.data.generator import generate_splits
from agent_damage.src.inference.predictor import EnsemblePredictor
from agent_damage.src.models.mlp import MLP
from agent_damage.src.models.rf_model import RFDamageModel
from agent_damage.src.models.svm_model import SVMDamageModel
from agent_damage.src.processing.facility_loader import load_core_facilities
from agent_damage.src.processing.heat_source import HeatSourceParams
from agent_damage.src.training.evaluator import evaluate_classifier
from agent_damage.src.training.torch_trainer import TorchTrainConfig, train_torch_model


def test_end_to_end_pipeline(tmp_path: Path):
    # 1. Generate small dataset
    train_df, val_df, test_df = generate_splits(n_train=180, n_val=60, n_test=60, seed=3)
    scaler = fit_scaler(train_df)
    train_ds = DamageDataset(train_df, scaler=scaler)
    val_ds = DamageDataset(val_df, scaler=scaler)
    test_ds = DamageDataset(test_df, scaler=scaler)

    X_train, y_train = train_ds.as_numpy()
    X_test, y_test = test_ds.as_numpy()

    # 2. Train 3 models (skip CNN1D to keep runtime small)
    svm = SVMDamageModel().fit(X_train, y_train)
    rf = RFDamageModel().fit(X_train, y_train)
    mlp_model, _ = train_torch_model(
        MLP(input_dim=train_ds.num_features),
        train_ds,
        val_ds,
        TorchTrainConfig(num_epochs=5, batch_size=32, device="cpu"),
    )

    # 3. Per-model accuracy
    for m in (svm, rf, mlp_model):
        metrics = evaluate_classifier(m, X_test, y_test)
        assert 0.0 <= metrics["accuracy"] <= 1.0

    # 4. Ensemble predictor
    weights = {
        "svm": evaluate_classifier(svm, X_test, y_test)["accuracy"] + 1e-3,
        "rf": evaluate_classifier(rf, X_test, y_test)["accuracy"] + 1e-3,
        "mlp": evaluate_classifier(mlp_model, X_test, y_test)["accuracy"] + 1e-3,
    }
    predictor = EnsemblePredictor(
        models={"svm": svm, "rf": rf, "mlp": mlp_model},
        weights=weights,
        scaler=scaler,
    )

    # 5. Facility-level inference
    facility = load_core_facilities()[0]
    heat = HeatSourceParams(elevation=30, azimuth=180, duration=2.1, heat_flux=7000)
    result = predictor.predict_facility(facility, heat)
    assert len(result.building_results) == facility.num_buildings
    # Try each aggregation algorithm
    for alg in ("max", "weighted", "threshold"):
        _ = result.get_overall_level(algorithm=alg)
