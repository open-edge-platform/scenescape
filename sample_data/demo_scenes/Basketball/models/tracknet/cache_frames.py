#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Extract RGB JPEG frames referenced by the TrackNet manifest for fast training."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2


def main():
  here = Path(__file__).resolve().parent
  p = argparse.ArgumentParser(description=__doc__)
  p.add_argument("--manifest", default=str(here / "dataset" / "manifest.jsonl"))
  p.add_argument("--outdir", default=str(here / "dataset" / "frames"))
  args = p.parse_args()

  rows = [
    json.loads(line)
    for line in Path(args.manifest).read_text(encoding="utf-8").splitlines()
    if line.strip()
  ]
  needed = {}
  for row in rows:
    video = row["video"]
    t = int(row["frame_index"])
    needed.setdefault(video, set()).update({t - 1, t, t + 1})

  outdir = Path(args.outdir)
  outdir.mkdir(parents=True, exist_ok=True)
  total = 0
  for video, indices in needed.items():
    stem = Path(video).stem
    ordered = sorted(indices)
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
      print(f"Cannot open {video}", file=sys.stderr)
      return 1
    want = set(ordered)
    idx = 0
    while want:
      ok, frame = cap.read()
      if not ok:
        break
      if idx in want:
        path = outdir / f"{stem}_{idx:05d}.jpg"
        cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        want.remove(idx)
        total += 1
      idx += 1
    cap.release()
    if want:
      print(f"Missing frames in {video}: {sorted(want)[:10]}...", file=sys.stderr)
  print(f"Wrote {total} JPEGs → {outdir}", flush=True)
  return 0


if __name__ == "__main__":
  sys.exit(main())
