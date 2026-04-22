#!/usr/bin/env python3
"""Generate all visualization images for the three damage assessment reports."""

import json
import pickle
import sys
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import matplotlib as mpl
import numpy as np
import pandas as pd
import torch

mpl.rcParams['font.sans-serif'] = ['SimHei', 'WenQuanYi Micro Hei', 'DejaVu Sans']
mpl.rcParams['axes.unicode_minus'] = False

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.src.models.cnn1d import CNN1D
from agent_damage.src.models.mlp import MLP

ROOT = Path(__file__).resolve().parents[1]
CKPT_DIR = ROOT / "checkpoints"
OUTPUT_DIR = ROOT / "reports" / "images"
DATA_DIR = ROOT / "data"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_TO_FACILITIES = {
    "aerospace": ["Aerospace Facilities", "Airport Hangar"],
    "machinery": ["Machinery Manufacturing"],
    "metallurgical": ["Metallurgical Facilities"],
}

# ========== 1. Training Curves ==========
def plot_training_curves():
    summary_path = ROOT / "output" / "train_summary.json"
    with open(summary_path) as f:
        summary = json.load(f)

    histories = summary.get("histories", {})
    if not histories:
        print("No histories found, skipping training curves")
        return

    models_to_plot = ["mlp", "cnn1d"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Training Curves for Deep Learning Models", fontsize=14, fontweight='bold')

    colors = {"mlp": "#2E86AB", "cnn1d": "#A23B72"}

    for idx, model_name in enumerate(models_to_plot):
        if model_name not in histories:
            continue
        hist = histories[model_name]
        epochs = range(1, len(hist["train_loss"]) + 1)

        # Loss subplot
        ax_loss = axes[idx, 0]
        ax_loss.plot(epochs, hist["train_loss"], color=colors[model_name], label="Train", linewidth=1.5)
        ax_loss.plot(epochs, hist["val_loss"], color=colors[model_name], linestyle="--", label="Validation", linewidth=1.5)
        ax_loss.set_title(f"{model_name.upper()} Loss", fontsize=11)
        ax_loss.set_xlabel("Epoch")
        ax_loss.set_ylabel("Loss (Cross-Entropy)")
        ax_loss.legend()
        ax_loss.grid(True, alpha=0.3)

        # Accuracy subplot
        ax_acc = axes[idx, 1]
        ax_acc.plot(epochs, hist["train_acc"], color=colors[model_name], label="Train", linewidth=1.5)
        ax_acc.plot(epochs, hist["val_acc"], color=colors[model_name], linestyle="--", label="Validation", linewidth=1.5)
        ax_acc.set_title(f"{model_name.upper()} Accuracy", fontsize=11)
        ax_acc.set_xlabel("Epoch")
        ax_acc.set_ylabel("Accuracy")
        ax_acc.set_ylim([0.4, 1.02])
        ax_acc.legend()
        ax_acc.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "training_curves_all.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("Generated training_curves_all.png")

# ========== 2. Confusion Matrices ==========
def _load_models():
    models = {}

    scaler_path = CKPT_DIR / "scaler.pkl"
    if scaler_path.exists():
        with open(scaler_path, "rb") as f:
            models["scaler"] = pickle.load(f)

    svm_path = CKPT_DIR / "svm_model.pkl"
    if svm_path.exists():
        with open(svm_path, "rb") as f:
            models["svm"] = pickle.load(f)["model"]

    rf_path = CKPT_DIR / "rf_model.pkl"
    if rf_path.exists():
        with open(rf_path, "rb") as f:
            models["rf"] = pickle.load(f)["model"]

    mlp_path = CKPT_DIR / "mlp_model.pt"
    if mlp_path.exists():
        ckpt = torch.load(mlp_path, map_location="cpu", weights_only=False)
        m = MLP(input_dim=23)
        m.load_state_dict(ckpt["state_dict"])
        m.eval()
        models["mlp"] = m

    cnn1d_path = CKPT_DIR / "cnn1d_model.pt"
    if cnn1d_path.exists():
        ckpt = torch.load(cnn1d_path, map_location="cpu", weights_only=False)
        m = CNN1D(input_dim=23)
        m.load_state_dict(ckpt["state_dict"])
        m.eval()
        models["cnn1d"] = m

    return models

def _predict_proba(model, X):
    if isinstance(model, torch.nn.Module):
        with torch.no_grad():
            logits = model(torch.from_numpy(X.astype(np.float32)))
            return torch.softmax(logits, dim=1).cpu().numpy()
    return np.asarray(model.predict_proba(X))

def _predict(model, X):
    return np.argmax(_predict_proba(model, X), axis=1)

def plot_confusion_matrices():
    models = _load_models()
    if not models:
        print("No models found, skipping confusion matrices")
        return

    scaler = models.get("scaler")
    if not scaler:
        print("No scaler found, skipping confusion matrices")
        return

    df = pd.read_csv(DATA_DIR / "test.csv")
    feature_cols = [c for c in df.columns if c not in ["label", "facility_name", "building_name"]]
    X = scaler.transform(df[feature_cols].to_numpy(dtype=np.float32))
    y = df["label"].to_numpy()

    from sklearn.metrics import confusion_matrix

    fig, axes = plt.subplots(2, 3, figsize=(16, 11))
    fig.suptitle("Confusion Matrices on Test Set", fontsize=14, fontweight='bold')

    class_names = ["Low", "Medium", "High"]
    model_list = ["svm", "rf", "mlp", "cnn1d"]
    axes_flat = axes.flatten()

    all_probs = {}
    for name in model_list:
        if name in models:
            probs = _predict_proba(models[name], X)
            all_probs[name] = probs

    # Individual model confusion matrices
    for idx, name in enumerate(model_list):
        if name not in models:
            continue
        preds = _predict(models[name], X)
        cm = confusion_matrix(y, preds, labels=[0, 1, 2])
        cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)

        ax = axes_flat[idx]
        im = ax.imshow(cm_norm, cmap="Blues", vmin=0, vmax=1)
        ax.set_xticks([0, 1, 2])
        ax.set_yticks([0, 1, 2])
        ax.set_xticklabels(class_names)
        ax.set_yticklabels(class_names)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")
        ax.set_title(f"{name.upper()} (acc={np.mean(preds==y):.1%})")

        for i in range(3):
            for j in range(3):
                color = "white" if cm_norm[i, j] > 0.5 else "black"
                ax.text(j, i, f"{cm[i,j]}\n({cm_norm[i,j]:.1%})", ha="center", va="center", color=color, fontsize=9)

    # Ensemble confusion matrix
    if len(all_probs) >= 2:
        avg_probs = np.mean([all_probs[n] for n in all_probs], axis=0)
        ensemble_preds = np.argmax(avg_probs, axis=1)
        cm = confusion_matrix(y, ensemble_preds, labels=[0, 1, 2])
        cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)

        ax = axes_flat[4]
        im = ax.imshow(cm_norm, cmap="Greens", vmin=0, vmax=1)
        ax.set_xticks([0, 1, 2])
        ax.set_yticks([0, 1, 2])
        ax.set_xticklabels(class_names)
        ax.set_yticklabels(class_names)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")
        acc = np.mean(ensemble_preds == y)
        ax.set_title(f"Ensemble (acc={acc:.1%})")

        for i in range(3):
            for j in range(3):
                color = "white" if cm_norm[i, j] > 0.5 else "black"
                ax.text(j, i, f"{cm[i,j]}\n({cm_norm[i,j]:.1%})", ha="center", va="center", color=color, fontsize=9)

    # Hide the last subplot
    axes_flat[5].axis("off")

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "confusion_matrices_all.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("Generated confusion_matrices_all.png")

# ========== 3. Damage Distribution Plots ==========
def plot_damage_distributions(facility_filter: List[str] | None = None):
    """Plot damage level distribution for each facility type across heat flux levels."""
    from agent_damage.src.processing.facility_loader import load_core_facilities
    from agent_damage.src.processing.heat_source import AZIMUTH_OPTIONS, DURATION_OPTIONS, ELEVATION_OPTIONS, HEAT_FLUX_OPTIONS
    from agent_damage.src.data.labeling import simulate_damage_label
    from agent_damage.src.processing.occlusion import occluding_higher_count

    facilities = load_core_facilities()

    if facility_filter:
        facilities = [f for f in facilities if f.name in facility_filter]
        if not facilities:
            print(f"No facilities matched filter {facility_filter}, skipping damage distribution")
            return

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("毁伤等级分布随热通量变化趋势", fontsize=14, fontweight='bold')

    azimuth_fixed = 0  # 固定方位角

    for f_idx, facility in enumerate(facilities):
        row, col = f_idx // 2, f_idx % 2
        ax = axes[row, col]
        facility_name = facility.cn_name

        # For each building, compute damage level at different heat flux levels
        heat_fluxes = [f for f in HEAT_FLUX_OPTIONS if f >= 500]  # Focus on meaningful range

        for b_idx, building in enumerate(facility.buildings):
            damage_scores = []
            for hf in heat_fluxes:
                # Use a fixed moderate duration and elevation
                heat_source_params = [
                    (e, d, hf, azimuth_fixed)
                    for e in ELEVATION_OPTIONS
                    for d in DURATION_OPTIONS
                ]
                scores = []
                for e, d, hf_val, az in heat_source_params:
                    from agent_damage.src.processing.heat_source import HeatSourceParams
                    try:
                        hs = HeatSourceParams(elevation=e, azimuth=az, duration=d, heat_flux=hf_val)
                        occ = occluding_higher_count(facility, building, az)
                        label = simulate_damage_label(building, hs, occ)
                        scores.append(label.numeric)
                    except:
                        pass
                if scores:
                    damage_scores.append(np.mean(scores))
                else:
                    damage_scores.append(0)

            ax.plot([hf/1000 for hf in heat_fluxes], damage_scores,
                   marker='o', markersize=3, label=building.cn_name, alpha=0.7)

        ax.set_xlabel("热通量 (kW/m2)")
        ax.set_ylabel("平均毁伤等级 (0=Low, 1=Medium, 2=High)")
        ax.set_title(facility_name)
        ax.set_ylim([-0.1, 2.2])
        ax.set_yticks([0, 1, 2])
        ax.set_yticklabels(["Low", "Medium", "High"])
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7, loc='upper left')

    plt.tight_layout()
    output_name = "damage_distribution_by_facility.png"
    if facility_filter:
        safe_names = "_".join(f.name.replace(" ", "_") for f in facilities)
        output_name = f"damage_distribution_{safe_names}.png"
    plt.savefig(OUTPUT_DIR / output_name, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Generated {output_name}")

# ========== 4. Per-Model Training Curves ==========
def plot_mlp_curves():
    summary_path = ROOT / "output" / "train_summary.json"
    with open(summary_path) as f:
        summary = json.load(f)

    hist = summary.get("histories", {}).get("mlp", {})
    if not hist:
        return

    epochs = range(1, len(hist["train_loss"]) + 1)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle("MLP Training Curves", fontsize=13, fontweight='bold')

    ax1.plot(epochs, hist["train_loss"], color="#2E86AB", label="Train Loss", linewidth=1.5)
    ax1.plot(epochs, hist["val_loss"], color="#E94F37", label="Val Loss", linewidth=1.5, linestyle="--")
    ax1.set_xlabel("Epoch"); ax1.set_ylabel("Cross-Entropy Loss")
    ax1.legend(); ax1.grid(True, alpha=0.3); ax1.set_title("Loss")

    ax2.plot(epochs, hist["train_acc"], color="#2E86AB", label="Train Acc", linewidth=1.5)
    ax2.plot(epochs, hist["val_acc"], color="#E94F37", label="Val Acc", linewidth=1.5, linestyle="--")
    ax2.set_xlabel("Epoch"); ax2.set_ylabel("Accuracy")
    ax2.set_ylim([0.4, 1.02])
    ax2.legend(); ax2.grid(True, alpha=0.3); ax2.set_title("Accuracy")

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "mlp_training_curves.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("Generated mlp_training_curves.png")

def plot_cnn1d_curves():
    summary_path = ROOT / "output" / "train_summary.json"
    with open(summary_path) as f:
        summary = json.load(f)

    hist = summary.get("histories", {}).get("cnn1d", {})
    if not hist:
        return

    epochs = range(1, len(hist["train_loss"]) + 1)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle("CNN1D Training Curves", fontsize=13, fontweight='bold')

    ax1.plot(epochs, hist["train_loss"], color="#A23B72", label="Train Loss", linewidth=1.5)
    ax1.plot(epochs, hist["val_loss"], color="#E94F37", label="Val Loss", linewidth=1.5, linestyle="--")
    ax1.set_xlabel("Epoch"); ax1.set_ylabel("Cross-Entropy Loss")
    ax1.legend(); ax1.grid(True, alpha=0.3); ax1.set_title("Loss")

    ax2.plot(epochs, hist["train_acc"], color="#A23B72", label="Train Acc", linewidth=1.5)
    ax2.plot(epochs, hist["val_acc"], color="#E94F37", label="Val Acc", linewidth=1.5, linestyle="--")
    ax2.set_xlabel("Epoch"); ax2.set_ylabel("Accuracy")
    ax2.set_ylim([0.4, 1.02])
    ax2.legend(); ax2.grid(True, alpha=0.3); ax2.set_title("Accuracy")

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "cnn1d_training_curves.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("Generated cnn1d_training_curves.png")

# ========== 5. Combustible Distribution Heatmap ==========
def plot_combustible_heatmap():
    """Plot a heatmap of combustible category distribution across facility types."""
    from agent_damage.src.processing.combustible_stats import COMBUSTIBLE_CATEGORIES, classify_combustible_key, combustible_vector
    from agent_damage.src.processing.facility_loader import load_core_facilities
    import json

    facilities = load_core_facilities()

    # Compute average combustible vectors per building type
    categories = list(COMBUSTIBLE_CATEGORIES)
    building_names = []
    vectors = []

    for facility in facilities:
        for building in facility.buildings:
            vec = building.combustible_vector()
            vectors.append(vec)
            building_names.append(f"{facility.cn_name}\n{building.cn_name}")

    vectors = np.array(vectors)  # (n_buildings, 8)
    n_buildings = len(building_names)

    fig, ax = plt.subplots(figsize=(14, max(8, n_buildings * 0.5)))
    im = ax.imshow(vectors, cmap="YlOrRd", aspect='auto', vmin=0, vmax=0.5)

    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels([c.replace('_', '\n') for c in categories], fontsize=8)
    ax.set_yticks(range(n_buildings))
    ax.set_yticklabels(building_names, fontsize=7)
    ax.set_xlabel("可燃物类别", fontsize=10)
    ax.set_ylabel("建筑", fontsize=10)
    ax.set_title("各建筑可燃物类别分布热力图", fontsize=12, fontweight='bold')

    plt.colorbar(im, ax=ax, label="占比", shrink=0.6)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "combustible_heatmap.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("Generated combustible_heatmap.png")

# ========== 6. Building Size Scatter Plot ==========
def plot_building_sizes():
    """Plot scatter of building sizes for all facility types."""
    from agent_damage.src.processing.facility_loader import load_core_facilities

    facilities = load_core_facilities()
    colors = ['#2E86AB', '#A23B72', '#F6BD60', '#84A59D']

    fig, ax = plt.subplots(figsize=(12, 7))

    for f_idx, facility in enumerate(facilities):
        for b in facility.buildings:
            ax.scatter(b.length, b.width, s=b.height * 20,
                      color=colors[f_idx], alpha=0.7,
                      label=f"{facility.cn_name} - {b.cn_name}" if True else "")

    # Add labels for key buildings
    for f_idx, facility in enumerate(facilities):
        for b in facility.buildings:
            ax.annotate(b.cn_name, (b.length, b.width),
                       fontsize=6, alpha=0.8,
                       xytext=(3, 3), textcoords='offset points')

    ax.set_xlabel("长度 (m)", fontsize=10)
    ax.set_ylabel("宽度 (m)", fontsize=10)
    ax.set_title("各设施建筑尺寸分布（圆圈大小反映高度）", fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)

    # Create legend with unique entries
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), fontsize=6, loc='upper left', ncol=2)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "building_sizes.png", dpi=150, bbox_inches='tight')
    plt.close()
    print("Generated building_sizes.png")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", choices=["aerospace", "machinery", "metallurgical"], default=None)
    args = parser.parse_args()

    print("Generating all images...")
    plot_training_curves()
    plot_confusion_matrices()
    if args.report:
        if args.report in REPORT_TO_FACILITIES:
            plot_damage_distributions(REPORT_TO_FACILITIES[args.report])
        else:
            plot_damage_distributions()
    else:
        plot_damage_distributions()
    plot_mlp_curves()
    plot_cnn1d_curves()
    plot_combustible_heatmap()
    plot_building_sizes()
    print("\nAll images generated successfully!")