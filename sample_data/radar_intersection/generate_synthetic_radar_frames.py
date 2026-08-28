#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generate synthetic VIDETEC-style (N,5) radar frames for the radar DNN demo.

Frames are float32 [range_m, doppler_mps, azimuth_deg, elevation_deg, magnitude]
with sparse clusters that RadarPillars OpenVINO typically turns into boxes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def make_frame(rng: np.random.Generator, clusters: list[tuple]) -> np.ndarray:
  parts = []
  for center_r, center_az, n, mag0 in clusters:
    f = np.zeros((n, 5), np.float32)
    f[:, 0] = center_r + rng.normal(0, 0.35, n)
    f[:, 1] = rng.normal(1.0, 0.25, n)
    f[:, 2] = center_az + rng.normal(0, 1.2, n)
    f[:, 3] = rng.normal(0.0, 0.4, n)
    f[:, 4] = mag0 + rng.random(n) * 15.0
    parts.append(f)
  # Clutter
  clutter_n = int(rng.integers(8, 24))
  c = np.zeros((clutter_n, 5), np.float32)
  c[:, 0] = rng.uniform(2.0, 45.0, clutter_n)
  c[:, 1] = rng.normal(0.0, 2.0, clutter_n)
  c[:, 2] = rng.uniform(-25.0, 25.0, clutter_n)
  c[:, 3] = rng.normal(0.0, 1.0, clutter_n)
  c[:, 4] = rng.uniform(2.0, 10.0, clutter_n)
  parts.append(c)
  return np.vstack(parts).astype(np.float32)


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("-o", "--out-dir", required=True)
  ap.add_argument("-n", "--num-frames", type=int, default=60)
  ap.add_argument("--seed", type=int, default=0)
  args = ap.parse_args()
  out = Path(args.out_dir)
  out.mkdir(parents=True, exist_ok=True)
  rng = np.random.default_rng(args.seed)
  # Three moving clusters (range drifts slowly across the sequence).
  for i in range(args.num_frames):
    t = i / max(1, args.num_frames - 1)
    clusters = [
      (8.0 + 4.0 * t, -5.0 + 2.0 * t, 28, 18.0),
      (18.0 + 6.0 * t, 12.0 - 3.0 * t, 24, 20.0),
      (12.0 + 2.0 * np.sin(t * 6), -15.0 + 8.0 * t, 20, 16.0),
    ]
    frame = make_frame(rng, clusters)
    np.save(out / f"{i:06d}.npy", frame)
  print(f"Wrote {args.num_frames} frames to {out}")


if __name__ == "__main__":
  main()
