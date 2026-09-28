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
) -> list[str]:
  """GStreamer fragments for recorded radar bins + g3dinference."""
  parts = [
    f"multifilesrc location={shlex.quote(data_path)} start-index={start_index}",
  ]
  if stop_index is not None:
    parts.append(f"stop-index={stop_index}")
  if loop:
    parts.append("loop=true")
  parts += [
    "caps=application/octet-stream",
    f"! g3dlidarparse stride=1 frame-rate={frame_rate} point-features={int(point_features)}",
    f"! g3dinference config={shlex.quote(model_config)}"
    f" model-type={shlex.quote(model_type)}"
    f" device={shlex.quote(device)}"
    f" score-threshold={score_threshold}",
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
) -> list[str]:
  parts = [
    f"multifilesrc location={shlex.quote(data_path)} start-index={start_index}",
  ]
  if stop_index is not None:
    parts.append(f"stop-index={stop_index}")
  if loop:
    parts.append("loop=true")
  parts += [
    "caps=image/jpeg",
    "! jpegdec",
    "! videoconvert",
    "! video/x-raw,format=BGR",
    f"! gvafpsthrottle target-fps={frame_rate}",
    f"! gvadetect model={shlex.quote(model)}"
    f" model-proc={shlex.quote(model_proc)}"
    f" device={shlex.quote(device)}"
    f" threshold={score_threshold}",
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


def setup_getimage_responder(
  client: mqtt.Client,
  sensor_id: str,
  data_path: str,
  frame_index_cell: list,
  start_index: int,
) -> None:
  """Answer Manager UI image requests from the recorded JPEG sequence.

  Scene live view publishes ``getimage`` and expects
  ``scenescape/image/camera/{id}``. The camera calibration page publishes
  ``getcalibrationimage`` and expects
  ``scenescape/image/calibration/camera/{id}`` (same contract as
  ``sscape_post_inference_data_publish``).
  """
  live_topic = f"scenescape/image/camera/{sensor_id}"
  calib_topic = f"scenescape/image/calibration/camera/{sensor_id}"

  def _jpeg_payload() -> str | None:
    idx = frame_index_cell[0]
    if idx is None:
      return None
    return read_frame_as_jpeg_b64(data_path % idx) or read_frame_as_jpeg_b64(
      data_path % start_index)

  def _on_message(msg_client, _userdata, message):
    cmd = message.payload.decode("utf-8", errors="replace").strip()
    if cmd == "getimage":
      topic = live_topic
    elif cmd == "getcalibrationimage":
      topic = calib_topic
    else:
      return
    b64 = _jpeg_payload()
    if b64 is not None:
      msg_client.publish(topic, json.dumps({"image": b64}), qos=0)

  client.subscribe(f"scenescape/cmd/camera/{sensor_id}")
  client.on_message = _on_message
