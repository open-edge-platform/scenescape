#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Recorded-file GStreamer fragments for the radar-intersection demo.

All radar perception modes share one publish stack:

  multifilesrc → g3dlidarparse → g3dinference → gvametaconvert → FIFO

| model-type   | point-features | data |
| --- | ---: | --- |
| classical    | 5 | frames_bin/%06d.bin |
| roadside     | 5 | frames_bin/%06d.bin |
| radarpillars | 7 | pcd_bin/%06d.bin |

Live / stream-friendly densify: set ``accumulate_past`` (GST
``accumulate-past``) so g3dinference concatenates prior frames with the
current cloud before inference. Prefer single-frame ``pcd_bin`` + past=10
over prebuilt ``pcd_bin_acc5`` so the same path works for live radar.
"""

from __future__ import annotations

import base64
import json
import os
import shlex

import paho.mqtt.client as mqtt


def radar_multifilesrc_parts(
  *,
  data_path: str,
  start_index: int,
  stop_index: int | None,
  loop: bool,
  frame_rate: int,
  model_config: str,
  model_type: str,
  point_features: int,
  device: str,
  score_threshold: float,
  add_tensor_data: str,
  fifo_path: str,
  accumulate_past: int = 0,
) -> list[str]:
  """GStreamer fragments for recorded radar bins + g3dinference."""
  parts = [
    f"multifilesrc location={shlex.quote(data_path)} start-index={start_index}",
  ]
  if stop_index is not None:
    parts.append(f"stop-index={stop_index}")
  if loop:
    parts.append("loop=true")
  infer = (
    f"! g3dinference config={shlex.quote(model_config)}"
    f" model-type={shlex.quote(model_type)}"
    f" device={shlex.quote(device)}"
    f" score-threshold={score_threshold}"
  )
  if accumulate_past and int(accumulate_past) > 0:
    infer += f" accumulate-past={int(accumulate_past)}"
  parts += [
    "caps=application/octet-stream",
    f"! g3dlidarparse stride=1 frame-rate={frame_rate} point-features={int(point_features)}",
    infer,
    f"! gvametaconvert add-tensor-data={add_tensor_data} format=json",
    f"! gvametapublish method=file file-format=json-lines file-path={shlex.quote(fifo_path)}",
    "! fakesink sync=false",
  ]
  return parts


def camera_multifilesrc_parts(
  *,
  data_path: str,
  start_index: int,
  stop_index: int | None,
  loop: bool,
  frame_rate: int,
  model: str,
  model_proc: str,
  device: str,
  score_threshold: float,
  fifo_path: str,
  model_instance_id: str | None = None,
) -> list[str]:
  parts = [
    f"multifilesrc location={shlex.quote(data_path)} start-index={start_index}",
  ]
  if stop_index is not None:
    parts.append(f"stop-index={stop_index}")
  if loop:
    parts.append("loop=true")
  detect = (
    f"! gvadetect model={shlex.quote(model)}"
    f" model-proc={shlex.quote(model_proc)}"
    f" device={shlex.quote(device)}"
    f" threshold={score_threshold}"
  )
  if model_instance_id:
    detect += f" model-instance-id={shlex.quote(model_instance_id)}"
  parts += [
    "caps=image/jpeg",
    "! jpegdec",
    "! videoconvert",
    "! video/x-raw,format=BGR",
    f"! gvafpsthrottle target-fps={frame_rate}",
    detect,
    "! gvametaconvert add-tensor-data=false format=json",
    f"! gvametapublish method=file file-format=json-lines file-path={shlex.quote(fifo_path)}",
    "! fakesink sync=false",
  ]
  return parts


def ensure_parent_dir(path: str) -> None:
  parent = os.path.dirname(path)
  if parent:
    os.makedirs(parent, exist_ok=True)


def playback_index(published_count: int, start: int, stop: int | None, loop: bool) -> int:
  """Dataset file index for the latest published camera frame."""
  if published_count <= 0:
    return start
  offset = published_count - 1
  if stop is None:
    return start + offset
  span = stop - start + 1
  if span <= 0:
    return start
  if loop:
    return start + (offset % span)
  return min(start + offset, stop)


def read_frame_as_jpeg_b64(path: str) -> str | None:
  try:
    with open(path, "rb") as f:
      return base64.b64encode(f.read()).decode("ascii")
  except Exception as exc:
    print(f"[radar-camera] Failed to read preview frame {path}: {exc}", flush=True)
    return None


# Match sscape_post_inference_data_publish person red; vehicles use a darker teal
# so boxes stay readable on bright asphalt / truck sides.
_ANNOTATE_COLORS = {
  "person": (0, 0, 255),
  "vehicle": (40, 120, 50),
  "bicycle": (40, 120, 50),
  "cyclist": (40, 120, 50),
}
_ANNOTATE_DEFAULT = (180, 40, 200)


def annotate_frame_jpeg_b64(path: str, objects: dict | None, fps: float | None = None) -> str | None:
  """Load a JPEG, draw detection boxes, return base64 JPEG (SceneScape live view)."""
  try:
    import cv2  # pylint: disable=import-outside-toplevel
  except ImportError:
    return read_frame_as_jpeg_b64(path)
  img = cv2.imread(path)
  if img is None:
    return read_frame_as_jpeg_b64(path)
  for otype, obj_list in (objects or {}).items():
    color = _ANNOTATE_COLORS.get(str(otype).lower(), _ANNOTATE_DEFAULT)
    if not isinstance(obj_list, list):
      continue
    for obj in obj_list:
      if not isinstance(obj, dict):
        continue
      bbox = obj.get("bounding_box_px") or {}
      try:
        x = int(bbox["x"])
        y = int(bbox["y"])
        w = int(bbox["width"])
        h = int(bbox["height"])
      except (KeyError, TypeError, ValueError):
        continue
      cv2.rectangle(img, (x, y), (x + w, y + h), color, 4)
  if fps is not None:
    scale = int((img.shape[0] + 479) / 480)
    fps_str = f"FPS {float(fps):.1f}"
    cv2.putText(
      img, fps_str, (0, 30 * scale), cv2.FONT_HERSHEY_SIMPLEX,
      1 * scale, (0, 0, 0), 5 * scale,
    )
    cv2.putText(
      img, fps_str, (0, 30 * scale), cv2.FONT_HERSHEY_SIMPLEX,
      1 * scale, (255, 255, 255), 2 * scale,
    )
  ok, buf = cv2.imencode(".jpg", img)
  if not ok:
    return read_frame_as_jpeg_b64(path)
  return base64.b64encode(buf.tobytes()).decode("ascii")


def setup_getimage_responder(
  client: mqtt.Client,
  sensor_id: str,
  data_path: str,
  frame_index_cell: list,
  start_index: int,
  image_b64_cell: list | None = None,
) -> None:
  """Answer Manager UI image requests from the recorded JPEG sequence.

  Scene live view publishes ``getimage`` and expects
  ``scenescape/image/camera/{id}``. The camera calibration page publishes
  ``getcalibrationimage`` and expects
  ``scenescape/image/calibration/camera/{id}`` (same contract as
  ``sscape_post_inference_data_publish``).

  When ``image_b64_cell`` is set, live view serves that cached (annotated)
  JPEG. Calibration still uses the raw frame at ``frame_index_cell``.

  Multiple cameras may register; a shared ``on_message`` dispatches by topic.
  """
  live_topic = f"scenescape/image/camera/{sensor_id}"
  calib_topic = f"scenescape/image/calibration/camera/{sensor_id}"
  cmd_topic = f"scenescape/cmd/camera/{sensor_id}"

  def _raw_jpeg() -> str | None:
    idx = frame_index_cell[0]
    if idx is None:
      return None
    return read_frame_as_jpeg_b64(data_path % idx) or read_frame_as_jpeg_b64(
      data_path % start_index)

  def _handle(_msg_client, message) -> None:
    cmd = message.payload.decode("utf-8", errors="replace").strip()
    if cmd == "getimage":
      topic = live_topic
      b64 = None
      if image_b64_cell is not None and image_b64_cell[0]:
        b64 = image_b64_cell[0]
      if b64 is None:
        b64 = _raw_jpeg()
    elif cmd == "getcalibrationimage":
      topic = calib_topic
      b64 = _raw_jpeg()
    else:
      return
    if b64 is not None:
      _msg_client.publish(topic, json.dumps({"image": b64}), qos=0)

  handlers = getattr(client, "_sscape_cmd_handlers", None)
  if handlers is None:
    handlers = {}
    client._sscape_cmd_handlers = handlers

    def _dispatch(msg_client, _userdata, message):
      handler = handlers.get(message.topic)
      if handler is not None:
        handler(msg_client, message)

    client.on_message = _dispatch

  handlers[cmd_topic] = _handle
  client.subscribe(cmd_topic)
