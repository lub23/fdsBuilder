from pathlib import Path

from PIL import Image

from agent_damage.scripts.train_experimental import (
    _candidate_models,
    _plot_extra_trees_architecture,
)


def test_only_production_extra_trees_model_is_configured() -> None:
    models = _candidate_models(seed=42)
    assert set(models) == {"grade_constrained_extra_trees"}
    params = models["grade_constrained_extra_trees"].get_params(deep=True)
    assert params["regressor__n_estimators"] == 75
    assert params["classifier__n_estimators"] == 75
    assert params["classifier__criterion"] == "entropy"
    assert params["classifier__class_weight"] == "balanced"


def test_extra_trees_architecture_figure_is_rendered(tmp_path: Path) -> None:
    output = tmp_path / "extra_trees_architecture.png"
    _plot_extra_trees_architecture(output, n_estimators=75, feature_count=58)
    with Image.open(output) as image:
        assert image.width >= 2000
        assert image.height >= 1000
