#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Torch-free roadside helpers (features, normalize, instance cluster).

Shared by OpenVINO runtime, export, and offline baselines.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CLASS_NAMES = ("background", "person", "vehicle")
NUM_CLASSES = len(CLASS_NAMES)
FEATURE_DIM = 6


def frame_to_features(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
  """(N,5) → XYZ (N,3) and model features (N,6)."""
  frame = np.asarray(frame, dtype=np.float32)
  if frame.size == 0:
    return np.zeros((0, 3), dtype=np.float32), np.zeros((0, FEATURE_DIM), dtype=np.float32)
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


def instances_to_objects(instances: list[Instance]) -> dict[str, list[dict]]:
  """SceneScape objects map from roadside instances."""
  objects: dict[str, list[dict]] = {}
  for i, inst in enumerate(instances):
    size = [0.6, 0.6, 1.7] if inst.category == "person" else [2.0, 1.5, 1.5]
    objects.setdefault(inst.category, []).append({
      "id": i + 1,
      "category": inst.category,
      "translation": inst.translation,
      "size": size,
      "confidence": float(inst.confidence),
      "source": "radar",
    })
  return objects
