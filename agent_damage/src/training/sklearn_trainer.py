"""Thin wrapper that invokes sklearn model `.fit()` and returns the fitted model."""

from __future__ import annotations

from typing import Union

import numpy as np

from ..models.rf_model import RFDamageModel
from ..models.svm_model import SVMDamageModel


SklearnModel = Union[SVMDamageModel, RFDamageModel]


def train_sklearn_model(model: SklearnModel, X: np.ndarray, y: np.ndarray) -> SklearnModel:
    return model.fit(X, y)
