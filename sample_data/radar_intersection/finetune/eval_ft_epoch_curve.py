#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Epoch-wise VIDETEC GNSS curve for fine-tune checkpoints.

For each ``checkpoint_epoch_*.pth`` under ``--ckpt-dir``:
  1. batch-infer stride window → JSONL
  2. run ``eval_radarpillars_gnss.py`` (VRU + all-class)
  3. append a one-line summary to the curve JSON
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))

from radarpillar_env import radarpillar_python, resolve_radarpillar_root  # noqa: E402


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument(
    "--radarpillar-root", type=Path, default=None,
    help="RadarPillar checkout (default: $RADARPILLAR_ROOT or ../RadarPillar)")
  # Defaults filled after resolving root (see main).
  ap.add_argument("--ckpt-dir", type=Path, default=None)
  ap.add_argument("--cfg-file", type=Path, default=None)
  ap.add_argument("--python", type=Path, default=None)
  ap.add_argument("--frames-dir", type=Path,
                  default=_ROOT / "VIDETEC-2/converted/frames")
  ap.add_argument("--out-dir", type=Path, default=_ROOT / "VIDETEC-2")
  ap.add_argument("--start-index", type=int, default=3000)
  ap.add_argument("--stop-index", type=int, default=5000)
  ap.add_argument("--stride", type=int, default=5)
  ap.add_argument("--score-threshold", type=float, default=0.01)
  ap.add_argument("--epochs", type=int, nargs="*", default=None,
                  help="Subset of epochs (default: all checkpoint_epoch_*.pth)")
  return ap.parse_args(argv)


def _epoch_from_name(p: Path) -> int | None:
  # checkpoint_epoch_5.pth
  stem = p.stem
  if "epoch_" not in stem:
    return None
  try:
    return int(stem.split("epoch_")[-1])
  except ValueError:
    return None


def main(argv=None):
  args = parse_args(argv)
  rp = resolve_radarpillar_root(args.radarpillar_root)
  if args.ckpt_dir is None:
    args.ckpt_dir = (
      rp / "output/cfgs/vod_models/videtec_radarpillar_gantry/"
      "videtec_gantry_ft/ckpt")
  if args.cfg_file is None:
    args.cfg_file = rp / "tools/cfgs/vod_models/videtec_radarpillar_gantry.yaml"
  if args.python is None:
    args.python = radarpillar_python(rp)

  ckpts = sorted(args.ckpt_dir.glob("checkpoint_epoch_*.pth"), key=_epoch_from_name)
  if args.epochs:
    want = set(args.epochs)
    ckpts = [c for c in ckpts if _epoch_from_name(c) in want]
  if not ckpts:
    raise SystemExit(f"no checkpoints in {args.ckpt_dir}")

  index = args.frames_dir / "index.json"
  sensor = args.frames_dir / "sensor.json"
  gnss_glob = str(_ROOT / "VIDETEC-2/gnss/rosbag2_2025_10_09-14_43_55/*_gps.csv")
  py = str(args.python)
  batch = str(_HERE / "batch_pytorch_radarpillars_infer.py")
  eval_py = str(_ROOT / "radarpillars/eval_radarpillars_gnss.py")

  curve = {
    "score_threshold": args.score_threshold,
    "window": [args.start_index, args.stop_index, args.stride],
    "epochs": [],
  }

  for ckpt in ckpts:
    ep = _epoch_from_name(ckpt)
    print(f"\n===== epoch {ep} ({ckpt.name}) =====", flush=True)
    dets = args.out_dir / f"detections_stride5_pytorch_ft{ep}.jsonl"
    cmd_batch = [
      py, batch,
      "--cfg-file", str(args.cfg_file),
      "--ckpt", str(ckpt),
      "--frames-dir", str(args.frames_dir),
      "--start-index", str(args.start_index),
      "--stop-index", str(args.stop_index),
      "--stride", str(args.stride),
      "--score-threshold", str(args.score_threshold),
      "-o", str(dets),
    ]
    subprocess.check_call(cmd_batch)

    # Count dets
    n_frames = n_obj = nonempty = 0
    cats: dict[str, int] = {}
    for line in dets.open():
      e = json.loads(line)
      n_frames += 1
      objs = e.get("objects") or []
      n_obj += len(objs)
      if objs:
        nonempty += 1
      for o in objs:
        cats[o.get("category", "?")] = cats.get(o.get("category", "?"), 0) + 1

    entry = {
      "epoch": ep,
      "ckpt": str(ckpt),
      "detections": str(dets),
      "n_frames": n_frames,
      "n_nonempty": nonempty,
      "n_objects": n_obj,
      "categories": cats,
      "metrics": {},
    }

    for tag, cats_arg in [
      ("vru", "person,pedestrian,cyclist,bicycle"),
      ("all", "person,pedestrian,cyclist,bicycle,vehicle,car"),
    ]:
      out_m = args.out_dir / f"gnss_metrics_stride5_pytorch_ft{ep}_{tag}.json"
      # shell-expand gnss glob
      import glob as _glob
      gnss_files = _glob.glob(gnss_glob)
      if not gnss_files:
        raise SystemExit(f"no GNSS files for {gnss_glob}")
      cmd = [
        py, eval_py,
        "--index", str(index),
        "--detections", str(dets),
        "--gnss", gnss_files[0],
        "--sensor", str(sensor),
        "--videtec-origin", "--max-dt", "0.2",
        "--categories", cats_arg,
        "-o", str(out_m),
      ]
      subprocess.check_call(cmd)
      metrics = json.loads(out_m.read_text())
      entry["metrics"][tag] = {
        "recall_at_m": metrics.get("recall_at_m"),
        "position_error_m_when_matched": metrics.get("position_error_m_when_matched"),
        "frames_within_max_dt": metrics.get("frames_within_max_dt"),
      }
      r3 = (metrics.get("recall_at_m") or {}).get("3.0")
      print(f"  {tag} VRU/all @3m recall={r3} dets={n_obj}", flush=True)

    curve["epochs"].append(entry)

  out_curve = args.out_dir / "gnss_ft_epoch_curve.json"
  out_curve.write_text(json.dumps(curve, indent=2) + "\n")
  print(f"\nWrote {out_curve}", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
