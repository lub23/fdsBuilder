import pickle
from pathlib import Path

import pytest

from agent_damage.src.data.dataset import DamageDataset, fit_scaler
from agent_damage.src.data.generator import generate_balanced_dataset
from agent_damage.src.inference.loader import (
    CheckpointError,
    list_available_checkpoints,
    load_predictor_from_checkpoints,
)
from agent_damage.src.inference.predictor import EnsemblePredictor
from agent_damage.src.models.rf_model import RFDamageModel


def _prepare_ckpt_dir(tmp_path: Path, with_rf: bool = True, with_summary: bool = True):
    ckpt_dir = tmp_path / "checkpoints"
    output_dir = tmp_path / "output"
    ckpt_dir.mkdir()
    output_dir.mkdir()

    df = generate_balanced_dataset(n_samples=90, seed=3)
    scaler = fit_scaler(df)
    with open(ckpt_dir / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    if with_rf:
        ds = DamageDataset(df, scaler=scaler)
        X, y = ds.as_numpy()
        rf = RFDamageModel().fit(X, y)
        with open(ckpt_dir / "rf_model.pkl", "wb") as f:
            pickle.dump({"model": rf, "scaler": scaler}, f)

    if with_summary:
        (output_dir / "train_summary.json").write_text(
            '{"val_metrics": {"rf": {"accuracy": 0.92}}}'
        )

    return ckpt_dir, output_dir


def test_loader_builds_ensemble_predictor(tmp_path: Path):
    ckpt_dir, output_dir = _prepare_ckpt_dir(tmp_path)
    predictor = load_predictor_from_checkpoints(ckpt_dir, output_dir)
    assert isinstance(predictor, EnsemblePredictor)
    assert set(predictor.models) == {"rf"}
    # Weights should reflect the summary.json accuracy (plus jitter)
    assert pytest.approx(predictor.ensemble.weights["rf"], rel=1e-3) == 1.0


def test_loader_without_summary_uses_uniform_weights(tmp_path: Path):
    ckpt_dir, output_dir = _prepare_ckpt_dir(tmp_path, with_summary=False)
    predictor = load_predictor_from_checkpoints(ckpt_dir, output_dir)
    assert predictor.ensemble.weights["rf"] == 1.0


def test_loader_raises_when_scaler_missing(tmp_path: Path):
    ckpt_dir = tmp_path / "checkpoints"
    output_dir = tmp_path / "output"
    ckpt_dir.mkdir()
    output_dir.mkdir()
    with pytest.raises(CheckpointError):
        load_predictor_from_checkpoints(ckpt_dir, output_dir)


def test_loader_raises_when_no_models(tmp_path: Path):
    ckpt_dir, output_dir = _prepare_ckpt_dir(tmp_path, with_rf=False)
    with pytest.raises(CheckpointError):
        load_predictor_from_checkpoints(ckpt_dir, output_dir)


def test_list_available_checkpoints(tmp_path: Path):
    ckpt_dir, _ = _prepare_ckpt_dir(tmp_path)
    names = list_available_checkpoints(ckpt_dir)
    assert "scaler" in names
    assert "Random Forest" in names
    assert "SVM" not in names
