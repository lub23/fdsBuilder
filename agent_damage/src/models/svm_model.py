"""SVM classifier wrapper (sklearn) matching our common interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.svm import SVC


@dataclass
class SVMDamageModel:
    C: float = 1.0
    gamma: str = "scale"

    def __post_init__(self) -> None:
        self._clf: Optional[SVC] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "SVMDamageModel":
        self._clf = SVC(
            C=self.C,
            kernel="rbf",
            gamma=self.gamma,
            class_weight="balanced",
            probability=True,
            random_state=0,
        )
        self._clf.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self._clf is not None, "Call .fit() first"
        return self._clf.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        assert self._clf is not None, "Call .fit() first"
        return self._clf.predict_proba(X)
