# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Lightweight TrackNet-style spatiotemporal ball heatmap model.

Three consecutive RGB frames (9 channels) → single-channel ball heatmap.
Architecture follows TrackNetV2's encoder–decoder idea at a smaller width so
CPU fine-tuning on the Basketball demo clips stays practical.
"""

from __future__ import annotations

import torch
from torch import nn


class _ConvBlock(nn.Module):
  def __init__(self, cin: int, cout: int, layers: int = 2):
    super().__init__()
    mods = []
    for i in range(layers):
      mods.extend([
        nn.Conv2d(cin if i == 0 else cout, cout, 3, padding=1, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
      ])
    self.net = nn.Sequential(*mods)

  def forward(self, x):
    return self.net(x)


class TrackNet(nn.Module):
  """TrackNetV2-inspired U-Net for sports-ball heatmaps."""

  def __init__(self, in_channels: int = 9, out_channels: int = 1):
    super().__init__()
    self.down1 = _ConvBlock(in_channels, 32, 2)
    self.pool1 = nn.MaxPool2d(2, 2)
    self.down2 = _ConvBlock(32, 64, 2)
    self.pool2 = nn.MaxPool2d(2, 2)
    self.down3 = _ConvBlock(64, 128, 3)
    self.pool3 = nn.MaxPool2d(2, 2)
    self.bridge = _ConvBlock(128, 256, 3)

    self.up3 = nn.ConvTranspose2d(256, 128, 2, stride=2)
    self.dec3 = _ConvBlock(256, 128, 2)
    self.up2 = nn.ConvTranspose2d(128, 64, 2, stride=2)
    self.dec2 = _ConvBlock(128, 64, 2)
    self.up1 = nn.ConvTranspose2d(64, 32, 2, stride=2)
    self.dec1 = _ConvBlock(64, 32, 2)
    self.head = nn.Conv2d(32, out_channels, 1)

  def forward(self, x: torch.Tensor) -> torch.Tensor:
    d1 = self.down1(x)
    d2 = self.down2(self.pool1(d1))
    d3 = self.down3(self.pool2(d2))
    b = self.bridge(self.pool3(d3))

    u3 = self.up3(b)
    if u3.shape[-2:] != d3.shape[-2:]:
      u3 = nn.functional.interpolate(
        u3, size=d3.shape[-2:], mode="bilinear", align_corners=False
      )
    u3 = self.dec3(torch.cat([u3, d3], dim=1))

    u2 = self.up2(u3)
    if u2.shape[-2:] != d2.shape[-2:]:
      u2 = nn.functional.interpolate(
        u2, size=d2.shape[-2:], mode="bilinear", align_corners=False
      )
    u2 = self.dec2(torch.cat([u2, d2], dim=1))

    u1 = self.up1(u2)
    if u1.shape[-2:] != d1.shape[-2:]:
      u1 = nn.functional.interpolate(
        u1, size=d1.shape[-2:], mode="bilinear", align_corners=False
      )
    u1 = self.dec1(torch.cat([u1, d1], dim=1))
    return self.head(u1)


def gaussian_heatmap(
  height: int,
  width: int,
  cx: float,
  cy: float,
  sigma: float = 2.5,
) -> torch.Tensor:
  """Unit-peak Gaussian heatmap at (cx, cy) in pixel coordinates."""
  ys = torch.arange(height, dtype=torch.float32).view(-1, 1)
  xs = torch.arange(width, dtype=torch.float32).view(1, -1)
  heat = torch.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2.0 * sigma ** 2))
  return heat
