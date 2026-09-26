#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Batch RadarPillars OpenVINO inference over converted VIDETEC frames/bins.

Writes JSONL compatible with ``eval_radarpillars_gnss.py``:
  {"frame_index": N, "timestamp": ..., "objects": [{translation, category, confidence, ...}]}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from radarpillars_infer import RadarPillarsOV  # noqa: E402


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--frames-dir", type=Path, required=True, help="frames/ with %%06d.npy + index.json")
  ap.add_argument("--config", type=Path,
                  default=_HERE / "model_installer/FP16/radarpillars_ov_config.json")
  ap.add_argument("--device", default="CPU")
  ap.add_argument("--score-threshold", type=float, default=0.03)
  ap.add_argument("--start-index", type=int, default=0)
  ap.add_argument("--stop-index", type=int, default=None)
  ap.add_argument("--stride", type=int, default=1)
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  index_path = args.frames_dir / "index.json"
  index = {int(e["frame_index"]): e for e in json.loads(index_path.read_text())}
  model = RadarPillarsOV(args.config, device=args.device)
  model.cfg["score_threshold"] = float(args.score_threshold)

  start = args.start_index
  stop = args.stop_index if args.stop_index is not None else max(index)
  args.output.parent.mkdir(parents=True, exist_ok=True)
  n_frames = 0
  n_objs = 0
  with args.output.open("w") as fh:
    for frame_index in range(start, stop + 1, max(1, args.stride)):
      path = args.frames_dir / f"{frame_index:06d}.npy"
      if not path.is_file():
        continue
      points = np.load(path)
      # Already (N,5) VIDETEC → convert; or load .bin if preferred.
      if points.ndim == 2 and points.shape[1] == 5:
        from videtec_to_pcd import videtec_to_pcd
        points = videtec_to_pcd(points)
      elif points.ndim == 2 and points.shape[1] == 7:
        points = points.astype(np.float32)
      else:
        # raw float dump
        points = np.fromfile(path, dtype=np.float32).reshape(-1, 7)
      objects = model.infer(points)
      entry = {
        "frame_index": frame_index,
        "timestamp": index.get(frame_index, {}).get("timestamp"),
        "objects": objects,
      }
      fh.write(json.dumps(entry) + "\n")
      n_frames += 1
      n_objs += len(objects)
      if n_frames % 50 == 0:
        print(f"... {n_frames} frames, {n_objs} objects", flush=True)
  print(f"Wrote {n_frames} frames ({n_objs} objects) → {args.output}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
