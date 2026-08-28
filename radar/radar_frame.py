# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""VIDETEC-style radar live frame contract.

Canonical per-frame layout is float32 (N, 5):

  [range_m, doppler_mps, azimuth_deg, elevation_deg, magnitude]

Live UDP/SDK publishers and file replay share this layout. HDF5 archives
(e.g. VIDETEC-2) are converted offline into these frames.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

FRAME_DTYPE = np.float32
FRAME_COLUMNS = ("range_m", "doppler_mps", "azimuth_deg", "elevation_deg", "magnitude")
FRAME_WIDTH = len(FRAME_COLUMNS)


def as_frame(detections: Iterable | np.ndarray) -> np.ndarray:
  """Normalize detections to float32 (N, 5). Empty frames are (0, 5)."""
  arr = np.asarray(list(detections) if not isinstance(detections, np.ndarray) else detections,
                   dtype=FRAME_DTYPE)
  if arr.size == 0:
    return np.zeros((0, FRAME_WIDTH), dtype=FRAME_DTYPE)
  if arr.ndim == 1:
    if arr.shape[0] != FRAME_WIDTH:
      raise ValueError(f"Expected {FRAME_WIDTH} columns, got shape {arr.shape}")
    return arr.reshape(1, FRAME_WIDTH)
  if arr.ndim != 2 or arr.shape[1] != FRAME_WIDTH:
    raise ValueError(f"Expected (N, {FRAME_WIDTH}) frame, got shape {arr.shape}")
  return arr.astype(FRAME_DTYPE, copy=False)


def spherical_to_xyz(frame: np.ndarray) -> np.ndarray:
  """Convert (N, 5) detections to radar-local XYZ metres (N, 3).

  Convention: +X forward, +Y left, +Z up. Azimuth is degrees from +X toward +Y;
  elevation is degrees from the XY plane toward +Z.
  """
  frame = as_frame(frame)
  if frame.shape[0] == 0:
    return np.zeros((0, 3), dtype=FRAME_DTYPE)
  r = frame[:, 0]
  az = np.deg2rad(frame[:, 2])
  el = np.deg2rad(frame[:, 3])
  cos_el = np.cos(el)
  x = r * cos_el * np.cos(az)
  y = r * cos_el * np.sin(az)
  z = r * np.sin(el)
  return np.stack([x, y, z], axis=1).astype(FRAME_DTYPE)


def default_object_size() -> list[float]:
  """Default 3-D size (metres) for clustered radar tracks."""
  return [2.0, 1.5, 1.5]
