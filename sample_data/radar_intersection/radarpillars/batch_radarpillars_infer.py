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

_HERE = Path(__file__).resolve().parent
_RI_ROOT = _HERE.parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))
if str(_RI_ROOT / "prepare") not in sys.path:
  sys.path.insert(0, str(_RI_ROOT / "prepare"))

from radarpillars_infer import RadarPillarsOV  # noqa: E402
from videtec_accumulate import (  # noqa: E402
  accumulate_points,
  accumulate_points_causal,
  load_vod_points,
)


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--frames-dir", type=Path, required=True, help="frames/ with %%06d.npy + index.json")
  ap.add_argument("--config", type=Path,
                  default=_RI_ROOT / "model_installer/FP16/radarpillars_ov_config.json")
  ap.add_argument("--device", default="CPU")
  ap.add_argument("--score-threshold", type=float, default=0.03)
  ap.add_argument("--start-index", type=int, default=0)
  ap.add_argument("--stop-index", type=int, default=None)
  ap.add_argument("--stride", type=int, default=1)
  ap.add_argument(
    "--accumulate-half-window", type=int, default=0,
    help="Non-causal stack ±N (offline). Mutually exclusive with --accumulate-past.")
  ap.add_argument(
    "--accumulate-past", type=int, default=0,
    help="Causal stack past N frames + current (live path). past=10 ≈ H=5 span.")
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  if args.accumulate_half_window and args.accumulate_past:
    raise SystemExit("Use only one of --accumulate-half-window or --accumulate-past")
  index_path = args.frames_dir / "index.json"
  index = {int(e["frame_index"]): e for e in json.loads(index_path.read_text())}
  model = RadarPillarsOV(args.config, device=args.device)
  model.cfg["score_threshold"] = float(args.score_threshold)

  start = args.start_index
  stop = args.stop_index if args.stop_index is not None else max(index)
  half = max(0, int(args.accumulate_half_window))
  past = max(0, int(args.accumulate_past))
  args.output.parent.mkdir(parents=True, exist_ok=True)
  n_frames = 0
  n_objs = 0
  with args.output.open("w") as fh:
    for frame_index in range(start, stop + 1, max(1, args.stride)):
      path = args.frames_dir / f"{frame_index:06d}.npy"
      if not path.is_file():
        continue
      if past > 0:
        points = accumulate_points_causal(args.frames_dir, frame_index, past)
      elif half > 0:
        points = accumulate_points(args.frames_dir, frame_index, half)
      else:
        points = load_vod_points(path)
      objects = model.infer(points)
      entry = {
        "frame_index": frame_index,
        "timestamp": index.get(frame_index, {}).get("timestamp"),
        "objects": objects,
        "accumulate_half_window": half,
        "accumulate_past": past,
        "n_points": int(len(points)),
      }
      fh.write(json.dumps(entry) + "\n")
      n_frames += 1
      n_objs += len(objects)
      if n_frames % 50 == 0:
        print(f"... {n_frames} frames, {n_objs} objects", flush=True)
  densify = ""
  if past:
    densify = f" (causal past={past})"
  elif half:
    densify = f" (accumulate ±{half})"
  print(f"Wrote {n_frames} frames ({n_objs} objects) → {args.output}{densify}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
