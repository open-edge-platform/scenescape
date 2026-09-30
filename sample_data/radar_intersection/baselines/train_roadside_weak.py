#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Weakly supervise roadside PointNetSeg on VIDETEC using RTK-GNSS.

Label rule (per point, frames with GNSS association):
  - XY within ``--person-radius-m`` of GNSS → person
  - else if |doppler| >= threshold → vehicle
  - else → background

Trains only on frames that contain at least one person point. Global
min-max feature stats are fit on the training clouds.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_HERE) not in sys.path:
  sys.path.insert(0, str(_HERE))
if str(_ROOT / "radarpillars") not in sys.path:
  sys.path.insert(0, str(_ROOT / "radarpillars"))

from eval_radarpillars_gnss import (  # noqa: E402
  VIDETEC_UTM_EASTING_M,
  VIDETEC_UTM_NORTHING_M,
  VIDETEC_UTM_ZONE,
  _to_seconds,
  load_gnss_csv,
  world_to_radar_xy,
)
from roadside_seg import (  # noqa: E402
  NUM_CLASSES,
  PointNetSeg,
  frame_to_features,
  normalize_features,
)


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


def build_weak_samples(
  frames_dir: Path,
  index: list[dict],
  gnss: np.ndarray,
  sensor: dict,
  *,
  start: int,
  end: int,
  stride: int,
  half: int,
  person_radius_m: float,
  doppler_vehicle_mps: float,
  max_dt_s: float,
) -> list[dict]:
  index_by = {int(e["frame_index"]): e for e in index}
  g_t = gnss["t"]
  samples = []
  for fi in range(start, end + 1, stride):
    entry = index_by.get(fi)
    if entry is None or "timestamp" not in entry:
      continue
    t = float(_to_seconds(np.array([entry["timestamp"]], dtype=np.float64))[0])
    j = int(np.argmin(np.abs(g_t - t)))
    if abs(float(g_t[j] - t)) > max_dt_s:
      continue
    gx, gy = float(gnss["x"][j]), float(gnss["y"][j])
    rx, ry = world_to_radar_xy(np.array([gx]), np.array([gy]), sensor)
    gx, gy = float(rx[0]), float(ry[0])

    frame = _accumulate_n5(frames_dir, fi, half) if half else np.load(
      frames_dir / f"{fi:06d}.npy").astype(np.float32)
    if frame.ndim != 2 or frame.shape[0] == 0:
      continue
    xyz, feats = frame_to_features(frame)
    dxy = np.hypot(xyz[:, 0] - gx, xyz[:, 1] - gy)
    labels = np.zeros(xyz.shape[0], dtype=np.int64)
    labels[np.abs(frame[:, 1]) >= doppler_vehicle_mps] = 2
    labels[dxy <= person_radius_m] = 1
    if not np.any(labels == 1):
      continue
    samples.append({"feats": feats, "labels": labels, "frame_index": fi})
  return samples


class CloudDataset(Dataset):
  def __init__(self, samples: list[dict], norm_stats: dict):
    self.samples = samples
    self.norm_stats = norm_stats

  def __len__(self):
    return len(self.samples)

  def __getitem__(self, i):
    s = self.samples[i]
    feats, _ = normalize_features(s["feats"], self.norm_stats)
    return torch.from_numpy(feats), torch.from_numpy(s["labels"])


def collate_clouds(batch):
  feats = [b[0] for b in batch]
  labels = [b[1] for b in batch]
  return feats, labels


def fit_global_stats(samples: list[dict]) -> dict:
  if not samples:
    return {"lo": [0.0] * 6, "hi": [1.0] * 6}
  all_f = np.concatenate([s["feats"] for s in samples], axis=0)
  lo = all_f.min(axis=0)
  hi = all_f.max(axis=0)
  return {"lo": lo.tolist(), "hi": hi.tolist()}


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--frames-dir", type=Path, required=True)
  ap.add_argument("--index", type=Path, required=True)
  ap.add_argument("--gnss", type=Path, required=True)
  ap.add_argument("--sensor", type=Path, required=True)
  ap.add_argument("--train-start", type=int, default=1000)
  ap.add_argument("--train-end", type=int, default=6000)
  ap.add_argument("--exclude-start", type=int, default=None,
                  help="Inclusive start of frames to skip (e.g. eval window)")
  ap.add_argument("--exclude-end", type=int, default=None,
                  help="Inclusive end of frames to skip")
  ap.add_argument("--stride", type=int, default=2)
  ap.add_argument("--accumulate-half-window", type=int, default=5)
  ap.add_argument("--person-radius-m", type=float, default=3.0)
  ap.add_argument("--doppler-vehicle-mps", type=float, default=0.5)
  ap.add_argument("--max-dt", type=float, default=0.2)
  ap.add_argument("--epochs", type=int, default=40)
  ap.add_argument("--lr", type=float, default=1e-3)
  ap.add_argument("--batch-size", type=int, default=8)
  ap.add_argument("--device", default="cuda")
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  device = torch.device(args.device if torch.cuda.is_available() else "cpu")
  index = json.loads(args.index.read_text())
  sensor = json.loads(args.sensor.read_text())
  gnss = load_gnss_csv(
    args.gnss,
    origin_utm_easting=VIDETEC_UTM_EASTING_M,
    origin_utm_northing=VIDETEC_UTM_NORTHING_M,
    utm_zone=VIDETEC_UTM_ZONE,
  )
  half = max(0, int(args.accumulate_half_window))
  samples = build_weak_samples(
    args.frames_dir, index, gnss, sensor,
    start=args.train_start, end=args.train_end, stride=args.stride,
    half=half, person_radius_m=args.person_radius_m,
    doppler_vehicle_mps=args.doppler_vehicle_mps, max_dt_s=args.max_dt,
  )
  if args.exclude_start is not None and args.exclude_end is not None:
    lo, hi = int(args.exclude_start), int(args.exclude_end)
    before = len(samples)
    samples = [s for s in samples if not (lo <= int(s["frame_index"]) <= hi)]
    print(f"excluded [{lo},{hi}]: {before} → {len(samples)} samples", flush=True)
  print(f"weak samples with person support: {len(samples)}", flush=True)
  if len(samples) < 10:
    raise SystemExit("too few weak-labeled clouds; widen train window or radius")

  # Hold out every 5th sample for a tiny val loss print.
  train_s = [s for i, s in enumerate(samples) if i % 5 != 0]
  val_s = [s for i, s in enumerate(samples) if i % 5 == 0]
  stats = fit_global_stats(train_s)
  train_loader = DataLoader(
    CloudDataset(train_s, stats), batch_size=args.batch_size, shuffle=True,
    collate_fn=collate_clouds)
  model = PointNetSeg().to(device)
  opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
  # Class weights: person rare
  counts = np.zeros(NUM_CLASSES, dtype=np.float64)
  for s in train_s:
    for c in range(NUM_CLASSES):
      counts[c] += np.sum(s["labels"] == c)
  weights = counts.sum() / np.maximum(counts, 1.0)
  weights = weights / weights.mean()
  w = torch.tensor(weights, dtype=torch.float32, device=device)
  print(f"class counts {counts.tolist()} weights {weights.tolist()}", flush=True)

  best_val = math.inf
  best_state = None
  for epoch in range(1, args.epochs + 1):
    model.train()
    total, npts = 0.0, 0
    for feats_list, labels_list in train_loader:
      opt.zero_grad()
      loss = 0.0
      for feats, labels in zip(feats_list, labels_list):
        feats = feats.to(device)
        labels = labels.to(device)
        logits = model(feats)
        loss = loss + F.cross_entropy(logits, labels, weight=w)
        npts += int(labels.numel())
      loss = loss / max(len(feats_list), 1)
      loss.backward()
      torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
      opt.step()
      total += float(loss.item()) * len(feats_list)
    # val
    model.eval()
    vloss, vbatches = 0.0, 0
    with torch.no_grad():
      for s in val_s:
        feats, _ = normalize_features(s["feats"], stats)
        logits = model(torch.from_numpy(feats).to(device))
        labels = torch.from_numpy(s["labels"]).to(device)
        vloss += float(F.cross_entropy(logits, labels, weight=w).item())
        vbatches += 1
    vloss = vloss / max(vbatches, 1)
    print(f"epoch {epoch:03d} train_loss={total / max(len(train_loader), 1):.4f} "
          f"val_loss={vloss:.4f}", flush=True)
    if vloss < best_val:
      best_val = vloss
      best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

  args.output.parent.mkdir(parents=True, exist_ok=True)
  torch.save({
    "model": best_state if best_state is not None else model.state_dict(),
    "norm_stats": stats,
    "meta": {
      "train_samples": len(train_s),
      "val_samples": len(val_s),
      "accumulate_half_window": half,
      "person_radius_m": args.person_radius_m,
      "best_val_loss": best_val,
      "class_counts": counts.tolist(),
      # Provenance for commercial-safe path (no RoadsideRadar / CC BY-NC-SA data).
      "train_data": "VIDETEC-2",
      "train_data_license": "CC BY 4.0",
      "train_data_attribution": (
        "VIDETEC-2, Zenodo https://zenodo.org/records/17799385, CC BY 4.0"
      ),
      "labeling": "weak GNSS (person radius); no RoadsideRadar / INFRA-3DRC labels",
      "code_license": "Apache-2.0",
      "excludes_datasets": [
        "RoadsideRadar (CC BY-NC-SA 4.0 — non-commercial)",
      ],
      "train_start": args.train_start,
      "train_end": args.train_end,
      "exclude_start": args.exclude_start,
      "exclude_end": args.exclude_end,
      "frames_dir": str(args.frames_dir),
      "gnss": str(args.gnss),
    },
  }, args.output)
  print(f"saved {args.output} best_val={best_val:.4f}", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
