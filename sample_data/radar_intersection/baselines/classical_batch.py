#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Batch classical cluster+track on VIDETEC (N,5) frames → GNSS-eval JSONL.

Runs the SceneScape ``radar/`` v1 perception sequentially over a frame window
(track continuity), optionally stacking neighbor frames before clustering
(``--accumulate-half-window``, same densify idea as RadarPillars H=5).

Dynamic clusters (|doppler| >= threshold) are labeled ``person`` so VRU
category filters in ``eval_radarpillars_gnss.py`` can score them; static /
slow clusters are ``vehicle``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_RADAR = _HERE.parents[2] / "radar"
if str(_RADAR) not in sys.path:
  sys.path.insert(0, str(_RADAR))

from radar_frame import as_frame, spherical_to_xyz  # noqa: E402
from radar_perception import RadarPerception  # noqa: E402


def _load_frame(path: Path) -> np.ndarray:
  if not path.is_file():
    return np.zeros((0, 5), dtype=np.float32)
  return as_frame(np.load(path))


def _accumulate_n5(frames_dir: Path, frame_index: int, half: int) -> np.ndarray:
  chunks = []
  for fi in range(frame_index - half, frame_index + half + 1):
    arr = _load_frame(frames_dir / f"{fi:06d}.npy")
    if arr.shape[0]:
      chunks.append(arr)
  if not chunks:
    return np.zeros((0, 5), dtype=np.float32)
  return np.concatenate(chunks, axis=0)


def _mean_abs_doppler(frame: np.ndarray, cluster_xyz: np.ndarray,
                      cluster_dist: float) -> float:
  """Mean |doppler| of detections belonging to a cluster centroid."""
  if frame.shape[0] == 0:
    return 0.0
  xyz = spherical_to_xyz(frame)
  dist = np.linalg.norm(xyz - cluster_xyz.reshape(1, 3), axis=1)
  mask = dist <= max(cluster_dist, 0.5)
  if not np.any(mask):
    i = int(np.argmin(dist))
    return float(abs(frame[i, 1]))
  return float(np.mean(np.abs(frame[mask, 1])))


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--frames-dir", type=Path, required=True)
  ap.add_argument("--index", type=Path, required=True)
  ap.add_argument("--start", type=int, default=2100)
  ap.add_argument("--end", type=int, default=4100)
  ap.add_argument("--stride", type=int, default=5)
  ap.add_argument("--accumulate-half-window", type=int, default=0)
  ap.add_argument("--cluster-distance-m", type=float, default=2.5)
  ap.add_argument("--track-distance-m", type=float, default=5.0)
  ap.add_argument("--doppler-person-mps", type=float, default=0.4,
                  help="|doppler| >= this → category person")
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  index = {int(e["frame_index"]): e for e in json.loads(args.index.read_text())}
  perc = RadarPerception(
    cluster_distance_m=args.cluster_distance_m,
    track_distance_m=args.track_distance_m,
  )
  half = max(0, int(args.accumulate_half_window))
  args.output.parent.mkdir(parents=True, exist_ok=True)
  n_emit = 0

  with args.output.open("w") as out:
    for fi in range(args.start, args.end + 1):
      if half:
        frame = _accumulate_n5(args.frames_dir, fi, half)
      else:
        frame = _load_frame(args.frames_dir / f"{fi:06d}.npy")
      xyz = spherical_to_xyz(frame)
      clusters = perc._cluster(xyz)
      tracks = perc._associate(clusters)

      if (fi - args.start) % args.stride != 0:
        continue

      objects = []
      for track in tracks:
        dop = _mean_abs_doppler(frame, track.position, args.cluster_distance_m)
        cat = "person" if dop >= args.doppler_person_mps else "vehicle"
        objects.append({
          "id": int(track.track_id),
          "category": cat,
          "translation": track.position.astype(float).tolist(),
          "size": [2.0, 1.5, 1.5] if cat == "vehicle" else [0.6, 0.6, 1.7],
          "confidence": float(track.confidence),
        })
      entry = index.get(fi, {})
      line = {
        "frame_index": fi,
        "timestamp": entry.get("timestamp"),
        "objects": objects,
        "method": "classical_cluster_track",
        "accumulate_half_window": half,
      }
      out.write(json.dumps(line) + "\n")
      n_emit += 1

  print(f"wrote {n_emit} frames → {args.output}", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
