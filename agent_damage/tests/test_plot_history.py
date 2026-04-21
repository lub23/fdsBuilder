"""Tests for plot_history module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_damage.src.training.plot_history import plot_training_curves


def test_plot_training_curves_creates_file(tmp_path):
    summary_data = {
        "histories": {
            "mlp": {
                "train_loss": [0.5, 0.3, 0.1],
                "val_loss": [0.6, 0.4, 0.2],
                "train_acc": [0.7, 0.8, 0.9],
                "val_acc": [0.65, 0.75, 0.85],
            }
        }
    }
    summary_path = tmp_path / "train_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f)

    output_path = tmp_path / "training_curves.png"
    plot_training_curves(summary_path, output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_plot_training_curves_no_histories(tmp_path, capsys):
    summary_data = {"val_metrics": {}, "test_metrics": {}}
    summary_path = tmp_path / "train_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f)

    output_path = tmp_path / "training_curves.png"
    plot_training_curves(summary_path, output_path)

    captured = capsys.readouterr()
    assert "[plot] No histories found" in captured.out
    assert not output_path.exists()