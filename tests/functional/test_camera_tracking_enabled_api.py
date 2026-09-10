#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import threading
import time
from pathlib import Path

import pytest

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK, FULL_STACK_WITH_RETAIL_VIDEO,FULL_STACK_AUTOCALIBRATION

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_AUTOCALIBRATION,
  auth=AUTH_CONTROLLER,
)

MAX_WAIT = 60
FRAME_INTERVAL = 0.5


class SceneOutputCollector:
  """Collect DATA_SCENE messages for one scene/category."""

  def __init__(self, pubsub, scene_uid, thing_type="person"):
    self._pubsub = pubsub
    self._topic = PubSub.formatTopic(
      PubSub.DATA_SCENE,
      scene_id=scene_uid,
      thing_type=thing_type,
    )
    self._lock = threading.Lock()
    self._messages = []

  def __enter__(self):
    self._pubsub.addCallback(self._topic, self._on_message)
    return self

  def __exit__(self, *exc):
    self._pubsub.removeCallback(self._topic)

  def _on_message(self, _client, _userdata, message):
    try:
      data = json.loads(message.payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
      return
    with self._lock:
      self._messages.append(data)

  def clear(self):
    with self._lock:
      self._messages.clear()

  def messages(self):
    with self._lock:
      return list(self._messages)

  def max_unique_detection_count(self):
    msgs = self.messages()
    if not msgs:
      return None
    counts = [msg.get("unique_detection_count") for msg in msgs
              if msg.get("unique_detection_count") is not None]
    return max(counts) if counts else None

  def wait_for_unique_count_at_least(self, minimum, timeout=MAX_WAIT, interval=0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
      value = self.max_unique_detection_count()
      if value is not None and value >= minimum:
        return value
      time.sleep(interval)
    return None


def connect_mqtt(params):
  pubsub = PubSub(
    params["auth"],
    None,
    params["rootcert"],
    params["broker_url"],
    port=int(params["broker_port"]),
    keepalive=60,
  )
  pubsub.connect()
  pubsub.loopStart()
  for _ in range(100):
    if pubsub.isConnected():
      break
    time.sleep(0.1)
  assert pubsub.isConnected(), "Failed to connect to MQTT broker"
  return pubsub


def make_frame(camera_id, detections):
  return {
    "id": camera_id,
    "timestamp": get_iso_time(),
    "rate": 10.0,
    "objects": {
      "person": detections,
    },
  }


def make_detection(det_id, x):
  return {
    "id": int(det_id),
    "category": "person",
    "bounding_box": {
      "x": x,
      "y": 0.0,
      "width": 0.24,
      "height": 0.49,
    },
  }


def publish_frames(pubsub, camera_id, detections, num_frames=12, interval=FRAME_INTERVAL):
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
  for _ in range(num_frames):
    pubsub.publish(topic, json.dumps(make_frame(camera_id, detections)))
    time.sleep(interval)


def create_test_scene(rest, repo_root):
  map_path = Path(repo_root) / "tests" / "resources" / "maps" / "HazardZoneSceneLarge.png"
  assert map_path.exists(), f"Map not found: {map_path}"

  with open(map_path, "rb") as f:
    map_data = f.read()

  scene_data = {
    "name": "tracking_enabled_scene",
    "scale": 100,
    "map": (str(map_path), map_data),
  }
  result = rest.createScene(scene_data)
  assert result, (result.statusCode, result.errors)
  return result["uid"]


def create_test_camera(rest, scene_uid):
  camera_data = {
    "name": "tracking_camera",
    "sensor_id": "tracking_camera",
    "scene": scene_uid,
    "intrinsics": {
      "fx": 905.0,
      "fy": 905.0,
      "cx": 640.0,
      "cy": 360.0,
    },
    "translation": [3.0, 4.0, 1.0],
    "rotation": [130.0, 10.0, 20.0],
    "scale": [1.0, 1.0, 1.0],
    "transform_type": "euler",
    "tracking_enabled": True
  }

  result = rest.createCamera(camera_data)
  assert result, (result.statusCode, result.errors)
  return result["uid"]


def test_camera_tracking_enabled_rest_and_runtime(
  scenescape_env,
  request,
  record_xml_attribute,
  repo_root,
  params,
):
  """
  Functional test for camera tracking_enabled:
    1. Create isolated scene + camera with tracking_enabled=True
    2. Verify GET/list return tracking_enabled=True
    3. Publish detections and observe unique_detection_count >= 1
    4. Disable tracking via REST and verify GET/list return False
    5. Publish a new distinct detection and verify unique_detection_count does not increase
    6. Re-enable tracking and verify unique_detection_count increases
  """
  rest = None
  pubsub = None
  scene_uid = None
  camera_uid = None

  try:
    rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert rest.authenticate(params["user"], params["password"]), "REST auth failed"

    scene_uid = create_test_scene(rest, repo_root)
    camera_uid = create_test_camera(rest, scene_uid)

    camera = rest.getCamera(camera_uid)
    assert camera, (camera.statusCode, camera.errors)
    assert camera.get("tracking_enabled") is True

    pubsub = connect_mqtt(params)

    camera_topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_uid)
    scene_topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=scene_uid, thing_type="person")

    with SceneOutputCollector(pubsub, scene_uid, "person") as collector:
      # Phase 1: enabled -> should create at least one unique track
      publish_frames(pubsub, camera_uid, [make_detection("0", 0.56)], num_frames=30, interval=0.5)
      baseline = collector.wait_for_unique_count_at_least(1)
      assert baseline is not None, "No tracked object observed while tracking_enabled=True"

      # Phase 2: disable tracking and verify API/list reflect it
      update = rest.updateCamera(camera_uid, {
        "name": "tracking_enabled_camera",
        "tracking_enabled": False,
      })
      assert update, (update.statusCode, update.errors)

      camera = rest.getCamera(camera_uid)
      assert camera, (camera.statusCode, camera.errors)
      assert camera.get("tracking_enabled") is False

      collector.clear()
      time.sleep(5)

      # Publish a distinct second person far enough away to become a new track if processed.
      publish_frames(pubsub, camera_uid, [
        make_detection("0", 0.56),
        make_detection("1", 1.10),
      ])

      time.sleep(5)
      after_disable = collector.max_unique_detection_count()
      if after_disable is not None:
        assert after_disable <= baseline, (
          f"unique_detection_count grew while tracking was disabled: "
          f"baseline={baseline}, after_disable={after_disable}"
        )

      # Phase 3: re-enable tracking and verify count can grow again
      update = rest.updateCamera(camera_uid, {
        "name": "tracking_enabled_camera",
        "tracking_enabled": True,
      })
      assert update, (update.statusCode, update.errors)

      camera = rest.getCamera(camera_uid)
      assert camera.get("tracking_enabled") is True

      collector.clear()
      time.sleep(5)

      publish_frames(pubsub, camera_uid, [
        make_detection("0", 0.56),
        make_detection("1", 1.10),
      ])

      grown = collector.wait_for_unique_count_at_least(baseline + 1, timeout=15)
      assert grown is not None, (
        f"unique_detection_count did not increase after re-enabling tracking "
        f"(baseline={baseline})"
      )

  finally:
    if pubsub is not None:
      pubsub.loopStop()
      pubsub.disconnect()

    if rest is not None:
      if camera_uid is not None:
        rest.deleteCamera(camera_uid)
      if scene_uid is not None:
        rest.deleteScene(scene_uid)
