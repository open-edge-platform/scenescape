#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared VIDETEC (N,5) → VoD-style RadarPillars (N,7) PCD helpers."""

from __future__ import annotations

import numpy as np


def videtec_to_pcd(frame: np.ndarray) -> np.ndarray:
  """(N,5) range/doppler/az/el/mag → (N,7) x,y,z,rcs,v_r,v_r_comp,time."""
  frame = np.asarray(frame, dtype=np.float32)
  if frame.size == 0:
    return np.zeros((0, 7), dtype=np.float32)
  r, d, az, el, mag = frame.T
  az_r = np.deg2rad(az)
  el_r = np.deg2rad(el)
  cos_el = np.cos(el_r)
  x = r * cos_el * np.cos(az_r)
  y = r * cos_el * np.sin(az_r)
  z = r * np.sin(el_r)
  # Without ego motion, compensated radial velocity ≈ measured Doppler.
  return np.stack([x, y, z, mag, d, d, np.zeros_like(d)], axis=1).astype(np.float32)
