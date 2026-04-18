"""Random Forest classifier wrapper (sklearn)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.ensemble import RandomForestClassifier


@dataclass
class RFDamageModel:
    n_estimators: int = 100
    max_depth: int = 10

    def __post_init__(self) -> None:
        self._clf: Optional[RandomForestClassifier] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RFDamageModel":
        self._clf = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            class_weight="balanced",
            random_state=0,
            n_jobs=-1,
        )
        self._clf.fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self._clf is not None, "Call .fit() first"
        return self._clf.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        assert self._clf is not None, "Call .fit() first"
        return self._clf.predict_proba(X)
