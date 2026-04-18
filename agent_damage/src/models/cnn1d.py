"""1D-CNN classifier per outline: 2 conv layers + dense."""

from __future__ import annotations

import torch
import torch.nn as nn


class CNN1D(nn.Module):
    def __init__(self, input_dim: int = 23, num_classes: int = 3) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(1, 16, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(2),
            nn.Conv1d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(2),
        )
        # After two MaxPool1d(2), sequence length = input_dim // 4
        flat_len = (input_dim // 4) * 32
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(flat_len, 128),
            nn.ReLU(inplace=True),
            nn.Linear(128, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, input_dim) -> (B, 1, input_dim)
        x = x.unsqueeze(1)
        x = self.features(x)
        return self.classifier(x)

    @torch.no_grad()
    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        return torch.softmax(self.forward(x), dim=-1)
