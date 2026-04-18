import numpy as np
import pytest
import torch

from agent_damage.src.models.cnn1d import CNN1D
from agent_damage.src.models.mlp import MLP
from agent_damage.src.models.rf_model import RFDamageModel
from agent_damage.src.models.svm_model import SVMDamageModel


def test_mlp_forward_shape():
    model = MLP(input_dim=23, num_classes=3)
    x = torch.randn(4, 23)
    logits = model(x)
    assert logits.shape == (4, 3)


def test_mlp_predict_proba_sums_to_one():
    model = MLP(input_dim=23, num_classes=3)
    x = torch.randn(8, 23)
    probs = model.predict_proba(x)
    assert probs.shape == (8, 3)
    assert torch.allclose(probs.sum(dim=1), torch.ones(8), atol=1e-5)


def test_cnn1d_forward_shape():
    model = CNN1D(input_dim=23, num_classes=3)
    x = torch.randn(4, 23)
    logits = model(x)
    assert logits.shape == (4, 3)


def test_cnn1d_predict_proba_sums_to_one():
    model = CNN1D(input_dim=23, num_classes=3)
    x = torch.randn(8, 23)
    probs = model.predict_proba(x)
    assert torch.allclose(probs.sum(dim=1), torch.ones(8), atol=1e-5)


def test_svm_predict_shapes():
    X = np.random.randn(60, 23).astype(np.float32)
    y = np.random.randint(0, 3, size=60)
    model = SVMDamageModel()
    model.fit(X, y)
    pred = model.predict(X)
    proba = model.predict_proba(X)
    assert pred.shape == (60,)
    assert proba.shape == (60, 3)
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-5)


def test_rf_predict_shapes():
    X = np.random.randn(60, 23).astype(np.float32)
    y = np.random.randint(0, 3, size=60)
    model = RFDamageModel()
    model.fit(X, y)
    pred = model.predict(X)
    proba = model.predict_proba(X)
    assert pred.shape == (60,)
    assert proba.shape == (60, 3)
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-5)
