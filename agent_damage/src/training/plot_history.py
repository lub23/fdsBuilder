"""Plot training curves from train_summary.json."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt


def plot_training_curves(summary_path: Path, output_path: Path) -> None:
    """Read train_summary.json and plot training curves for each model.

    Args:
        summary_path: Path to train_summary.json
        output_path: Path to save the figure
    """
    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)

    histories = summary.get("histories", {})
    if not histories:
        print("[plot] No histories found in train_summary.json")
        return

    models = list(histories.keys())
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

    fig, axes = plt.subplots(2, 1, figsize=(10, 6))
    fig.suptitle("Training Curves", fontsize=14)

    for idx, model_name in enumerate(models):
        hist = histories[model_name]
        color = colors[idx % len(colors)]

        train_loss = hist.get("train_loss", [])
        val_loss = hist.get("val_loss", [])
        train_acc = hist.get("train_acc", [])
        val_acc = hist.get("val_acc", [])

        epochs = list(range(1, len(train_loss) + 1))

        axes[0].plot(epochs, train_loss, label=f"{model_name} train", linestyle="-", color=color)
        axes[0].plot(epochs, val_loss, label=f"{model_name} val", linestyle="--", color=color)
        axes[1].plot(epochs, train_acc, label=f"{model_name} train", linestyle="-", color=color)
        axes[1].plot(epochs, val_acc, label=f"{model_name} val", linestyle="--", color=color)

    axes[0].set_title("Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[0].grid(True, alpha=0.3)

    axes[1].set_title("Accuracy")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Accuracy")
    axes[1].legend(loc="lower right", fontsize=8)
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=130)
    plt.close()
    print(f"[plot] Training curves saved to {output_path}")