"""Load trained model checkpoints from disk into an EnsemblePredictor.

Reads the artifacts produced by `agent_damage/scripts/train.py`:
    checkpoints/scaler.pkl
    checkpoints/svm_model.pkl      (optional)
    checkpoints/rf_model.pkl       (optional)
    checkpoints/mlp_model.pt       (optional)
    checkpoints/cnn1d_model.pt     (optional)
    output/train_summary.json      (optional; used for ensemble weights)
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import torch

from ..data.generator import FEATURE_COLUMNS
from ..models.cnn1d import CNN1D
from ..models.mlp import MLP
from .predictor import EnsemblePredictor


DEFAULT_CKPT_DIR = Path(__file__).resolve().parents[2] / "checkpoints"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


class CheckpointError(RuntimeError):
    """Raised when no usable checkpoints are found on disk."""


def _load_torch(path: Path, cls) -> torch.nn.Module:
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = cls(input_dim=len(FEATURE_COLUMNS))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model


def load_predictor_from_checkpoints(
    ckpt_dir: Path | None = None,
    output_dir: Path | None = None,
) -> EnsemblePredictor:
    """Build an EnsemblePredictor from saved checkpoints.

    Raises:
        CheckpointError: if scaler.pkl is missing, or no model files are found.
    """
    ckpt_dir = Path(ckpt_dir) if ckpt_dir else DEFAULT_CKPT_DIR
    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR

    scaler_path = ckpt_dir / "scaler.pkl"
    if not scaler_path.exists():
        raise CheckpointError(
            f"Missing scaler.pkl at {scaler_path}. Run `train.py` first."
        )
    with open(scaler_path, "rb") as f:
        scaler = pickle.load(f)

    models: Dict[str, Any] = {}

    svm_path = ckpt_dir / "svm_model.pkl"
    if svm_path.exists():
        with open(svm_path, "rb") as f:
            models["svm"] = pickle.load(f)["model"]

    rf_path = ckpt_dir / "rf_model.pkl"
    if rf_path.exists():
        with open(rf_path, "rb") as f:
            models["rf"] = pickle.load(f)["model"]

    mlp_path = ckpt_dir / "mlp_model.pt"
    if mlp_path.exists():
        models["mlp"] = _load_torch(mlp_path, MLP)

    cnn1d_path = ckpt_dir / "cnn1d_model.pt"
    if cnn1d_path.exists():
        models["cnn1d"] = _load_torch(cnn1d_path, CNN1D)

    if not models:
        raise CheckpointError(
            f"No model checkpoints found in {ckpt_dir}. "
            "Run `train.py` to produce at least one of: "
            "svm_model.pkl, rf_model.pkl, mlp_model.pt, cnn1d_model.pt."
        )

    weights: Dict[str, float] = _resolve_weights(models.keys(), output_dir)

    return EnsemblePredictor(models=models, weights=weights, scaler=scaler)


def _resolve_weights(model_names, output_dir: Path) -> Dict[str, float]:
    """Prefer val_metrics.{name}.accuracy from train_summary.json;
    fall back to equal weights. Adds 1e-3 jitter so a model with 0 accuracy
    can still participate."""
    summary_path = output_dir / "train_summary.json"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text())
        except Exception:
            summary = {}
        val_metrics = summary.get("val_metrics", {}) or {}
        weights = {
            name: float(val_metrics.get(name, {}).get("accuracy", 0.0)) + 1e-3
            for name in model_names
        }
        if sum(weights.values()) > 0:
            return weights

    return {name: 1.0 for name in model_names}


def list_available_checkpoints(ckpt_dir: Path | None = None) -> List[str]:
    """Return a human-readable list of which checkpoints are available."""
    ckpt_dir = Path(ckpt_dir) if ckpt_dir else DEFAULT_CKPT_DIR
    names = []
    for filename, label in (
        ("scaler.pkl", "scaler"),
        ("svm_model.pkl", "SVM"),
        ("rf_model.pkl", "Random Forest"),
        ("mlp_model.pt", "MLP"),
        ("cnn1d_model.pt", "CNN1D"),
    ):
        if (ckpt_dir / filename).exists():
            names.append(label)
    return names
