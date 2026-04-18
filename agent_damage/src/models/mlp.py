"""MLP classifier: 3 hidden layers 128-64-32 (per outline)."""

from __future__ import annotations

import torch
import torch.nn as nn


class MLP(nn.Module):
    def __init__(
        self,
        input_dim: int = 23,
        hidden_dims: tuple = (128, 64, 32),
        num_classes: int = 3,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        layers = []
        prev = input_dim
        for h in hidden_dims:
            layers.extend(
                [nn.Linear(prev, h), nn.ReLU(inplace=True), nn.Dropout(dropout)]
            )
            prev = h
        layers.append(nn.Linear(prev, num_classes))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)

    @torch.no_grad()
    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        return torch.softmax(self.forward(x), dim=-1)
