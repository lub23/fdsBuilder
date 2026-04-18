import pandas as pd
import pytest

from agent_damage.src.data.dataset import DamageDataset, fit_scaler
from agent_damage.src.data.generator import generate_balanced_dataset
from agent_damage.src.models.mlp import MLP
from agent_damage.src.models.rf_model import RFDamageModel
from agent_damage.src.models.svm_model import SVMDamageModel
from agent_damage.src.training.evaluator import evaluate_classifier
from agent_damage.src.training.sklearn_trainer import train_sklearn_model
from agent_damage.src.training.torch_trainer import (
    TorchTrainConfig,
    train_torch_model,
)


def _toy_datasets():
    train_df = generate_balanced_dataset(n_samples=150, seed=1)
    val_df = generate_balanced_dataset(n_samples=60, seed=2)
    scaler = fit_scaler(train_df)
    return (
        DamageDataset(train_df, scaler=scaler),
        DamageDataset(val_df, scaler=scaler),
    )


def test_train_torch_runs_and_reports_history():
    train_ds, val_ds = _toy_datasets()
    model = MLP(input_dim=train_ds.num_features)
    cfg = TorchTrainConfig(num_epochs=3, batch_size=32, early_stopping_patience=5)
    trained, history = train_torch_model(model, train_ds, val_ds, cfg)
    assert len(history["train_loss"]) == 3
    assert len(history["val_acc"]) == 3


def test_history_keys_present():
    train_ds, val_ds = _toy_datasets()
    model = MLP(input_dim=train_ds.num_features)
    cfg = TorchTrainConfig(num_epochs=1, batch_size=32)
    _, history = train_torch_model(model, train_ds, val_ds, cfg)
    for k in ("train_loss", "train_acc", "val_loss", "val_acc"):
        assert k in history


def test_train_sklearn_svm():
    train_ds, val_ds = _toy_datasets()
    X_train, y_train = train_ds.as_numpy()
    model = SVMDamageModel()
    fitted = train_sklearn_model(model, X_train, y_train)
    X_val, y_val = val_ds.as_numpy()
    preds = fitted.predict(X_val)
    assert preds.shape == (len(y_val),)


def test_train_sklearn_rf():
    train_ds, val_ds = _toy_datasets()
    X_train, y_train = train_ds.as_numpy()
    model = RFDamageModel()
    fitted = train_sklearn_model(model, X_train, y_train)
    X_val, y_val = val_ds.as_numpy()
    assert fitted.predict(X_val).shape == (len(y_val),)


def test_evaluate_classifier_returns_keys():
    train_ds, val_ds = _toy_datasets()
    X_train, y_train = train_ds.as_numpy()
    X_val, y_val = val_ds.as_numpy()
    model = RFDamageModel().fit(X_train, y_train)
    metrics = evaluate_classifier(model, X_val, y_val)
    for key in ("accuracy", "precision", "recall", "f1", "confusion_matrix"):
        assert key in metrics
    cm = metrics["confusion_matrix"]
    assert cm.shape == (3, 3)
