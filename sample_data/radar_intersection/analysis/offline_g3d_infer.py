#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Offline g3dinference runner with one JSONL line per input frame.

Uses Gst appsink with blocking ``try-pull-sample`` so empty detection frames
are not dropped (unlike ``gvametapublish``). Emits the same schema as
``batch_radarpillars_infer.py``.

For classical specifically, ``baselines/classical_batch.py`` is preferred when
running on the host (exact indexing, tunable doppler/extent gates). Use this
runner to exercise the live GST path inside the radar-stream container.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

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
  "radarpillars": {
    "point_features": 7,
    "default_config": (
      "/home/pipeline-server/models/public/radarpillars/FP16/radarpillars_ov_config.json"),
    "default_data": (
      "/home/pipeline-server/videos/radar_intersection/pcd_bin/%06d.bin"),
  },
}


def _objects_from_json(raw) -> list[dict]:
  if raw is None:
    return []
  if isinstance(raw, str):
    try:
      raw = json.loads(raw)
    except json.JSONDecodeError:
      return []
  if not isinstance(raw, dict):
    return []
  label_map = {0: "vehicle", 1: "person", 2: "cyclist"}
  candidates = []
  if isinstance(raw.get("objects"), list):
    candidates = raw["objects"]
  elif isinstance(raw.get("detections"), list):
    candidates = raw["detections"]
  else:
    for val in raw.values():
      if isinstance(val, list) and val and isinstance(val[0], dict):
        if any(k in val[0] for k in (
            "translation", "bbox", "bbox_3d", "center", "label", "category")):
          candidates = val
          break
  out = []
  for i, obj in enumerate(candidates):
    bb = obj.get("bbox_3d")
    if bb:
      trans = [float(bb["x"]), float(bb["y"]), float(bb["z"])]
      size = [float(bb.get("l", 0.6)), float(bb.get("w", 0.6)), float(bb.get("h", 1.7))]
      lid = int(obj.get("label_id", -1))
      cat = label_map.get(lid) or obj.get("label") or obj.get("category") or "object"
    else:
      cat = obj.get("category") or obj.get("label") or obj.get("class") or "object"
      if "translation" in obj:
        trans = list(obj["translation"][:3])
      elif "center" in obj:
        trans = list(obj["center"][:3])
      elif "bbox" in obj and len(obj["bbox"]) >= 3:
        trans = list(obj["bbox"][:3])
      else:
        continue
      size = obj.get("size") or [0.6, 0.6, 1.7]
    conf = float(obj.get("confidence", obj.get("score", obj.get("conf", 0.0))))
    out.append({
      "id": int(obj.get("id", i + 1)),
      "category": str(cat).lower(),
      "confidence": conf,
      "translation": [float(x) for x in trans],
      "size": [float(x) for x in size[:3]],
    })
  return out


def _objects_from_buffer(buf) -> list[dict]:
  # Prefer gstgva VideoFrame messages when available.
  try:
    from gstgva import VideoFrame  # type: ignore
    frame = VideoFrame(buf)
    messages = list(frame.messages()) if hasattr(frame, "messages") else []
    if messages:
      return _objects_from_json(messages[0])
  except Exception:
    pass
  try:
    ok, info = buf.map(Gst.MapFlags.READ)
    if ok and info.size:
      text = bytes(info.data)[: info.size].decode("utf-8", errors="ignore").strip()
      buf.unmap(info)
      if text.startswith("{"):
        return _objects_from_json(text)
    elif ok:
      buf.unmap(info)
  except Exception:
    pass
  return []


def build_pipeline(
  *,
  data_path: str,
  start_index: int,
  stop_index: int,
  model_config: str,
  model_type: str,
  point_features: int,
  device: str,
  score_threshold: float,
  accumulate_past: int,
) -> str:
  infer = (
    f"g3dinference config={model_config} model-type={model_type} "
    f"device={device} score-threshold={score_threshold}"
  )
  if accumulate_past > 0:
    infer += f" accumulate-past={int(accumulate_past)}"
  return (
    f"multifilesrc location={data_path} start-index={start_index} "
    f"stop-index={stop_index} caps=application/octet-stream ! "
    f"queue max-size-buffers=2 ! "
    f"g3dlidarparse stride=1 frame-rate=0 point-features={point_features} ! "
    f"{infer} ! "
    f"queue max-size-buffers=1 ! "
    f"gvametaconvert add-tensor-data=false format=json ! "
    f"appsink name=sink emit-signals=false sync=false max-buffers=8 drop=false"
  )


def run(
  *,
  model_type: str,
  data_path: str,
  model_config: str,
  start_index: int,
  stop_index: int,
  device: str,
  score_threshold: float,
  accumulate_past: int,
  output: Path,
) -> int:
  Gst.init([])
  mode = _MODE[model_type]
  desc = build_pipeline(
    data_path=data_path,
    start_index=start_index,
    stop_index=stop_index,
    model_config=model_config,
    model_type=model_type,
    point_features=mode["point_features"],
    device=device,
    score_threshold=score_threshold,
    accumulate_past=accumulate_past,
  )
  print("pipeline:", desc, flush=True)
  pipeline = Gst.parse_launch(desc)
  sink = pipeline.get_by_name("sink")
  if sink is None:
    raise RuntimeError("appsink not found")
  bus = pipeline.get_bus()
  pipeline.set_state(Gst.State.PLAYING)

  rows: list[list[dict]] = []
  done = False
  err_msg = None
  while not done:
    sample = sink.emit("try-pull-sample", 200 * Gst.MSECOND)
    if sample is not None:
      buf = sample.get_buffer()
      rows.append(_objects_from_buffer(buf))
      continue
    msg = bus.timed_pop_filtered(
      10 * Gst.MSECOND,
      Gst.MessageType.EOS | Gst.MessageType.ERROR)
    if msg is None:
      continue
    if msg.type == Gst.MessageType.EOS:
      done = True
    elif msg.type == Gst.MessageType.ERROR:
      err, debug = msg.parse_error()
      err_msg = f"{err} {debug}"
      done = True
  pipeline.set_state(Gst.State.NULL)
  if err_msg:
    sys.stderr.write(f"GST ERROR: {err_msg}\n")
    return 1

  expected = stop_index - start_index + 1
  output.parent.mkdir(parents=True, exist_ok=True)
  with output.open("w") as fh:
    for i in range(expected):
      objs = rows[i] if i < len(rows) else []
      fh.write(json.dumps({
        "frame_index": start_index + i,
        "objects": objs,
        "method": f"g3d_{model_type}",
      }) + "\n")
  print(f"wrote {expected} frames → {output} (appsink samples={len(rows)})")
  if len(rows) != expected:
    sys.stderr.write(f"warning: expected {expected} samples, got {len(rows)}\n")
  return 0


def parse_args(argv=None):
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--model-type", choices=sorted(_MODE), required=True)
  ap.add_argument("--data-path", default=None)
  ap.add_argument("--config", default=None)
  ap.add_argument("--start-index", type=int, default=3270)
  ap.add_argument("--stop-index", type=int, default=4100)
  ap.add_argument("--device", default="CPU")
  ap.add_argument("--score-threshold", type=float, default=None)
  ap.add_argument("--accumulate-past", type=int, default=0)
  ap.add_argument("-o", "--output", type=Path, required=True)
  return ap.parse_args(argv)


def main(argv=None):
  args = parse_args(argv)
  mode = _MODE[args.model_type]
  thr = args.score_threshold
  if thr is None:
    thr = 0.1 if args.model_type == "radarpillars" else 0.0
  return run(
    model_type=args.model_type,
    data_path=args.data_path or mode["default_data"],
    model_config=args.config or mode["default_config"],
    start_index=args.start_index,
    stop_index=args.stop_index,
    device=args.device,
    score_threshold=thr,
    accumulate_past=args.accumulate_past,
    output=args.output,
  )


if __name__ == "__main__":
  raise SystemExit(main() or 0)
