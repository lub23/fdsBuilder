#!/usr/bin/env python3
"""CLI: train SVM / RF / MLP / CNN1D and save checkpoints + metrics."""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.src.data.dataset import DamageDataset, fit_scaler
from agent_damage.src.models.cnn1d import CNN1D
from agent_damage.src.models.mlp import MLP
from agent_damage.src.models.rf_model import RFDamageModel
from agent_damage.src.models.svm_model import SVMDamageModel
from agent_damage.src.training.evaluator import evaluate_classifier
from agent_damage.src.training.plot_history import plot_training_curves
from agent_damage.src.training.torch_trainer import TorchTrainConfig, train_torch_model


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CKPT_DIR = ROOT / "checkpoints"
OUTPUT_DIR = ROOT / "output"


def _load_dataframes() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_df = pd.read_csv(DATA_DIR / "train.csv")
    val_df = pd.read_csv(DATA_DIR / "val.csv")
    test_df = pd.read_csv(DATA_DIR / "test.csv")
    return train_df, val_df, test_df


def _metric_summary(metrics: Dict[str, Any]) -> Dict[str, float]:
    return {
        "accuracy": float(metrics["accuracy"]),
        "precision": float(metrics["precision"]),
        "recall": float(metrics["recall"]),
        "f1": float(metrics["f1"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        choices=["svm", "rf", "mlp", "cnn1d"],
        default=["svm", "rf", "mlp", "cnn1d"],
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch_size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    train_df, val_df, test_df = _load_dataframes()
    scaler = fit_scaler(train_df)
    train_ds = DamageDataset(train_df, scaler=scaler)
    val_ds = DamageDataset(val_df, scaler=scaler)
    test_ds = DamageDataset(test_df, scaler=scaler)

    X_train, y_train = train_ds.as_numpy()
    X_val, y_val = val_ds.as_numpy()
    X_test, y_test = test_ds.as_numpy()

    val_metrics: Dict[str, Dict] = {}
    test_metrics: Dict[str, Dict] = {}
    histories: Dict[str, Dict] = {}

    for name in args.models:
        print(f"[train] training {name}")
        if name == "svm":
            model: Any = SVMDamageModel().fit(X_train, y_train)
            with open(CKPT_DIR / "svm_model.pkl", "wb") as f:
                pickle.dump({"model": model, "scaler": scaler}, f)
        elif name == "rf":
            model = RFDamageModel().fit(X_train, y_train)
            with open(CKPT_DIR / "rf_model.pkl", "wb") as f:
                pickle.dump({"model": model, "scaler": scaler}, f)
        elif name == "mlp":
            torch_model = MLP(input_dim=train_ds.num_features)
            cfg = TorchTrainConfig(
                num_epochs=args.epochs,
                batch_size=args.batch_size,
                learning_rate=args.lr,
                device=args.device,
            )
            torch_model, hist = train_torch_model(torch_model, train_ds, val_ds, cfg)
            torch.save(
                {"state_dict": torch_model.state_dict(), "history": hist},
                CKPT_DIR / "mlp_model.pt",
            )
            histories["mlp"] = hist
            model = torch_model
        elif name == "cnn1d":
            torch_model = CNN1D(input_dim=train_ds.num_features)
            cfg = TorchTrainConfig(
                num_epochs=args.epochs,
                batch_size=args.batch_size,
                learning_rate=args.lr,
                device=args.device,
            )
            torch_model, hist = train_torch_model(torch_model, train_ds, val_ds, cfg)
            torch.save(
                {"state_dict": torch_model.state_dict(), "history": hist},
                CKPT_DIR / "cnn1d_model.pt",
            )
            histories["cnn1d"] = hist
            model = torch_model
        else:
            raise ValueError(name)

        v = evaluate_classifier(model, X_val, y_val)
        t = evaluate_classifier(model, X_test, y_test)
        val_metrics[name] = _metric_summary(v)
        test_metrics[name] = _metric_summary(t)
        print(f"[train] {name} val={val_metrics[name]} test={test_metrics[name]}")

    with open(CKPT_DIR / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    summary = {
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "histories": {k: {sk: list(map(float, sv)) for sk, sv in v.items()} for k, v in histories.items()},
    }
    with open(OUTPUT_DIR / "train_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[train] Summary saved to {OUTPUT_DIR / 'train_summary.json'}")

    plot_training_curves(OUTPUT_DIR / "train_summary.json", OUTPUT_DIR / "training_curves.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
