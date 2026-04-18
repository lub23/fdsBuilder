import numpy as np
import pytest

from agent_damage.src.training.ensemble import (
    WeightedEnsemble,
    prediction_uncertainty,
)


def test_weighted_ensemble_simple():
    probs = {
        "A": np.array([[0.8, 0.1, 0.1], [0.2, 0.7, 0.1]]),
        "B": np.array([[0.6, 0.3, 0.1], [0.1, 0.6, 0.3]]),
    }
    weights = {"A": 0.6, "B": 0.4}
    ensemble = WeightedEnsemble(weights=weights)
    fused = ensemble.fuse(probs)
    assert np.allclose(fused[0], [0.72, 0.18, 0.10])
    assert np.allclose(fused[1], [0.16, 0.66, 0.18])


def test_weights_normalized_to_sum_one():
    weights = {"A": 0.8, "B": 0.2}
    ensemble = WeightedEnsemble(weights=weights)
    assert ensemble.weight_sum == 1.0


def test_from_accuracies_normalizes():
    accuracies = {"A": 0.8, "B": 0.4}
    ensemble = WeightedEnsemble.from_accuracies(accuracies)
    expected = {"A": 0.8 / 1.2, "B": 0.4 / 1.2}
    assert np.isclose(ensemble.weights["A"], expected["A"])
    assert np.isclose(ensemble.weights["B"], expected["B"])


def test_prediction_uncertainty_standard_deviation():
    probs = np.array(
        [
            [[0.8, 0.1, 0.1], [0.3, 0.5, 0.2]],
            [[0.7, 0.2, 0.1], [0.4, 0.4, 0.2]],
            [[0.9, 0.05, 0.05], [0.2, 0.6, 0.2]],
            [[0.75, 0.15, 0.1], [0.3, 0.5, 0.2]],
        ]
    )
    uncertainty = prediction_uncertainty(probs)
    assert uncertainty.shape == (2,)
    assert (uncertainty >= 0).all()


def test_weighted_ensemble_raises_on_mismatched_keys():
    probs = {"A": np.array([[0.8, 0.1, 0.1]])}
    ensemble = WeightedEnsemble(weights={"A": 0.6, "B": 0.4})
    with pytest.raises(KeyError):
        ensemble.fuse(probs)
