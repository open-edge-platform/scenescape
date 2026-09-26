#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compare RadarPillars backends on identical (N,7) clouds.

Backends:
  - pytorch  : OpenPCDet RadarPillar ckpt (unoptimized reference)
  - ov       : host preproc + OpenVINO BEV/detect IR (``radarpillars_infer.py``)
  - optional gstreamer JSONL from a prior ``g3dinference`` run

Does **not** need VoD labels — reports detection count and matched XY/score
deltas between backends.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
  sys.path.insert(0, str(_ROOT))
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))


def _match(a: list[dict], b: list[dict], max_dist: float = 2.0):
  """Greedy match by XY distance; return list of (ia, ib, dist, dscore)."""
  if not a or not b:
    return []
  used_b = set()
  pairs = []
  for ia, oa in enumerate(a):
    ax, ay = oa["translation"][0], oa["translation"][1]
    best = None
    for ib, ob in enumerate(b):
      if ib in used_b:
        continue
      d = float(np.hypot(ax - ob["translation"][0], ay - ob["translation"][1]))
      if d > max_dist:
        continue
      if best is None or d < best[0]:
        best = (d, ib, ob)
    if best is None:
      continue
    d, ib, ob = best
    used_b.add(ib)
    pairs.append({
      "ia": ia, "ib": ib, "dist_m": d,
      "score_a": float(oa["confidence"]), "score_b": float(ob["confidence"]),
      "dscore": float(oa["confidence"] - ob["confidence"]),
      "cat_a": oa.get("category"), "cat_b": ob.get("category"),
    })
  return pairs


def _summary(name_a, objs_a, name_b, objs_b, match_dist):
  pairs = _match(objs_a, objs_b, max_dist=match_dist)
  dists = [p["dist_m"] for p in pairs]
  dsc = [p["dscore"] for p in pairs]
  return {
    f"n_{name_a}": len(objs_a),
    f"n_{name_b}": len(objs_b),
    "n_matched": len(pairs),
    "match_dist_m": match_dist,
    "matched_xy_err_m": {
      "mean": float(np.mean(dists)) if dists else None,
      "median": float(np.median(dists)) if dists else None,
      "p95": float(np.percentile(dists, 95)) if dists else None,
    },
    "matched_score_delta_a_minus_b": {
      "mean": float(np.mean(dsc)) if dsc else None,
      "median": float(np.median(dsc)) if dsc else None,
    },
    "pairs_sample": pairs[:5],
  }


def _load_points(path: Path) -> np.ndarray:
  if path.suffix == ".npy":
    arr = np.load(path)
    if arr.ndim == 2 and arr.shape[1] == 5:
      from videtec_to_pcd import videtec_to_pcd
      return videtec_to_pcd(arr)
    if arr.ndim == 2 and arr.shape[1] >= 7:
      return arr[:, :7].astype(np.float32)
    raise SystemExit(f"unsupported npy shape {arr.shape}")
  return np.fromfile(path, dtype=np.float32).reshape(-1, 7)


def _make_synthetic(seed: int = 0) -> np.ndarray:
  """Dense VoD-like cluster in front FOV for a control parity case."""
  rng = np.random.default_rng(seed)
  parts = []
  for cx, cy, n in [(8.0, 0.0, 40), (15.0, 4.0, 30), (12.0, -6.0, 25)]:
    pts = np.zeros((n, 7), np.float32)
    pts[:, 0] = cx + rng.normal(0, 0.4, n)
    pts[:, 1] = cy + rng.normal(0, 0.3, n)
    pts[:, 2] = -1.5 + rng.normal(0, 0.2, n)
    pts[:, 3] = rng.uniform(5, 25, n)
    pts[:, 4] = rng.normal(0.5, 0.2, n)
    pts[:, 5] = pts[:, 4]
    pts[:, 6] = 0.0
    parts.append(pts)
  clutter_n = 20
  c = np.zeros((clutter_n, 7), np.float32)
  c[:, 0] = rng.uniform(2, 40, clutter_n)
  c[:, 1] = rng.uniform(-20, 20, clutter_n)
  c[:, 2] = rng.uniform(-2, 0, clutter_n)
  c[:, 3] = rng.uniform(1, 8, clutter_n)
  parts.append(c)
  return np.vstack(parts).astype(np.float32)


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--bins", type=Path, nargs="*", default=None,
                  help="One or more .bin/.npy clouds (7-float or VIDETEC 5-col npy)")
  ap.add_argument("--synthetic", type=int, default=1,
                  help="Also run N synthetic control clouds (0 to disable)")
  ap.add_argument("--score-threshold", type=float, default=0.03)
  ap.add_argument("--match-dist", type=float, default=2.0)
  ap.add_argument("--ov-config", type=Path,
                  default=_ROOT / "model_installer/FP16/radarpillars_ov_config.json")
  ap.add_argument("--skip-pytorch", action="store_true")
  ap.add_argument("--skip-ov", action="store_true")
  ap.add_argument("--pytorch-cfg", type=Path, default=None)
  ap.add_argument("--pytorch-ckpt", type=Path, default=None)
  ap.add_argument("--pytorch-device", default="cuda:0")
  ap.add_argument("-o", "--output", type=Path, default=None)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  clouds = []
  for i in range(max(0, args.synthetic)):
    clouds.append((f"synthetic_{i}", _make_synthetic(seed=i)))
  for p in args.bins or []:
    clouds.append((str(p), _load_points(p)))

  if not clouds:
    raise SystemExit("no clouds: pass --bins and/or --synthetic N")

  torch_model = ov_model = None
  if not args.skip_pytorch:
    from pytorch_radarpillars_infer import RadarPillarsTorch, _RP
    cfg = args.pytorch_cfg or (_RP / "tools/cfgs/vod_models/vod_radarpillar_rot.yaml")
    ckpt = args.pytorch_ckpt or (_RP / "weights/radarpillar_vod_best_map52.56.pth")
    torch_model = RadarPillarsTorch(cfg, ckpt, device=args.pytorch_device)
  if not args.skip_ov:
    from radarpillars_infer import RadarPillarsOV
    ov_model = RadarPillarsOV(args.ov_config)
    ov_model.cfg["score_threshold"] = float(args.score_threshold)

  report = {"score_threshold": args.score_threshold, "frames": []}
  for name, pts in clouds:
    entry = {"name": name, "n_points": int(pts.shape[0])}
    objs_t = objs_o = None
    if torch_model is not None:
      objs_t = torch_model.infer(pts, score_threshold=args.score_threshold)
      entry["pytorch"] = {
        "n": len(objs_t),
        "top": sorted(objs_t, key=lambda o: -o["confidence"])[:5],
      }
    if ov_model is not None:
      objs_o = ov_model.infer(pts)
      entry["ov"] = {
        "n": len(objs_o),
        "top": sorted(objs_o, key=lambda o: -o["confidence"])[:5],
      }
    if objs_t is not None and objs_o is not None:
      entry["pytorch_vs_ov"] = _summary("pytorch", objs_t, "ov", objs_o, args.match_dist)
    report["frames"].append(entry)

  # Aggregate
  if torch_model is not None and ov_model is not None:
    n_t = sum(f["pytorch"]["n"] for f in report["frames"])
    n_o = sum(f["ov"]["n"] for f in report["frames"])
    n_m = sum(f["pytorch_vs_ov"]["n_matched"] for f in report["frames"])
    report["aggregate"] = {
      "frames": len(report["frames"]),
      "pytorch_dets": n_t,
      "ov_dets": n_o,
      "matched": n_m,
      "match_rate_vs_pytorch": (n_m / n_t) if n_t else None,
    }

  text = json.dumps(report, indent=2) + "\n"
  if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
  print(text)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
