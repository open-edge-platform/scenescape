#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Build TrackNet training triplets from Basketball demos + YOLO FT ball boxes.

Runs OpenVINO YOLOv8s-FT on consecutive video frames, then writes:
  dataset/manifest.jsonl  — one JSON object per triplet
  (optional) cached RGB stacks / heatmaps are generated on the fly in train.py

Pseudo-labels fill short YOLO gaps (linear center interpolation) so the model
sees bounce-like motion while keeping size supervision out of scope (heatmap
center only).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from openvino import Core


def _parse_args():
  here = Path(__file__).resolve().parent
  root = here.parents[4]
  p = argparse.ArgumentParser(description=__doc__)
  p.add_argument(
    "--videos",
    nargs="+",
    default=[
      str(root / "sample_data/demo_scenes/Basketball/video/cam1.mp4"),
      str(root / "sample_data/demo_scenes/Basketball/video/cam2.mp4"),
    ],
  )
  p.add_argument(
    "--yolo-xml",
    default=str(
      root / "sample_data/demo_scenes/Basketball/models/"
      "yolov8s-ft-person-basketball/yolov8s-ft-person-basketball.xml"
    ),
  )
  p.add_argument("--device", default="GPU")
  p.add_argument("--ball-class", type=int, default=1, help="YOLO class id for basketball")
  p.add_argument("--conf", type=float, default=0.25)
  p.add_argument("--imgsz", type=int, default=640)
  p.add_argument("--gap-fill", type=int, default=4, help="Max frames to interpolate across")
  p.add_argument("--out", default=str(here / "dataset" / "manifest.jsonl"))
  p.add_argument("--stride", type=int, default=1, help="Keep every Nth labeled triplet")
  return p.parse_args()


def _letterbox(img, size):
  h, w = img.shape[:2]
  scale = min(size / h, size / w)
  nh, nw = int(round(h * scale)), int(round(w * scale))
  resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
  canvas = np.full((size, size, 3), 114, dtype=np.uint8)
  top = (size - nh) // 2
  left = (size - nw) // 2
  canvas[top:top + nh, left:left + nw] = resized
  return canvas, scale, left, top


def _yolo_ball(compiled, img_bgr, ball_class, conf_thr, imgsz):
  lb, scale, left, top = _letterbox(img_bgr, imgsz)
  rgb = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
  tensor = np.transpose(rgb, (2, 0, 1))[None, ...]
  out = compiled([tensor])[compiled.output(0)]
  # YOLOv8: (1, 4+nc, N) or (1, N, 4+nc)
  pred = np.array(out)
  if pred.ndim != 3:
    return None
  if pred.shape[1] < pred.shape[2]:
    pred = pred[0].T
  else:
    pred = pred[0]
  if pred.shape[1] < 6:
    return None
  boxes = pred[:, :4]
  scores = pred[:, 4:]
  cls = np.argmax(scores, axis=1)
  conf = scores[np.arange(len(scores)), cls]
  mask = (cls == ball_class) & (conf >= conf_thr)
  if not np.any(mask):
    return None
  i = int(np.argmax(conf * mask))
  cx, cy, w, h = boxes[i]
  # undo letterbox
  cx = (cx - left) / scale
  cy = (cy - top) / scale
  w = w / scale
  h = h / scale
  return {
    "cx": float(cx),
    "cy": float(cy),
    "w": float(w),
    "h": float(h),
    "conf": float(conf[i]),
  }


def _interpolate_gaps(dets, gap_fill):
  """Fill short None runs by linear interpolation of cx,cy,w,h."""
  out = list(dets)
  n = len(out)
  i = 0
  while i < n:
    if out[i] is not None:
      i += 1
      continue
    j = i
    while j < n and out[j] is None:
      j += 1
    gap = j - i
    if gap <= gap_fill and i > 0 and j < n and out[i - 1] and out[j]:
      a, b = out[i - 1], out[j]
      for k in range(gap):
        t = (k + 1) / (gap + 1)
        out[i + k] = {
          "cx": a["cx"] * (1 - t) + b["cx"] * t,
          "cy": a["cy"] * (1 - t) + b["cy"] * t,
          "w": a["w"] * (1 - t) + b["w"] * t,
          "h": a["h"] * (1 - t) + b["h"] * t,
          "conf": min(a["conf"], b["conf"]) * 0.5,
          "pseudo": True,
        }
    i = j
  return out


def _process_video(path, compiled, args):
  cap = cv2.VideoCapture(str(path))
  if not cap.isOpened():
    raise RuntimeError(f"Cannot open {path}")
  frames = []
  dets = []
  idx = 0
  while True:
    ok, frame = cap.read()
    if not ok:
      break
    det = _yolo_ball(
      compiled, frame, args.ball_class, args.conf, args.imgsz
    )
    frames.append(frame)
    dets.append(det)
    idx += 1
    if idx % 50 == 0:
      print(f"  {path.name}: labeled {idx} frames", flush=True)
  cap.release()
  dets = _interpolate_gaps(dets, args.gap_fill)
  rows = []
  for t in range(1, len(frames) - 1):
    if dets[t] is None:
      continue
    if args.stride > 1 and (t % args.stride) != 0:
      continue
    # Prefer repo-relative paths so host training works after Docker labeling.
    try:
      video_path = str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
      video_path = str(path.resolve())
    rows.append({
      "video": video_path,
      "frame_index": t,
      "cx": dets[t]["cx"],
      "cy": dets[t]["cy"],
      "w": dets[t]["w"],
      "h": dets[t]["h"],
      "conf": dets[t]["conf"],
      "pseudo": bool(dets[t].get("pseudo", False)),
      "width": int(frames[t].shape[1]),
      "height": int(frames[t].shape[0]),
    })
  print(
    f"  {path.name}: {len(frames)} frames, {sum(d is not None for d in dets)} "
    f"ball labels, {len(rows)} triplets",
    flush=True,
  )
  # free frames; train.py re-reads by index
  del frames
  return rows


def main():
  args = _parse_args()
  xml = Path(args.yolo_xml)
  if not xml.is_file():
    print(f"Missing YOLO IR: {xml}", file=sys.stderr)
    return 1
  core = Core()
  device = args.device if args.device in core.available_devices else "CPU"
  print(f"Loading {xml} on {device}", flush=True)
  compiled = core.compile_model(core.read_model(str(xml)), device)

  out = Path(args.out)
  out.parent.mkdir(parents=True, exist_ok=True)
  n = 0
  with out.open("w", encoding="utf-8") as fh:
    for v in args.videos:
      path = Path(v)
      for row in _process_video(path, compiled, args):
        fh.write(json.dumps(row) + "\n")
        n += 1
  print(f"Wrote {n} triplets → {out}", flush=True)
  return 0


if __name__ == "__main__":
  sys.exit(main())
