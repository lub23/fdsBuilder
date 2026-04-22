#!/usr/bin/env python3
"""CLI: load trained models, run ensemble evaluation, write report + plots."""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.src.data.dataset import DamageDataset
from agent_damage.src.models.cnn1d import CNN1D
from agent_damage.src.models.mlp import MLP
from agent_damage.src.training.ensemble import WeightedEnsemble, prediction_uncertainty
from agent_damage.src.training.evaluator import evaluate_classifier

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CKPT_DIR = ROOT / "checkpoints"
OUTPUT_DIR = ROOT / "output"


def _load_torch(path: Path, model_cls, num_features: int):
    ckpt = torch.load(path, map_location="cpu")
    model = model_cls(input_dim=num_features)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model


def _plot_confusion(cm: np.ndarray, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks([0, 1, 2], labels=["Low", "Medium", "High"])
    ax.set_yticks([0, 1, 2], labels=["Low", "Medium", "High"])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)
    for i in range(3):
        for j in range(3):
            ax.text(j, i, int(cm[i, j]), ha="center", va="center")
    plt.colorbar(im, ax=ax)
    plt.tight_layout()
    plt.savefig(path, dpi=130)
    plt.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="test", choices=["val", "test"])
    args = parser.parse_args()

    with open(CKPT_DIR / "scaler.pkl", "rb") as f:
        scaler = pickle.load(f)

    df = pd.read_csv(DATA_DIR / f"{args.split}.csv")
    ds = DamageDataset(df, scaler=scaler)
    X, y = ds.as_numpy()
    facility_names = df["facility_name"].to_numpy()

    models: Dict[str, Any] = {}
    if (CKPT_DIR / "svm_model.pkl").exists():
        with open(CKPT_DIR / "svm_model.pkl", "rb") as f:
            models["svm"] = pickle.load(f)["model"]
    if (CKPT_DIR / "rf_model.pkl").exists():
        with open(CKPT_DIR / "rf_model.pkl", "rb") as f:
            models["rf"] = pickle.load(f)["model"]
    if (CKPT_DIR / "mlp_model.pt").exists():
        models["mlp"] = _load_torch(CKPT_DIR / "mlp_model.pt", MLP, ds.num_features)
    if (CKPT_DIR / "cnn1d_model.pt").exists():
        models["cnn1d"] = _load_torch(
            CKPT_DIR / "cnn1d_model.pt", CNN1D, ds.num_features
        )
    if not models:
        raise RuntimeError("No model checkpoints found in " + str(CKPT_DIR))

    per_model_metrics: Dict[str, Dict[str, float]] = {}
    probas: Dict[str, np.ndarray] = {}
    for name, model in models.items():
        metrics = evaluate_classifier(model, X, y)
        per_model_metrics[name] = {
            "accuracy": float(metrics["accuracy"]),
            "precision": float(metrics["precision"]),
            "recall": float(metrics["recall"]),
            "f1": float(metrics["f1"]),
        }
        probas[name] = metrics["probabilities"]
        _plot_confusion(
            metrics["confusion_matrix"],
            OUTPUT_DIR / f"confusion_{name}_{args.split}.png",
            f"Confusion: {name.upper()} ({args.split})",
        )

    unique_facilities = np.unique(facility_names)
    per_facility_metrics: Dict[str, Dict[str, Any]] = {}
    for ftype in unique_facilities:
        mask = facility_names == ftype
        f_y = y[mask]
        per_facility_metrics[ftype] = {}
        for name in models:
            f_probs = probas[name][mask]
            f_preds = np.argmax(f_probs, axis=1)
            per_facility_metrics[ftype][name] = {
                "accuracy": float(np.mean(f_preds == f_y)),
                "precision": float(precision_score(f_y, f_preds, average="weighted", zero_division=0)),
                "recall": float(recall_score(f_y, f_preds, average="weighted", zero_division=0)),
                "f1": float(f1_score(f_y, f_preds, average="weighted", zero_division=0)),
            }
        if len(models) >= 2:
            avg_probs = np.mean([probas[n][mask] for n in models], axis=0)
            f_ensemble_preds = np.argmax(avg_probs, axis=1)
            per_facility_metrics[ftype]["ensemble"] = {
                "accuracy": float(np.mean(f_ensemble_preds == f_y)),
                "f1": float(f1_score(f_y, f_ensemble_preds, average="weighted", zero_division=0)),
            }

    summary_path = OUTPUT_DIR / "train_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        accuracies = {
            name: summary["val_metrics"][name]["accuracy"]
            for name in models
            if name in summary.get("val_metrics", {})
        }
    else:
        accuracies = {name: per_model_metrics[name]["accuracy"] for name in models}

    ensemble = WeightedEnsemble.from_accuracies(accuracies)
    fused = ensemble.fuse(probas)
    preds = fused.argmax(axis=1)
    stack = np.stack(list(probas.values()), axis=0)
    uncertainty = prediction_uncertainty(stack)

    ensemble_metrics = {
        "accuracy": float(accuracy_score(y, preds)),
        "f1": float(f1_score(y, preds, average="weighted", zero_division=0)),
        "mean_uncertainty": float(uncertainty.mean()),
    }
    _plot_confusion(
        confusion_matrix(y, preds, labels=[0, 1, 2]),
        OUTPUT_DIR / f"confusion_ensemble_{args.split}.png",
        f"Confusion: Ensemble ({args.split})",
    )

    report = {
        "split": args.split,
        "per_model": per_model_metrics,
        "per_facility": per_facility_metrics,
        "ensemble": ensemble_metrics,
        "weights": ensemble.weights,
    }
    report_path = OUTPUT_DIR / f"evaluation_{args.split}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[evaluate] Report saved to {report_path}")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())