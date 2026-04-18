"""Weighted ensemble fusion over per-model probability matrices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


@dataclass
class WeightedEnsemble:
    """Stores normalized per-model weights and fuses probability matrices.

    probabilities for each model: shape (n_samples, n_classes)
    Output: fused probabilities shape (n_samples, n_classes)
    """

    weights: Dict[str, float]

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if total <= 0:
            raise ValueError("All weights are zero")
        self.weights = {k: v / total for k, v in self.weights.items()}

    @property
    def weight_sum(self) -> float:
        return sum(self.weights.values())

    @classmethod
    def from_accuracies(cls, accuracies: Dict[str, float]) -> "WeightedEnsemble":
        return cls(weights=dict(accuracies))

    def fuse(self, probs: Dict[str, np.ndarray]) -> np.ndarray:
        missing = set(self.weights) - set(probs)
        if missing:
            raise KeyError(f"Missing probabilities for models: {missing}")
        stacked = None
        for name, w in self.weights.items():
            contribution = probs[name] * w
            stacked = contribution if stacked is None else stacked + contribution
        assert stacked is not None
        return stacked


def prediction_uncertainty(probs_stack: np.ndarray) -> np.ndarray:
    """Per-sample uncertainty = mean standard deviation across models of
    each class probability.

    probs_stack: (n_models, n_samples, n_classes)
    returns: (n_samples,)
    """
    if probs_stack.ndim != 3:
        raise ValueError(f"Expected 3D array, got shape {probs_stack.shape}")
    stds = probs_stack.std(axis=0)  # (n_samples, n_classes)
    return stds.mean(axis=1)
