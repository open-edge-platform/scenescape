#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Train TrackNet on Basketball triplets and export OpenVINO FP16."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from model import TrackNet, gaussian_heatmap


def _parse_args():
  here = Path(__file__).resolve().parent
  p = argparse.ArgumentParser(description=__doc__)
  p.add_argument("--manifest", default=str(here / "dataset" / "manifest.jsonl"))
  p.add_argument("--frames-dir", default=str(here / "dataset" / "frames"))
  p.add_argument("--outdir", default=str(here / ".." / "tracknet-basketball"))
  p.add_argument("--height", type=int, default=144)
  p.add_argument("--width", type=int, default=256)
  p.add_argument("--epochs", type=int, default=25)
  p.add_argument("--batch", type=int, default=4)
  p.add_argument("--lr", type=float, default=1e-3)
  p.add_argument("--sigma", type=float, default=3.0)
  p.add_argument("--pos-weight", type=float, default=40.0)
  p.add_argument("--val-frac", type=float, default=0.15)
  p.add_argument("--seed", type=int, default=0)
  p.add_argument("--device", default="cpu")
  p.add_argument("--num-workers", type=int, default=2)
  return p.parse_args()


class TripletDataset(Dataset):
  def __init__(self, rows, height, width, sigma, frames_dir: Path):
    self.rows = rows
    self.height = height
    self.width = width
    self.sigma = sigma
    self.frames_dir = Path(frames_dir)

  def __len__(self):
    return len(self.rows)

  def _frame(self, video, index):
    path = self.frames_dir / f"{Path(video).stem}_{index:05d}.jpg"
    frame = cv2.imread(str(path))
    if frame is None:
      raise RuntimeError(f"Missing cached frame {path}")
    return frame

  def __getitem__(self, idx):
    row = self.rows[idx]
    video = row["video"]
    t = int(row["frame_index"])
    frames = [self._frame(video, t - 1), self._frame(video, t), self._frame(video, t + 1)]
    rgbs = []
    for f in frames:
      rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
      rgb = cv2.resize(rgb, (self.width, self.height), interpolation=cv2.INTER_AREA)
      rgbs.append(rgb.astype(np.float32) / 255.0)
    x = np.concatenate(rgbs, axis=2)  # H,W,9
    x = np.transpose(x, (2, 0, 1))

    sx = self.width / float(row["width"])
    sy = self.height / float(row["height"])
    cx = float(row["cx"]) * sx
    cy = float(row["cy"]) * sy
    heat = gaussian_heatmap(self.height, self.width, cx, cy, self.sigma)
    return torch.from_numpy(x), heat.unsqueeze(0)


def _load_manifest(path):
  rows = []
  with open(path, encoding="utf-8") as fh:
    for line in fh:
      line = line.strip()
      if line:
        rows.append(json.loads(line))
  return rows


def _heatmap_loss(logits, target, pos_weight: float):
  """BCE with boosted weight on ball pixels so the net does not collapse to empty."""
  weight = 1.0 + (pos_weight - 1.0) * target
  return nn.functional.binary_cross_entropy_with_logits(
    logits, target, weight=weight
  )


def _peak_metrics(logits, heat, tol=4):
  prob = torch.sigmoid(logits)
  b = prob.shape[0]
  hit = 0
  for i in range(b):
    p = prob[i, 0]
    g = heat[i, 0]
    if float(g.max()) < 0.1:
      continue
    py, px = divmod(int(torch.argmax(p).item()), p.shape[1])
    gy, gx = divmod(int(torch.argmax(g).item()), g.shape[1])
    if abs(px - gx) <= tol and abs(py - gy) <= tol:
      hit += 1
  return hit, b


def main():
  args = _parse_args()
  random.seed(args.seed)
  torch.manual_seed(args.seed)

  rows = _load_manifest(args.manifest)
  if len(rows) < 20:
    print(f"Need more triplets in {args.manifest} (got {len(rows)})", file=sys.stderr)
    return 1
  random.shuffle(rows)
  n_val = max(1, int(len(rows) * args.val_frac))
  val_rows = rows[:n_val]
  train_rows = rows[n_val:]
  print(f"train={len(train_rows)} val={len(val_rows)} size={args.width}x{args.height}")

  frames_dir = Path(args.frames_dir)
  if not frames_dir.is_dir() or not any(frames_dir.glob("*.jpg")):
    print(
      f"Missing frame cache in {frames_dir}. Run cache_frames.py first.",
      file=sys.stderr,
    )
    return 1
  train_ds = TripletDataset(
    train_rows, args.height, args.width, args.sigma, frames_dir
  )
  val_ds = TripletDataset(
    val_rows, args.height, args.width, args.sigma, frames_dir
  )
  train_loader = DataLoader(
    train_ds, batch_size=args.batch, shuffle=True,
    num_workers=args.num_workers, pin_memory=False,
  )
  val_loader = DataLoader(
    val_ds, batch_size=args.batch, shuffle=False, num_workers=0,
  )

  device = torch.device(args.device)
  model = TrackNet().to(device)
  opt = torch.optim.Adam(model.parameters(), lr=args.lr)

  best_hit = -1.0
  outdir = Path(args.outdir)
  outdir.mkdir(parents=True, exist_ok=True)
  ckpt = outdir / "tracknet_best.pt"

  for epoch in range(1, args.epochs + 1):
    model.train()
    total = 0.0
    for x, y in train_loader:
      x, y = x.to(device), y.to(device)
      opt.zero_grad(set_to_none=True)
      logits = model(x)
      if logits.shape[-2:] != y.shape[-2:]:
        logits = nn.functional.interpolate(
          logits, size=y.shape[-2:], mode="bilinear", align_corners=False
        )
      loss = _heatmap_loss(logits, y, args.pos_weight)
      loss.backward()
      opt.step()
      total += float(loss.item()) * x.shape[0]
    train_loss = total / max(1, len(train_rows))

    model.eval()
    hits = 0
    count = 0
    vloss = 0.0
    with torch.no_grad():
      for x, y in val_loader:
        x, y = x.to(device), y.to(device)
        logits = model(x)
        if logits.shape[-2:] != y.shape[-2:]:
          logits = nn.functional.interpolate(
            logits, size=y.shape[-2:], mode="bilinear", align_corners=False
          )
        vloss += float(_heatmap_loss(logits, y, args.pos_weight).item()) * x.shape[0]
        h, b = _peak_metrics(logits, y)
        hits += h
        count += b
    hit_rate = hits / max(1, count)
    print(
      f"epoch {epoch:02d}/{args.epochs} loss={train_loss:.4f} "
      f"val_loss={vloss / max(1, len(val_rows)):.4f} peak@tol={hit_rate:.3f}",
      flush=True,
    )
    if hit_rate >= best_hit:
      best_hit = hit_rate
      torch.save({
        "model": model.state_dict(),
        "height": args.height,
        "width": args.width,
        "hit_rate": hit_rate,
        "epoch": epoch,
      }, ckpt)

  print(f"Best checkpoint → {ckpt} (peak@5px={best_hit:.3f})", flush=True)

  # Export ONNX then OpenVINO FP16
  state = torch.load(ckpt, map_location="cpu", weights_only=False)
  model = TrackNet()
  model.load_state_dict(state["model"])
  model.eval()
  h, w = int(state["height"]), int(state["width"])
  onnx_path = outdir / "tracknet_basketball.onnx"
  dummy = torch.zeros(1, 9, h, w)
  export_kwargs = dict(
    input_names=["frames"], output_names=["heatmap"], opset_version=17,
  )
  try:
    torch.onnx.export(model, dummy, str(onnx_path), dynamo=False, **export_kwargs)
  except TypeError:
    torch.onnx.export(model, dummy, str(onnx_path), **export_kwargs)
  print(f"ONNX → {onnx_path}", flush=True)

  import openvino as ov
  ov_model = ov.convert_model(str(onnx_path))
  xml_path = outdir / "tracknet_basketball.xml"
  ov.save_model(ov_model, str(xml_path), compress_to_fp16=True)
  meta = {
    "height": h,
    "width": w,
    "in_channels": 9,
    "label": "basketball",
    "hit_rate": best_hit,
    "epoch": state["epoch"],
  }
  (outdir / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
  print(f"OpenVINO FP16 → {xml_path}", flush=True)
  return 0


if __name__ == "__main__":
  sys.exit(main())
