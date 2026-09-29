# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Gantry-static multi-frame radar point accumulation for VIDETEC clouds.

Stacks neighbor frame indices in radar-local coordinates (static gantry —
no ego-motion compensation). Used by offline PyTorch/OV batch infer and by
densified ``pcd_bin`` generation for ``g3dinference`` playback.

Modes:
  * Non-causal ``accumulate_points`` — ``[fi - H, fi + H]`` (offline gate).
  * Causal ``accumulate_points_causal`` — ``[fi - past, fi]`` (live stream;
    ``past=10`` matches the span of H=5 without future frames).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def load_vod_points(path: Path) -> np.ndarray:
  """Load a frame as VoD-style float32 ``(N, 7)``."""
  if path.suffix == ".bin":
    return np.fromfile(path, dtype=np.float32).reshape(-1, 7)
  points = np.load(path)
  if points.ndim == 2 and points.shape[1] == 5:
    from videtec_to_pcd import videtec_to_pcd
    return videtec_to_pcd(points)
  if points.ndim == 2 and points.shape[1] >= 7:
    return points[:, :7].astype(np.float32)
  return np.fromfile(path, dtype=np.float32).reshape(-1, 7)


def accumulate_points(
  frames_dir: Path,
  frame_index: int,
  half_window: int,
  *,
  extension: str = ".npy",
) -> np.ndarray:
  """Concatenate VoD-style points across ``[fi-H, fi+H]``.

  ``extension`` is ``.npy`` (VIDETEC frames) or ``.bin`` (pcd_bin).
  """
  half = max(0, int(half_window))
  chunks = []
  for fi in range(frame_index - half, frame_index + half + 1):
    path = frames_dir / f"{fi:06d}{extension}"
    if not path.is_file():
      continue
    pts = load_vod_points(path)
    if pts.size:
      chunks.append(pts)
  if not chunks:
    return np.zeros((0, 7), dtype=np.float32)
  return np.concatenate(chunks, axis=0)


def accumulate_points_causal(
  frames_dir: Path,
  frame_index: int,
  past: int,
  *,
  extension: str = ".npy",
) -> np.ndarray:
  """Concatenate VoD-style points across ``[fi - past, fi]`` (no future).

  Matches ``g3dinference accumulate-past=N`` for offline quality gates.
  Use ``past=10`` to approximate non-causal H=5 (11-frame span).
  """
  past_n = max(0, int(past))
  chunks = []
  for fi in range(frame_index - past_n, frame_index + 1):
    path = frames_dir / f"{fi:06d}{extension}"
    if not path.is_file():
      continue
    pts = load_vod_points(path)
    if pts.size:
      chunks.append(pts)
  if not chunks:
    return np.zeros((0, 7), dtype=np.float32)
  return np.concatenate(chunks, axis=0)
