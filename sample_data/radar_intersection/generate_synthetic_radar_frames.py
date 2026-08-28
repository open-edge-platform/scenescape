#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Generate synthetic radar frames for the radar DNN demo.

Writes:
  - VIDETEC-style ``frames/%06d.npy`` (N,5) for offline Python tooling
  - VoD-style ``pcd_bin/%06d.bin`` float32 (N,7) for
    ``g3dlidarparse point-features=7 ! g3dinference model-type=radarpillars``
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def make_videtec_frame(rng: np.random.Generator, clusters: list[tuple]) -> np.ndarray:
  parts = []
  for center_r, center_az, n, mag0 in clusters:
    f = np.zeros((n, 5), np.float32)
    f[:, 0] = center_r + rng.normal(0, 0.35, n)
    f[:, 1] = rng.normal(1.0, 0.25, n)
    f[:, 2] = center_az + rng.normal(0, 1.2, n)
    f[:, 3] = rng.normal(0.0, 0.4, n)
    f[:, 4] = mag0 + rng.random(n) * 15.0
    parts.append(f)
  clutter_n = int(rng.integers(8, 24))
  c = np.zeros((clutter_n, 5), np.float32)
  c[:, 0] = rng.uniform(2.0, 45.0, clutter_n)
  c[:, 1] = rng.normal(0.0, 2.0, clutter_n)
  c[:, 2] = rng.uniform(-25.0, 25.0, clutter_n)
  c[:, 3] = rng.normal(0.0, 1.0, clutter_n)
  c[:, 4] = rng.uniform(2.0, 10.0, clutter_n)
  parts.append(c)
  return np.vstack(parts).astype(np.float32)


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
  return np.stack([x, y, z, mag, d, d, np.zeros_like(d)], axis=1).astype(np.float32)


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("-o", "--out-dir", required=True, help="Base radar_intersection dir")
  ap.add_argument("-n", "--num-frames", type=int, default=60)
  ap.add_argument("--seed", type=int, default=0)
  args = ap.parse_args()
  base = Path(args.out_dir)
  frames_dir = base / "frames"
  pcd_dir = base / "pcd_bin"
  frames_dir.mkdir(parents=True, exist_ok=True)
  pcd_dir.mkdir(parents=True, exist_ok=True)
  rng = np.random.default_rng(args.seed)
  for i in range(args.num_frames):
    t = i / max(1, args.num_frames - 1)
    clusters = [
      (8.0 + 4.0 * t, -5.0 + 2.0 * t, 28, 18.0),
      (18.0 + 6.0 * t, 12.0 - 3.0 * t, 24, 20.0),
      (12.0 + 2.0 * np.sin(t * 6), -15.0 + 8.0 * t, 20, 16.0),
    ]
    frame = make_videtec_frame(rng, clusters)
    np.save(frames_dir / f"{i:06d}.npy", frame)
    videtec_to_pcd(frame).tofile(pcd_dir / f"{i:06d}.bin")
  print(f"Wrote {args.num_frames} frames to {frames_dir} and {pcd_dir}")


if __name__ == "__main__":
  main()
