# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Gantry-static multi-frame radar point accumulation for VIDETEC clouds.

Stacks neighbor frame indices ``[fi - H, fi + H]`` in radar-local coordinates
(static gantry — no ego-motion compensation). Used by offline PyTorch/OV batch
infer and by densified ``pcd_bin`` generation for ``g3dinference`` playback.
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
