#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run OpenVINO OMZ person-vehicle-bike detector over staged camera JPEGs.

Writes one JSONL line per frame::
  {"frame_index": N, "w": W, "h": H, "dets": [{label, conf, x, y, w, h}, ...]}

Intended to run inside the radar-stream / DLSPS container where the OMZ model
is installed under ``MODELS_PATH``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import openvino as ov

LABELS = {1: "vehicle", 2: "person", 3: "cyclist"}
DEFAULT_MODEL = (
  "/home/pipeline-server/models/omz/"
  "person-vehicle-bike-detection-crossroad-1016/FP32/"
  "person-vehicle-bike-detection-crossroad-1016.xml"
)


def detect_frames(
    images_dir: Path,
    start: int,
    stop: int,
    model_xml: Path,
    device: str,
    score_threshold: float,
    out: Path,
) -> int:
  core = ov.Core()
  compiled = core.compile_model(core.read_model(str(model_xml)), device)
  inp = compiled.input(0)
  _, _, h, w = inp.shape
  out.parent.mkdir(parents=True, exist_ok=True)
  n = 0
  t0 = time.time()
  with out.open("w") as fh:
    for idx in range(start, stop + 1):
      path = images_dir / f"{idx:06d}.jpg"
      img = cv2.imread(str(path))
      if img is None:
        continue
      ih, iw = img.shape[:2]
      blob = cv2.resize(img, (w, h)).transpose(2, 0, 1)[None].astype(np.float32)
      res = compiled([blob])[compiled.output(0)].reshape(-1, 7)
      dets = []
      for _, lab, conf, x0, y0, x1, y1 in res:
        if conf < score_threshold:
          continue
        dets.append({
          "label": LABELS.get(int(lab), str(int(lab))),
          "conf": float(conf),
          "x": float(x0 * iw),
          "y": float(y0 * ih),
          "w": float((x1 - x0) * iw),
          "h": float((y1 - y0) * ih),
        })
      fh.write(json.dumps({"frame_index": idx, "w": iw, "h": ih, "dets": dets}) + "\n")
      n += 1
  print(f"done frames={n} elapsed={time.time() - t0:.1f}s -> {out}")
  return n


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--images-dir", type=Path, required=True,
                  help="Directory with %%06d.jpg")
  ap.add_argument("--start-index", type=int, default=3270)
  ap.add_argument("--stop-index", type=int, default=4100)
  ap.add_argument("--model", type=Path, default=Path(DEFAULT_MODEL))
  ap.add_argument("--device", default="CPU")
  ap.add_argument("--score-threshold", type=float, default=0.3)
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  detect_frames(
    args.images_dir, args.start_index, args.stop_index,
    args.model, args.device, args.score_threshold, args.output)


if __name__ == "__main__":
  main()
