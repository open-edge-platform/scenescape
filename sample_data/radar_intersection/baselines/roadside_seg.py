#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Roadside-style segment-then-instance baseline for sparse gantry radar.

Inspired by RoadsideRadar (Bhanderi et al., Sci. Rep. 2025): semantic
segmentation of the (N,5) point cloud, then class-aware instance formation
that **keeps single-point objects**. Architecture is a compact PointNet-style
MLP (not the full upstream training stack); weights are trained on VIDETEC
with GNSS weak labels (see ``train_roadside_weak.py``).

Point features (6): x, y, z, doppler, magnitude, |doppler|.
Classes: 0=background, 1=person, 2=vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

CLASS_NAMES = ("background", "person", "vehicle")
NUM_CLASSES = len(CLASS_NAMES)


def frame_to_features(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
  """(N,5) → XYZ (N,3) and model features (N,6)."""
  frame = np.asarray(frame, dtype=np.float32)
  if frame.size == 0:
    return np.zeros((0, 3), dtype=np.float32), np.zeros((0, 6), dtype=np.float32)
  r = frame[:, 0]
  dop = frame[:, 1]
  az = np.deg2rad(frame[:, 2])
  el = np.deg2rad(frame[:, 3])
  mag = frame[:, 4]
  cos_el = np.cos(el)
  x = r * cos_el * np.cos(az)
  y = r * cos_el * np.sin(az)
  z = r * np.sin(el)
  xyz = np.stack([x, y, z], axis=1).astype(np.float32)
  feats = np.stack([x, y, z, dop, mag, np.abs(dop)], axis=1).astype(np.float32)
  return xyz, feats


def normalize_features(feats: np.ndarray,
                       stats: dict | None = None) -> tuple[np.ndarray, dict]:
  """Per-cloud min-max normalize (paper-style); return stats if computed."""
  if feats.shape[0] == 0:
    return feats, stats or {}
  if stats is None:
    lo = feats.min(axis=0)
    hi = feats.max(axis=0)
    stats = {"lo": lo.tolist(), "hi": hi.tolist()}
  else:
    lo = np.asarray(stats["lo"], dtype=np.float32)
    hi = np.asarray(stats["hi"], dtype=np.float32)
  span = np.maximum(hi - lo, 1e-3)
  return ((feats - lo) / span).astype(np.float32), stats


class PointNetSeg(nn.Module):
  """Shared-MLP PointNet segmentation with global max-pool context."""

  def __init__(self, in_dim: int = 6, num_classes: int = NUM_CLASSES):
    super().__init__()
    self.mlp1 = nn.Sequential(
      nn.Linear(in_dim, 64), nn.LayerNorm(64), nn.LeakyReLU(0.1),
      nn.Linear(64, 64), nn.LayerNorm(64), nn.LeakyReLU(0.1),
    )
    self.mlp2 = nn.Sequential(
      nn.Linear(64, 128), nn.LayerNorm(128), nn.LeakyReLU(0.1),
      nn.Linear(128, 256), nn.LayerNorm(256), nn.LeakyReLU(0.1),
    )
    self.head = nn.Sequential(
      nn.Linear(64 + 256, 128), nn.LayerNorm(128), nn.LeakyReLU(0.1),
      nn.Dropout(0.2),
      nn.Linear(128, 64), nn.LeakyReLU(0.1),
      nn.Linear(64, num_classes),
    )

  def forward(self, x: torch.Tensor) -> torch.Tensor:
    # x: (N, C) — callers skip empty clouds (keeps OV/ONNX export clean).
    local = self.mlp1(x)
    mid = self.mlp2(local)
    glob = mid.max(dim=0, keepdim=True).values.expand(mid.shape[0], -1)
    return self.head(torch.cat([local, glob], dim=-1))


@dataclass
class Instance:
  category: str
  translation: list[float]
  confidence: float
  n_points: int


def class_aware_instances(
  xyz: np.ndarray,
  labels: np.ndarray,
  scores: np.ndarray,
  *,
  cluster_distance_m: float = 2.0,
  min_score: float = 0.35,
) -> list[Instance]:
  """Greedy distance clustering per foreground class; keep 1-point objects."""
  out: list[Instance] = []
  for cls_id, cat in enumerate(CLASS_NAMES):
    if cls_id == 0:
      continue
    mask = (labels == cls_id) & (scores >= min_score)
    idxs = np.where(mask)[0]
    if idxs.size == 0:
      continue
    remaining = idxs.tolist()
    while remaining:
      seed = remaining.pop(0)
      members = [seed]
      changed = True
      while changed:
        changed = False
        centroid = xyz[members].mean(axis=0)
        keep = []
        for i in remaining:
          if float(np.linalg.norm(xyz[i] - centroid)) <= cluster_distance_m:
            members.append(i)
            changed = True
          else:
            keep.append(i)
        remaining = keep
      conf = float(np.mean(scores[members]))
      cen = xyz[members].mean(axis=0)
      out.append(Instance(
        category=cat,
        translation=cen.astype(float).tolist(),
        confidence=conf,
        n_points=len(members),
      ))
  return out


class RoadsideSegmenter:
  def __init__(self, ckpt: str | Path | None = None, device: str = "cpu"):
    self.device = torch.device(device)
    self.model = PointNetSeg().to(self.device)
    self.norm_stats: dict | None = None
    if ckpt is not None:
      payload = torch.load(ckpt, map_location=self.device, weights_only=False)
      self.model.load_state_dict(payload["model"])
      self.norm_stats = payload.get("norm_stats")
    self.model.eval()

  def predict_instances(
    self,
    frame: np.ndarray,
    *,
    cluster_distance_m: float = 2.0,
    min_score: float = 0.35,
  ) -> list[Instance]:
    xyz, feats = frame_to_features(frame)
    if xyz.shape[0] == 0:
      return []
    feats_n, _ = normalize_features(feats, self.norm_stats)
    with torch.no_grad():
      logits = self.model(torch.from_numpy(feats_n).to(self.device))
      prob = F.softmax(logits, dim=-1).cpu().numpy()
    labels = prob.argmax(axis=1)
    scores = prob.max(axis=1)
    return class_aware_instances(
      xyz, labels, scores,
      cluster_distance_m=cluster_distance_m, min_score=min_score)
