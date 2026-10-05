#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Run classical/roadside via gst-launch + gvametapublish, then reindex JSONL.

``gvametapublish`` may drop empty frames; this script maps published lines to
``start_index + i`` when counts match, otherwise fills gaps with empty object
lists and sets ``empty_frames_dropped=true``. Prefer
``baselines/classical_batch.py`` for exact classical indexing.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_LABEL = {0: "vehicle", 1: "person", 2: "cyclist"}

_MODE = {
  "classical": {
    "point_features": 5,
    "default_config": (
      "/home/pipeline-server/models/public/classical/classical_ov_config.json"),
    "default_data": (
      "/home/pipeline-server/videos/radar_intersection/frames_bin/%06d.bin"),
  },
  "roadside": {
    "point_features": 5,
    "default_config": (
      "/home/pipeline-server/models/public/roadside/FP16/roadside_ov_config.json"),
    "default_data": (
      "/home/pipeline-server/videos/radar_intersection/frames_bin/%06d.bin"),
  },
}


def _normalize(raw: dict) -> list[dict]:
  out = []
  for i, obj in enumerate(raw.get("objects") or []):
    bb = obj.get("bbox_3d") or {}
    if not bb:
      continue
    lid = int(obj.get("label_id", 0))
    cat = _LABEL.get(lid, obj.get("label") or obj.get("category") or "object")
    out.append({
      "id": int(obj.get("id", i + 1)),
      "category": str(cat).lower(),
      "confidence": float(obj.get("confidence", 0)),
      "translation": [float(bb["x"]), float(bb["y"]), float(bb["z"])],
      "size": [float(bb.get("l", 0.6)), float(bb.get("w", 0.6)), float(bb.get("h", 1.7))],
    })
  return out


def run(
  *,
  model_type: str,
  data_path: str,
  model_config: str,
  start_index: int,
  stop_index: int,
  device: str,
  score_threshold: float,
  output: Path,
) -> int:
  mode = _MODE[model_type]
  with tempfile.TemporaryDirectory(prefix="g3dpub_") as td:
    pub = Path(td) / "out.jsonl"
    pub.write_text("")
    cmd = [
      "gst-launch-1.0", "-q",
      "multifilesrc", f"location={data_path}",
      f"start-index={start_index}", f"stop-index={stop_index}",
      "caps=application/octet-stream",
      "!", "queue", "max-size-buffers=2",
      "!", "g3dlidarparse", "stride=1", "frame-rate=0",
      f"point-features={mode['point_features']}",
      "!", "g3dinference", f"config={model_config}",
      f"model-type={model_type}", f"device={device}",
      f"score-threshold={score_threshold}",
      "!", "queue", "max-size-buffers=1",
      "!", "gvametaconvert", "add-tensor-data=false", "format=json",
      "!", "gvametapublish", "method=file", "file-format=json-lines",
      f"file-path={pub}",
      "!", "fakesink", "sync=false",
    ]
    print("running:", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
      sys.stderr.write(proc.stderr or proc.stdout or "gst failed\n")
      return proc.returncode
    parsed = []  # list of (frame_index, objects)
    for line in pub.read_text().splitlines():
      line = line.strip()
      if not line:
        continue
      try:
        raw = json.loads(line)
      except json.JSONDecodeError:
        continue
      objs = _normalize(raw)
      lf = raw.get("lidar_frame") or {}
      if "frame_id" in lf:
        fi = start_index + int(lf["frame_id"])
      else:
        fi = start_index + len(parsed)
      parsed.append((fi, objs))
    expected = stop_index - start_index + 1
    by_fi = {fi: objs for fi, objs in parsed}
    dropped = len(parsed) != expected
    if dropped:
      sys.stderr.write(
        f"warning: gst published {len(parsed)} lines for {expected} frames "
        "(empty frames dropped; using lidar_frame.frame_id when present)\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as fh:
      for fi in range(start_index, stop_index + 1):
        row = {
          "frame_index": fi,
          "objects": by_fi.get(fi, []),
          "method": f"g3d_{model_type}",
        }
        if dropped and fi not in by_fi:
          row["empty_frames_dropped"] = True
        fh.write(json.dumps(row) + "\n")
    print(f"wrote {expected} frames → {output} (raw={len(parsed)})")
  return 0


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--model-type", choices=sorted(_MODE), required=True)
  ap.add_argument("--data-path", default=None)
  ap.add_argument("--config", default=None)
  ap.add_argument("--start-index", type=int, default=3270)
  ap.add_argument("--stop-index", type=int, default=4100)
  ap.add_argument("--device", default="CPU")
  ap.add_argument("--score-threshold", type=float, default=0.0)
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  mode = _MODE[args.model_type]
  return run(
    model_type=args.model_type,
    data_path=args.data_path or mode["default_data"],
    model_config=args.config or mode["default_config"],
    start_index=args.start_index,
    stop_index=args.stop_index,
    device=args.device,
    score_threshold=args.score_threshold,
    output=args.output,
  )


if __name__ == "__main__":
  raise SystemExit(main() or 0)
