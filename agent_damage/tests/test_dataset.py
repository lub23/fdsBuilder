import numpy as np
import pandas as pd
import pytest
import torch

from agent_damage.src.data.dataset import DamageDataset, fit_scaler
from agent_damage.src.data.generator import FEATURE_COLUMNS, generate_balanced_dataset


@pytest.fixture(scope="module")
def toy_df() -> pd.DataFrame:
    return generate_balanced_dataset(n_samples=60, seed=123)


def test_dataset_exposes_numpy_arrays(toy_df: pd.DataFrame):
    scaler = fit_scaler(toy_df)
    ds = DamageDataset(toy_df, scaler=scaler)
    X, y = ds.as_numpy()
    assert X.shape == (60, 23)
    assert y.shape == (60,)
    assert y.dtype == np.int64
    assert set(y.tolist()) <= {0, 1, 2}


def test_dataset_torch_interface(toy_df: pd.DataFrame):
    scaler = fit_scaler(toy_df)
    ds = DamageDataset(toy_df, scaler=scaler)
    assert len(ds) == 60
    x, y = ds[0]
    assert isinstance(x, torch.Tensor)
    assert isinstance(y, torch.Tensor)
    assert x.shape == (23,)
    assert y.dtype == torch.long


def test_fit_scaler_is_deterministic(toy_df: pd.DataFrame):
    s1 = fit_scaler(toy_df)
    s2 = fit_scaler(toy_df)
    assert np.allclose(s1.mean_, s2.mean_)
    assert np.allclose(s1.scale_, s2.scale_)


def test_scaler_applied_consistently(toy_df: pd.DataFrame):
    scaler = fit_scaler(toy_df)
    ds = DamageDataset(toy_df, scaler=scaler)
    X_scaled = ds.as_numpy()[0]
    assert np.allclose(X_scaled.mean(axis=0), 0, atol=1e-6)
