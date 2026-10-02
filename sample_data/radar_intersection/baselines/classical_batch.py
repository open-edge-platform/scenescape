#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Batch classical cluster+track on VIDETEC (N,5) frames → GNSS-eval JSONL.

Runs the SceneScape ``radar/`` v1 perception sequentially over a frame window
(track continuity), optionally stacking neighbor frames before clustering
(``--accumulate-half-window``, same densify idea as RadarPillars H=5).

Person only when |doppler| is in the walking band *and* the cluster is compact
(extent / min points) *and* the track is stable — matches live
``classical_runtime`` so GNSS VRU eval reflects demo behavior. Everything else
is ``vehicle`` (prefer FP vehicles over phantom people on empty road).
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


def _cluster_stats(frame: np.ndarray, cluster_xyz: np.ndarray,
                   cluster_dist: float) -> tuple[float, int, float]:
  """Return (mean |doppler|, n_points, extent_xy) for members near centroid."""
  if frame.shape[0] == 0:
    return 0.0, 0, 0.0
  xyz = spherical_to_xyz(frame)
  dist = np.linalg.norm(xyz[:, :2] - cluster_xyz.reshape(1, 3)[:, :2], axis=1)
  mask = dist <= max(cluster_dist, 0.5)
  if not np.any(mask):
    i = int(np.argmin(dist))
    return float(abs(frame[i, 1])), 1, 0.0
  members = xyz[mask]
  mean_dop = float(np.mean(np.abs(frame[mask, 1])))
  extent = float(np.max(np.linalg.norm(members[:, :2] - cluster_xyz[:2], axis=1)))
  return mean_dop, int(mask.sum()), extent


def _label_person(
  mean_dop: float,
  n_points: int,
  extent_xy: float,
  confidence: float,
  *,
  dop_min: float,
  dop_max: float,
  max_extent: float,
  min_points: int,
  min_confidence: float,
) -> bool:
  return (
    dop_min <= mean_dop < dop_max
    and n_points >= min_points
    and extent_xy <= max_extent
    and confidence >= min_confidence
  )


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
  ap.add_argument("--doppler-person-mps", type=float, default=0.5)
  ap.add_argument("--doppler-person-max-mps", type=float, default=2.8)
  ap.add_argument("--person-max-extent-m", type=float, default=1.5)
  ap.add_argument("--person-min-points", type=int, default=1)
  ap.add_argument("--person-min-confidence", type=float, default=0.5)
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
  n_person = 0
  n_vehicle = 0

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
        dop, n_pts, extent = _cluster_stats(
          frame, track.position, args.cluster_distance_m)
        is_person = _label_person(
          dop, n_pts, extent, float(track.confidence),
          dop_min=args.doppler_person_mps,
          dop_max=args.doppler_person_max_mps,
          max_extent=args.person_max_extent_m,
          min_points=args.person_min_points,
          min_confidence=args.person_min_confidence,
        )
        cat = "person" if is_person else "vehicle"
        if is_person:
          n_person += 1
        else:
          n_vehicle += 1
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

  print(
    f"wrote {n_emit} frames → {args.output} "
    f"(person_objs={n_person} vehicle_objs={n_vehicle})",
    flush=True,
  )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
