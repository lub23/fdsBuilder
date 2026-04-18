#!/usr/bin/env python3
"""绘制所有模型的训练曲线对比图"""

import sys

sys.path.insert(0, "/home/blue/code/fdsBuilder/agent_facility_damage")

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from src.data.generator import generate_dataset_from_facilities

from src.models.mlp import MLPDamageModel
from src.models.lstm import LSTMDamageModel
from src.models.gru import GRUDamageModel
from src.models.cnn1d import CNN1DDamageModel


def generate_balanced_data(n_samples=15000, seed=42):
    np.random.seed(seed)
    X, y = generate_dataset_from_facilities(n_samples=n_samples, seed=seed)

    low_idx = np.where(y == 0)[0]
    med_idx = np.where(y == 1)[0]
    high_idx = np.where(y == 2)[0]

    n_low = min(len(low_idx), 5000)
    n_med = min(len(med_idx), 3000)
    n_high = min(len(high_idx), 3000)

    selected_idx = np.concatenate(
        [
            np.random.choice(low_idx, n_low, replace=False),
            np.random.choice(med_idx, n_med, replace=False)
            if len(med_idx) > 0
            else med_idx,
            np.random.choice(high_idx, n_high, replace=False)
            if len(high_idx) > 0
            else high_idx,
        ]
    )

    return X[selected_idx], y[selected_idx]


def train_model(model_class, model_name, X_train, y_train, model_args):
    X_train_t = torch.FloatTensor(X_train)
    y_train_t = torch.LongTensor(y_train)

    model = model_class(**model_args)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()

    epochs = 30
    train_losses = []
    val_accuracies = []

    for epoch in range(epochs):
        model.train()
        total_loss = 0
        n_batches = 0

indices = torch.randperm(len(X_train_t))
        batch_size = 64
        model.train()
        for i in range(0, len(indices), batch_size):
            batch_idx = indices[i:i+batch_size]
            if len(batch_idx) <= 1:
                continue
            X_batch = X_train_t[batch_idx]
            y_batch = y_train_t[batch_idx]
            
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            n_batches += 1

        train_losses.append(total_loss / n_batches)

        if (epoch + 1) % 10 == 0:
            print(f"  Epoch {epoch + 1}")

    return model, train_losses


def main():
    print("=" * 60)
    print("训练并绘制多模型曲线")
    print("=" * 60)

    print("\n[1/3] 生成数据...")
    X, y = generate_balanced_data(n_samples=15000, seed=42)
    print(f"  数据: {len(X)} 样本")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    models = [
        (
            "MLP",
            MLPDamageModel,
            {"input_dim": 29, "hidden_dims": [128, 256, 128, 64], "num_classes": 3},
        ),
        (
            "LSTM",
            LSTMDamageModel,
            {"input_dim": 29, "hidden_dim": 64, "num_layers": 2, "num_classes": 3},
        ),
        (
            "GRU",
            GRUDamageModel,
            {"input_dim": 29, "hidden_dim": 64, "num_layers": 2, "num_classes": 3},
        ),
        (
            "CNN1D",
            CNN1DDamageModel,
            {"input_dim": 29, "channels": [32, 64], "num_classes": 3},
        ),
    ]

    all_results = {}

    print("\n[2/3] 训练模型...")
    for name, model_class, args in models:
        print(f"  {name}:")
        model, losses = train_model(model_class, name, X_train, y_train, args)
        all_results[name] = losses
        checkpoint = {"model_state_dict": model.state_dict()}
        torch.save(checkpoint, f"checkpoints/{name.lower()}_model.pt")

    print("\n[3/3] 绘制曲线...")
    plt.figure(figsize=(12, 5))

    plt.subplot(1, 2, 1)
    for name, losses in all_results.items():
        plt.plot(losses, label=name, linewidth=2)
    plt.xlabel("Epoch")
    plt.ylabel("Training Loss")
    plt.title("Training Loss Curve")
    plt.legend()
    plt.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("output/training_curves.png", dpi=150)
    plt.close()

    print("\n训练完成!")
    print("  保存: output/training_curves.png")
    print("  保存: checkpoints/*_model.pt")


if __name__ == "__main__":
    main()
