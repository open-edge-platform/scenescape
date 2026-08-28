#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""SceneScape detection publish contract (input-agnostic).

Code here applies whether detections come from live sensors or from a
recorded-file proxy: MQTT topics/payload shape, wall-clock timestamps,
coordinate/orientation mapping, and always-publish (including empty) frames.

File-sequence replay, ``multifilesrc``, and skip-unread staging live in
``lidar_file_playback.py`` — not here.
"""

from __future__ import annotations

import math
import os
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# KITTI class index -> SceneScape label (person omitted; camera covers it).
LIDAR_KITTI_LABELS: dict[int, str] = {1: "cyclist", 2: "vehicle"}

ROOT_CA = "/run/secrets/certs/scenescape-ca.pem"


def make_timestamp(ts: float) -> str:
  """Format a Unix epoch seconds value as SceneScape UTC timestamp."""
  dt = datetime.fromtimestamp(ts, tz=timezone.utc)
  ms = dt.microsecond // 1000
  return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def wall_clock_timestamp() -> str:
  """Stamp detections as 'now' — the live-sensor and fusion-friendly clock."""
  return make_timestamp(time.time())


def lidar_to_scene_offset(x_l: float, y_l: float, z_l: float) -> tuple[float, float, float]:
  """LiDAR (x,y,z) -> scene offset: (-y,-x) axis swap, z forced to 0."""
  return -y_l, -x_l, 0.0


def bbox3d_to_quaternion(yaw: float) -> list[float]:
  """PointPillars yaw -> SceneScape ``[x, y, z, w]`` after the LiDAR->scene axis map.

  Position uses ``lidar_to_scene_offset`` ``(x, y) -> (-y, -x)``. A pure
  heading-vector transform under that map would be ``-yaw - pi/2``, but
  PointPillars ``bbox_3d.yaw`` (model ``theta``) is 90 degrees off that
  convention relative to box motion, so the working mapping is
  ``scene_yaw = -yaw``. Validated against LiDAR-only tracks (yaw vs
  velocity / frame-to-frame translation). Return a Z-yaw quaternion in the
  same ``[x, y, z, w]`` layout as the rest of Scenescape (see
  ``_yaw_to_quaternion`` in the controller).
  """
  scene_yaw = -float(yaw)
  half = scene_yaw / 2.0
  qz = math.sin(half)
  qw = math.cos(half)
  if qw < 0.0:
    qz, qw = -qz, -qw

  # Clamp away from exactly +/-1 (exclusiveMaximum in some schemas).
  _C = 1.0 - 1e-7
  return [0.0, 0.0, max(-_C, min(_C, qz)), max(-_C, min(_C, qw))]


def resolve_lidar_label(obj: dict, kitti_labels: dict[int, str] | None = None) -> str | None:
  labels = kitti_labels if kitti_labels is not None else LIDAR_KITTI_LABELS
  label = obj.get("label")
  if label and isinstance(label, str) and label.strip():
    label = label.strip()
    return label if label in ("vehicle", "cyclist") else None
  lid = obj.get("label_id")
  if lid is not None:
    try:
      return labels.get(int(lid))
    except (ValueError, TypeError):
      return None
  return None


def build_lidar_message(raw: dict, sensor_id: str, fps: float) -> dict:
  """Wrap PointPillars 3-D detections in SceneScape camera-detection format."""
  ts = wall_clock_timestamp()

  objects: dict = {}
  for i, obj in enumerate(raw.get("objects", [])):
    bbox = obj.get("bbox_3d")
    if not isinstance(bbox, dict) or "yaw" not in bbox:
      continue
    label = resolve_lidar_label(obj)
    if label is None:
      continue
    try:
      sx, sy, sz = lidar_to_scene_offset(
        bbox.get("x", 0.0), bbox.get("y", 0.0), bbox.get("z", 0.0)
      )
      objects.setdefault(label, []).append({
        "id":          i + 1,
        "category":    label,
        "confidence":  obj.get("confidence", 0.0),
        "translation": [sx, sy, sz],
        "size":        [bbox.get("l", 0.0), bbox.get("w", 0.0), bbox.get("h", 0.0)],
        "rotation":    bbox3d_to_quaternion(float(bbox["yaw"])),
        "source":      "lidar",
      })
    except (TypeError, ValueError):
      continue

  return {"id": sensor_id, "timestamp": ts, "rate": round(fps, 2), "objects": objects}


def build_camera_message(
  raw: dict, sensor_id: str, fps: float, allowed_labels: list[str] | None,
) -> dict:
  """Wrap gvametaconvert 2-D detections in SceneScape camera-detection format."""
  ts = wall_clock_timestamp()

  objects: dict = {}
  for i, item in enumerate(raw.get("objects", [])):
    detection = item.get("detection")
    if not isinstance(detection, dict) or "confidence" not in detection:
      continue
    label = detection.get("label") or str(detection.get("label_id", ""))
    label = label.strip()
    if allowed_labels and label not in allowed_labels:
      continue
    try:
      objects.setdefault(label, []).append({
        "id":              i + 1,
        "category":        label,
        "confidence":      detection["confidence"],
        "bounding_box_px": {
          "x":      item["x"],
          "y":      item["y"],
          "width":  item["w"],
          "height": item["h"],
        },
        "source":          "camera",
      })
    except (KeyError, TypeError):
      continue

  return {"id": sensor_id, "timestamp": ts, "rate": round(fps, 2), "objects": objects}


class MqttState:
  """Tracks active clients so atexit always disconnects every stream's client."""

  def __init__(self) -> None:
    self.clients: list[mqtt.Client] = []

  def add(self, client: mqtt.Client) -> None:
    self.clients.append(client)

  def shutdown(self) -> None:
    for client in self.clients:
      try:
        client.loop_stop()
        client.disconnect()
      except Exception:
        pass
    self.clients = []


def connect_mqtt(
  client_prefix: str,
  broker: str,
  port: int,
  mqtt_state: MqttState,
  on_connect_setup=None,
  root_ca: str = ROOT_CA,
) -> mqtt.Client:
  """Connect and, on every (re)connect, re-run on_connect_setup."""
  client = mqtt.Client(client_id=f"{client_prefix}-{uuid.uuid4().hex[:8]}")
  if os.path.exists(root_ca):
    client.tls_set(ca_certs=root_ca)
  for attempt in range(10):
    try:
      client.connect(broker, port, keepalive=60)
      client.loop_start()
      print(f"[{client_prefix}] Connected to {broker}:{port}", flush=True)
      if on_connect_setup is not None:
        on_connect_setup(client)
      mqtt_state.add(client)
      return client
    except Exception as exc:
      print(f"[{client_prefix}] Connect attempt {attempt + 1}/10 failed: {exc}", flush=True)
      time.sleep(2)
  raise RuntimeError(f"[{client_prefix}] Could not connect to MQTT broker after 10 attempts")


def safe_publish(
  client: mqtt.Client,
  client_prefix: str,
  topic: str,
  payload: str,
  broker: str,
  port: int,
  mqtt_state: MqttState,
  on_connect_setup=None,
  root_ca: str = ROOT_CA,
) -> mqtt.Client:
  result = client.publish(topic, payload, qos=0)
  if result.rc != mqtt.MQTT_ERR_SUCCESS:
    print(f"[{client_prefix}] Publish failed rc={result.rc}, reconnecting...", flush=True)
    try:
      client.loop_stop()
      client.disconnect()
    except Exception:
      pass
    client = connect_mqtt(
      client_prefix, broker, port, mqtt_state,
      on_connect_setup=on_connect_setup, root_ca=root_ca,
    )
    client.publish(topic, payload, qos=0)
  return client
