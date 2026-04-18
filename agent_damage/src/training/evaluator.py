"""Classifier metric computation (works for both PyTorch and sklearn models)."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)


def _predict(model: Any, X: np.ndarray) -> np.ndarray:
    if isinstance(model, torch.nn.Module):
        device = next(model.parameters()).device
        model.eval()
        with torch.no_grad():
            logits = model(torch.from_numpy(X).float().to(device))
            return logits.argmax(dim=1).cpu().numpy()
    return np.asarray(model.predict(X))


def _predict_proba(model: Any, X: np.ndarray) -> np.ndarray:
    if isinstance(model, torch.nn.Module):
        device = next(model.parameters()).device
        model.eval()
        with torch.no_grad():
            logits = model(torch.from_numpy(X).float().to(device))
            return torch.softmax(logits, dim=1).cpu().numpy()
    return np.asarray(model.predict_proba(X))


def evaluate_classifier(
    model: Any, X: np.ndarray, y: np.ndarray
) -> Dict[str, Any]:
    preds = _predict(model, X)
    return {
        "accuracy": accuracy_score(y, preds),
        "precision": precision_score(y, preds, average="weighted", zero_division=0),
        "recall": recall_score(y, preds, average="weighted", zero_division=0),
        "f1": f1_score(y, preds, average="weighted", zero_division=0),
        "confusion_matrix": confusion_matrix(y, preds, labels=[0, 1, 2]),
        "predictions": preds,
        "probabilities": _predict_proba(model, X),
    }
