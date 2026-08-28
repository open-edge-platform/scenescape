#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""SceneScape radar detection publish contract (input-agnostic).

Maps gvametaconvert 3-D OD JSON (from g3dinference model-type=radarpillars)
onto scenescape/data/radar/{id}. Translations stay in radar-local metres;
Controller applies sensor extrinsics.
"""

from __future__ import annotations

import math
import os
import time
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# RadarPillars class_names order in radarpillars_ov_config.json
RADAR_LABELS: dict[int, str] = {0: "vehicle", 1: "person", 2: "cyclist"}

ROOT_CA = "/run/secrets/certs/scenescape-ca.pem"


def make_timestamp(ts: float) -> str:
  dt = datetime.fromtimestamp(ts, tz=timezone.utc)
  ms = dt.microsecond // 1000
  return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


def wall_clock_timestamp() -> str:
  return make_timestamp(time.time())


def yaw_to_quaternion(yaw: float) -> list[float]:
  """Z-yaw → SceneScape ``[x, y, z, w]`` (radar-local, no LiDAR axis remap)."""
  half = float(yaw) / 2.0
  qz = math.sin(half)
  qw = math.cos(half)
  if qw < 0.0:
    qz, qw = -qz, -qw
  _c = 1.0 - 1e-7
  return [0.0, 0.0, max(-_c, min(_c, qz)), max(-_c, min(_c, qw))]


def resolve_radar_label(obj: dict, labels: dict[int, str] | None = None) -> str | None:
  names = labels if labels is not None else RADAR_LABELS
  label = obj.get("label")
  if isinstance(label, str) and label.strip():
    return label.strip()
  try:
    return names.get(int(obj.get("label_id")))
  except (TypeError, ValueError):
    return None


def build_radar_message(raw: dict, sensor_id: str, fps: float) -> dict:
  """Wrap RadarPillars 3-D detections for scenescape/data/radar/{id}."""
  ts = wall_clock_timestamp()
  objects: dict = {}
  for i, obj in enumerate(raw.get("objects") or []):
    bbox = obj.get("bbox_3d")
    if not isinstance(bbox, dict) or "yaw" not in bbox:
      continue
    label = resolve_radar_label(obj)
    if label is None:
      continue
    try:
      objects.setdefault(label, []).append({
        "id": i + 1,
        "category": label,
        "confidence": obj.get("confidence", 0.0),
        "translation": [
          float(bbox.get("x", 0.0)),
          float(bbox.get("y", 0.0)),
          float(bbox.get("z", 0.0)),
        ],
        "size": [
          float(bbox.get("l", 0.0)),
          float(bbox.get("w", 0.0)),
          float(bbox.get("h", 0.0)),
        ],
        "rotation": yaw_to_quaternion(float(bbox["yaw"])),
        "source": "radar",
      })
    except (TypeError, ValueError):
      continue
  return {"id": sensor_id, "timestamp": ts, "rate": round(fps, 2), "objects": objects}


def build_camera_message(
  raw: dict, sensor_id: str, fps: float, allowed_labels: list[str] | None,
) -> dict:
  ts = wall_clock_timestamp()
  objects: dict = {}
  for i, item in enumerate(raw.get("objects") or []):
    detection = item.get("detection")
    if not isinstance(detection, dict) or "confidence" not in detection:
      continue
    label = (detection.get("label") or str(detection.get("label_id", ""))).strip()
    if allowed_labels and label not in allowed_labels:
      continue
    try:
      objects.setdefault(label, []).append({
        "id": i + 1,
        "category": label,
        "confidence": detection["confidence"],
        "bounding_box_px": {
          "x": item["x"],
          "y": item["y"],
          "width": item["w"],
          "height": item["h"],
        },
        "source": "camera",
      })
    except (KeyError, TypeError):
      continue
  return {"id": sensor_id, "timestamp": ts, "rate": round(fps, 2), "objects": objects}


class MqttState:
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


def connect_mqtt(name: str, broker: str, port: int, state: MqttState) -> mqtt.Client:
  client = mqtt.Client(client_id=f"{name}-{uuid.uuid4().hex[:8]}", protocol=mqtt.MQTTv311)
  root_ca = os.environ.get("MQTT_ROOTCERT", ROOT_CA)
  if os.path.exists(root_ca):
    client.tls_set(ca_certs=root_ca)
    client.tls_insecure_set(True)
  for attempt in range(15):
    try:
      client.connect(broker, port, 60)
      client.loop_start()
      state.add(client)
      print(f"[{name}] connected {broker}:{port}", flush=True)
      return client
    except Exception as exc:
      print(f"[{name}] connect {attempt + 1}/15 failed: {exc}", flush=True)
      time.sleep(2)
  raise SystemExit(f"[{name}] MQTT connect failed")


def safe_publish(client: mqtt.Client, topic: str, payload: dict) -> None:
  import json
  client.publish(topic, json.dumps(payload), qos=0)
