"""PyTorch Dataset + numpy accessors for the 23-dim facility damage features."""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch.utils.data import Dataset

from .generator import FEATURE_COLUMNS


def fit_scaler(df: pd.DataFrame) -> StandardScaler:
    scaler = StandardScaler()
    scaler.fit(df[list(FEATURE_COLUMNS)].to_numpy(dtype=np.float32))
    return scaler


class DamageDataset(Dataset):
    """Wraps a DataFrame (as produced by `generate_balanced_dataset`).

    - `scaler` must be pre-fit on training data and reused for val/test.
    """

    def __init__(self, df: pd.DataFrame, scaler: StandardScaler) -> None:
        X_raw = df[list(FEATURE_COLUMNS)].to_numpy(dtype=np.float32)
        self._X = scaler.transform(X_raw).astype(np.float32)
        self._y = df["label"].to_numpy(dtype=np.int64)
        self._scaler = scaler

    def __len__(self) -> int:
        return self._X.shape[0]

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        return (
            torch.from_numpy(self._X[idx]),
            torch.tensor(self._y[idx], dtype=torch.long),
        )

    def as_numpy(self) -> Tuple[np.ndarray, np.ndarray]:
        return self._X.copy(), self._y.copy()

    @property
    def num_features(self) -> int:
        return self._X.shape[1]

    @property
    def num_classes(self) -> int:
        return 3

    @property
    def scaler(self) -> StandardScaler:
        return self._scaler
