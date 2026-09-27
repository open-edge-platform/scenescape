#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Batch roadside segment-then-instance inference → GNSS-eval JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from roadside_seg import RoadsideSegmenter  # noqa: E402


def _accumulate_n5(frames_dir: Path, frame_index: int, half: int) -> np.ndarray:
  chunks = []
  for fi in range(frame_index - half, frame_index + half + 1):
    path = frames_dir / f"{fi:06d}.npy"
    if path.is_file():
      arr = np.load(path)
      if arr.size:
        chunks.append(arr.astype(np.float32))
  if not chunks:
    return np.zeros((0, 5), dtype=np.float32)
  return np.concatenate(chunks, axis=0)


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--frames-dir", type=Path, required=True)
  ap.add_argument("--index", type=Path, required=True)
  ap.add_argument("--ckpt", type=Path, required=True)
  ap.add_argument("--start", type=int, default=2100)
  ap.add_argument("--end", type=int, default=4100)
  ap.add_argument("--stride", type=int, default=5)
  ap.add_argument("--accumulate-half-window", type=int, default=0)
  ap.add_argument("--cluster-distance-m", type=float, default=2.0)
  ap.add_argument("--min-score", type=float, default=0.35)
  ap.add_argument("--device", default="cuda")
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  index = {int(e["frame_index"]): e for e in json.loads(args.index.read_text())}
  seg = RoadsideSegmenter(args.ckpt, device=args.device)
  half = max(0, int(args.accumulate_half_window))
  args.output.parent.mkdir(parents=True, exist_ok=True)
  n_emit = 0
  with args.output.open("w") as out:
    for fi in range(args.start, args.end + 1, args.stride):
      if half:
        frame = _accumulate_n5(args.frames_dir, fi, half)
      else:
        path = args.frames_dir / f"{fi:06d}.npy"
        frame = np.load(path).astype(np.float32) if path.is_file() else np.zeros(
          (0, 5), dtype=np.float32)
      instances = seg.predict_instances(
        frame,
        cluster_distance_m=args.cluster_distance_m,
        min_score=args.min_score,
      )
      objects = [{
        "id": i + 1,
        "category": inst.category,
        "translation": inst.translation,
        "size": [0.6, 0.6, 1.7] if inst.category == "person" else [2.0, 1.5, 1.5],
        "confidence": inst.confidence,
        "n_points": inst.n_points,
      } for i, inst in enumerate(instances)]
      entry = index.get(fi, {})
      out.write(json.dumps({
        "frame_index": fi,
        "timestamp": entry.get("timestamp"),
        "objects": objects,
        "method": "roadside_segment_instance",
        "accumulate_half_window": half,
      }) + "\n")
      n_emit += 1
  print(f"wrote {n_emit} frames → {args.output}", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
