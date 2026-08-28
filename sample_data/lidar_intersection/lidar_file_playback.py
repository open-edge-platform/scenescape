#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Recorded file-sequence playback for the LiDAR intersection demo.

This module is **file-input only**. It stands in for live capture plumbing:

- Live sensors naturally drop/overwrite unread samples when a consumer is
  slow (ring buffer / latest-frame). ``LidarCatchUp`` approximates that for
  ``multifilesrc``, which cannot jump dataset indices at runtime.
- Dataset index helpers (``playback_index``, ``index_span_delta``) exist only
  because the proxy is a numbered file sequence, not a live device.
- GStreamer ``multifilesrc`` chain fragments and Manager ``getimage`` answers
  that read JPEG files from disk also belong here.

Do not put SceneScape MQTT payload shaping, wall-clock stamping, or
LiDAR→scene transforms here — those live in ``lidar_sensor_contract.py`` and
apply to any input mechanism.

Do not couple camera and LiDAR rates (pace-gate). Independent rates with
drop-stale on the slow path match live multi-sensor deployments.
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import threading
from collections.abc import Callable

import paho.mqtt.client as mqtt


def playback_index(published_count: int, start: int, stop: int | None, loop: bool) -> int:
  """Return the dataset file index for the latest published camera frame.

  ``published_count`` is the number of camera frames published so far
  (0 means none yet, so the start index).
  """
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


def index_span_delta(from_idx: int, to_idx: int, start: int, stop: int | None, loop: bool) -> int:
  """Forward distance in dataset frames from ``from_idx`` to ``to_idx``."""
  if from_idx == to_idx:
    return 0
  if stop is None or not loop:
    return max(0, to_idx - from_idx)
  span = stop - start + 1
  if span <= 0:
    return 0
  return (to_idx - from_idx) % span


class LidarCatchUp:
  """File-playback stand-in for live 'drop unread, keep latest' capture.

  Stages hardlinks (or copies) into a sequential feed directory so
  ``multifilesrc`` always advances, while each new slot points at the
  camera branch's current dataset index ("now").
  """

  def __init__(
    self,
    *,
    data_path: str,
    feed_dir: str,
    start_index: int,
    cam_start: int,
    cam_stop: int | None,
    cam_loop: bool,
    camera_index_fn: Callable[[], int],
  ) -> None:
    self._data_path = data_path
    self._feed_dir = feed_dir
    self._start_index = start_index
    self._cam_start = cam_start
    self._cam_stop = cam_stop
    self._cam_loop = cam_loop
    self._camera_index_fn = camera_index_fn
    self._lock = threading.Lock()
    self._slot_index: dict[int, int] = {}
    self._next_json_slot = 0
    self._next_create_slot = 0
    self.skipped_total = 0
    self.last_dataset_index = start_index

  def reset_feed_dir(self) -> None:
    if os.path.isdir(self._feed_dir):
      shutil.rmtree(self._feed_dir)
    os.makedirs(self._feed_dir, exist_ok=True)

  def prime(self) -> None:
    """Install slots 0 and 1 before gst-launch opens the LiDAR source."""
    self.reset_feed_dir()
    idx = self._camera_index_fn()
    with self._lock:
      self._link_slot(0, idx)
      self._link_slot(1, idx)
      self._next_json_slot = 0
      self._next_create_slot = 2
      self.last_dataset_index = idx
      self.skipped_total = 0

  def nudge_lookahead(self) -> None:
    """Keep the unread lookahead slot on camera-now (covers model-load wait)."""
    cam = self._camera_index_fn()
    with self._lock:
      look = self._next_json_slot + 1
      if look >= self._next_create_slot:
        return
      self._link_slot(look, cam)

  def on_lidar_done(self) -> tuple[int, int]:
    """Record a finished inference and stage the next catch-up slot.

    Returns ``(inferred_dataset_index, frames_skipped_this_step)``.
    """
    cam = self._camera_index_fn()
    with self._lock:
      slot = self._next_json_slot
      inferred = self._slot_index.get(slot, self._start_index)
      skipped = index_span_delta(
        inferred, cam, self._cam_start, self._cam_stop, self._cam_loop,
      )
      self.skipped_total += skipped
      self.last_dataset_index = inferred
      self._next_json_slot = slot + 1
      self._link_slot(self._next_create_slot, cam)
      self._next_create_slot += 1
      stale = slot - 2
      if stale >= 0:
        stale_path = os.path.join(self._feed_dir, f"{stale:08d}.bin")
        try:
          os.unlink(stale_path)
        except FileNotFoundError:
          pass
      return inferred, skipped

  def _link_slot(self, slot: int, dataset_index: int) -> None:
    src = self._data_path % dataset_index
    if not os.path.isfile(src):
      raise FileNotFoundError(f"LiDAR frame missing: {src}")
    dest = os.path.join(self._feed_dir, f"{slot:08d}.bin")
    tmp = dest + ".tmp"
    try:
      os.unlink(tmp)
    except FileNotFoundError:
      pass
    try:
      os.link(src, tmp)
    except OSError:
      shutil.copyfile(src, tmp)
    os.replace(tmp, dest)
    self._slot_index[slot] = dataset_index


def read_frame_as_jpeg_b64(path: str) -> str | None:
  """Read a frame file and base64 it as-is (already JPEG, no re-encode)."""
  try:
    with open(path, "rb") as f:
      return base64.b64encode(f.read()).decode("ascii")
  except Exception as exc:
    print(f"[camera-publisher] Failed to read preview frame {path}: {exc}", flush=True)
    return None


def setup_getimage_responder(
  client: mqtt.Client, sensor_id: str, data_path: str, frame_index_cell: list, start_index: int,
) -> None:
  """Answer the Manager UI's getimage command from a recorded JPEG sequence."""
  image_topic = f"scenescape/image/camera/{sensor_id}"

  def _on_message(msg_client, _userdata, message):
    if message.payload.decode("utf-8", errors="replace").strip() != "getimage":
      return
    idx = frame_index_cell[0]
    if idx is None:
      return
    b64 = read_frame_as_jpeg_b64(data_path % idx) or read_frame_as_jpeg_b64(data_path % start_index)
    if b64 is not None:
      msg_client.publish(image_topic, json.dumps({"image": b64}), qos=0)

  client.subscribe(f"scenescape/cmd/camera/{sensor_id}")
  client.on_message = _on_message


def lidar_multifilesrc_parts(
  *,
  skip_to_live: bool,
  feed_dir: str,
  data_path: str,
  start_index: int,
  stop_index: int | None,
  loop: bool,
  frame_rate: int,
  model_config: str,
  device: str,
  score_threshold: float,
  add_tensor_data: str,
  fifo_path: str,
) -> list[str]:
  """GStreamer fragments for the recorded LiDAR ``.bin`` branch."""
  if skip_to_live:
    feed = os.path.join(feed_dir, "%08d.bin")
    parts = [
      f"multifilesrc location={shlex.quote(feed)} start-index=0",
    ]
  else:
    parts = [
      f"multifilesrc location={shlex.quote(data_path)} start-index={start_index}",
    ]
    if stop_index is not None:
      parts.append(f"stop-index={stop_index}")
    if loop:
      parts.append("loop=true")
  parts += [
    "caps=application/octet-stream",
    f"! g3dlidarparse stride=1 frame-rate={frame_rate}",
    f"! g3dinference config={shlex.quote(model_config)}"
    f" model-type=pointpillars"
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
  """GStreamer fragments for the recorded camera JPEG branch."""
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
