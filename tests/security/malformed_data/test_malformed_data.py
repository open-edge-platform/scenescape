#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Security test: the scene controller must reject malformed sensor data.

This drives camera messages onto the MQTT input topic and verifies
that the controller only forwards data that both passes schema validation and
originates from a registered camera. Each case is exercised in isolation: a
single camera publishes for a short window while the test subscribes to the
scene output topic and counts forwarded updates.

Acceptance criteria:
  * A registered camera sending valid data produces scene updates.
  * Messages that fail schema validation produce no scene updates.
  * Messages from an unregistered camera produce no scene updates.
"""

import json
import threading
import time
import pytest
from http import HTTPStatus

import tests.common_test_utils as common
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import AUTH_CONTROLLER, FuncTestSpec

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

SCENE_NAME = "Demo"

# camera1 is pre-registered in tests/testdb.tar.bz2 and is used as the primary
# positive control. The remaining registered cameras are seeded over REST.
CONTROL_CAMERA = "camera1"
CANARY_CAMERA = "sensor10"
INVALID_SENDER = "sensor_bad"
SEEDED_CAMERAS = (CANARY_CAMERA, INVALID_SENDER)

# Never registered: exercises the unknown-sender drop path.
UNKNOWN_CAMERA = "camera4"

# How long to wait for an expected scene update before giving up.
EMIT_TIMEOUT_S = 120
# How long to drive a camera that must NOT produce scene updates.
DROP_WINDOW_S = 6
PUBLISH_INTERVAL_S = 0.2
DRAIN_TIME_S = 1.5


def _good_objects():
  """Return a schema-valid detection payload (normalized bounding box)."""
  return {
    "person": [
      {
        "id": 1,
        "category": "person",
        "confidence": 0.9,
        "bounding_box": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.3},
      }
    ]
  }


def _good_payload(camera_id):
  """Return a fully valid detector message for *camera_id*."""
  return {
    "timestamp": get_iso_time(),
    "id": camera_id,
    "objects": _good_objects(),
    "rate": 1.0,
  }


# Each builder takes a camera_id and returns a fresh message that must be
# rejected by the controller's schema validation.

def _missing_timestamp(camera_id):
  payload = _good_payload(camera_id)
  del payload["timestamp"]
  return payload


def _zero_confidence(camera_id):
  payload = _good_payload(camera_id)
  payload["objects"]["person"][0]["confidence"] = 0.0
  return payload


def _negative_confidence(camera_id):
  payload = _good_payload(camera_id)
  payload["objects"]["person"][0]["confidence"] = -0.88
  return payload


def _negative_bbox_width(camera_id):
  payload = _good_payload(camera_id)
  payload["objects"]["person"][0]["bounding_box"]["width"] = -0.2
  return payload


def _negative_bbox_height(camera_id):
  payload = _good_payload(camera_id)
  payload["objects"]["person"][0]["bounding_box"]["height"] = -0.3
  return payload


def _negative_object_id(camera_id):
  payload = _good_payload(camera_id)
  payload["objects"]["person"][0]["id"] = -100
  return payload


def _non_string_id(camera_id):
  payload = _good_payload(camera_id)
  # The sender id must be a string; an integer violates the schema.
  payload["id"] = 12345
  return payload


def _missing_category(camera_id):
  payload = _good_payload(camera_id)
  del payload["objects"]["person"][0]["category"]
  return payload


def _missing_geometry(camera_id):
  payload = _good_payload(camera_id)
  del payload["objects"]["person"][0]["bounding_box"]
  return payload


def _rotation_out_of_range(camera_id):
  payload = _good_payload(camera_id)
  # rotation quaternion components must satisfy -1 < value < 1.
  payload["objects"]["person"][0]["rotation"] = [1.0, 0.0, 0.0, 0.0]
  return payload


# name -> builder for messages that the controller must drop on schema grounds.
INVALID_CASES = (
  ("missing_timestamp", _missing_timestamp),
  ("zero_confidence", _zero_confidence),
  ("negative_confidence", _negative_confidence),
  ("negative_bbox_width", _negative_bbox_width),
  ("negative_bbox_height", _negative_bbox_height),
  ("negative_object_id", _negative_object_id),
  ("non_string_id", _non_string_id),
  ("missing_category", _missing_category),
  ("missing_geometry", _missing_geometry),
  ("rotation_out_of_range", _rotation_out_of_range),
)


class _SceneCounter:
  """Thread-safe counter of scene-output messages."""

  def __init__(self):
    self._lock = threading.Lock()
    self._count = 0

  def __call__(self, client, userdata, message):
    with self._lock:
      self._count += 1

  def reset(self):
    with self._lock:
      self._count = 0

  @property
  def count(self):
    with self._lock:
      return self._count


def _seed_camera(rest, scene_uid, camera_id):
  """Register *camera_id* on the given scene; skip if it already exists."""
  existing = rest.getCameras({"sensor_id": camera_id})
  if existing.get("results"):
    return
  camera_data = {
    "name": camera_id,
    "sensor_id": camera_id,
    "scene": scene_uid,
    "intrinsics": {"fx": 800.0, "fy": 800.0, "cx": 320.0, "cy": 240.0},
  }
  res = rest.createCamera(camera_data)
  assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), \
    f"Failed to seed camera {camera_id}: {res.errors}"


def _drive_until_emit(pubsub, counter, camera_id, timeout):
  """Publish valid data for *camera_id* until a scene update is seen.

  Returns ``(count, payload_json)`` where count is the number of scene
  messages observed (>0 on success) and payload_json is a sample of the
  message that was published.
  """
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
  counter.reset()
  payload_json = json.dumps(_good_payload(camera_id))
  deadline = time.time() + timeout
  while time.time() < deadline:
    payload_json = json.dumps(_good_payload(camera_id))
    pubsub.publish(topic, payload_json)
    time.sleep(PUBLISH_INTERVAL_S)
    if counter.count > 0:
      break
  return counter.count, payload_json


def _drive_expecting_drop(pubsub, counter, camera_id, build_payload, duration):
  """Publish *build_payload* for *camera_id* for *duration* seconds.

  Returns ``(count, payload_json)`` where count is the number of scene
  messages observed (should be 0) and payload_json is a sample of the
  message that was published.
  """
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
  counter.reset()
  payload_json = json.dumps(build_payload(camera_id))
  deadline = time.time() + duration
  while time.time() < deadline:
    payload_json = json.dumps(build_payload(camera_id))
    pubsub.publish(topic, payload_json)
    time.sleep(PUBLISH_INTERVAL_S)
  time.sleep(DRAIN_TIME_S)
  return counter.count, payload_json


def _print_evidence(evidence):
  """Emit a human-readable evidence table of per-case outcomes.

  Written to both stdout and the per-test log file so the rejection
  evidence (including the JSON payload that was published) is preserved
  as a durable test artifact.
  """
  header = (f"{'SENDER':<12} {'CASE':<28} {'EXPECT':>6} {'SEEN':>5}  "
            f"{'VERDICT':<9} {'RESULT':<6} PAYLOAD")
  lines = [
    "===== MALFORMED DATA REJECTION EVIDENCE =====",
    header,
    "-" * len(header),
  ]
  for sender, case, payload, expect, seen, verdict, ok in evidence:
    lines.append(f"{sender:<12} {case:<28} {expect:>6} {seen:>5}  "
                 f"{verdict:<9} {'PASS' if ok else 'FAIL':<6} {payload}")
  lines.append("=" * len(header))
  for line in lines:
    print(line)
    log.info(line)

@pytest.mark.test_name("NEX-T10423")
def test_malformed_data(scenescape_env, params):
  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), \
    "REST authentication failed"

  scenes = rest.getScenes({"name": SCENE_NAME})["results"]
  assert scenes, f"Scene {SCENE_NAME!r} not found"
  scene_uid = scenes[0]["uid"]

  for camera_id in SEEDED_CAMERAS:
    _seed_camera(rest, scene_uid, camera_id)

  counter = _SceneCounter()
  pubsub = PubSub(
    params["auth"], None, params["rootcert"],
    params["broker_url"], port=int(params["broker_port"]),
  )
  pubsub.connect()
  pubsub.loopStart()

  failures = []
  evidence = []
  try:
    scene_topic = PubSub.formatTopic(
      PubSub.DATA_SCENE, scene_id=scene_uid, thing_type="+",
    )
    pubsub.addCallback(scene_topic, counter)

    # Positive control: a registered camera with valid data must be forwarded.
    # This also guards against false passes from a broken database or pipeline.
    control_count, payload = _drive_until_emit(
      pubsub, counter, CONTROL_CAMERA, EMIT_TIMEOUT_S,
    )
    ok = control_count > 0
    evidence.append((CONTROL_CAMERA, "valid (control)", payload, ">0",
                     control_count, "ACCEPTED" if ok else "DROPPED", ok))
    if not ok:
      failures.append(
        f"positive control {CONTROL_CAMERA!r} produced no scene updates"
      )

    # Schema-invalid messages must never be forwarded.
    for name, builder in INVALID_CASES:
      seen, payload = _drive_expecting_drop(
        pubsub, counter, INVALID_SENDER, builder, DROP_WINDOW_S,
      )
      ok = seen == 0
      evidence.append((INVALID_SENDER, name, payload, "0", seen,
                       "REJECTED" if ok else "FORWARDED", ok))
      if not ok:
        failures.append(f"invalid case {name!r} produced {seen} scene updates")

    # Unknown sender: valid payload but unregistered camera must be dropped.
    seen, payload = _drive_expecting_drop(
      pubsub, counter, UNKNOWN_CAMERA, _good_payload, DROP_WINDOW_S,
    )
    ok = seen == 0
    evidence.append((UNKNOWN_CAMERA, "valid (unregistered sender)", payload, "0",
                     seen, "REJECTED" if ok else "FORWARDED", ok))
    if not ok:
      failures.append(
        f"unknown sender {UNKNOWN_CAMERA!r} produced {seen} scene updates"
      )

    # Freshly seeded camera with valid data must be forwarded,
    # confirming registration and the database are healthy.
    canary_count, payload = _drive_until_emit(
      pubsub, counter, CANARY_CAMERA, EMIT_TIMEOUT_S,
    )
    ok = canary_count > 0
    evidence.append((CANARY_CAMERA, "valid (canary)", payload, ">0",
                     canary_count, "ACCEPTED" if ok else "DROPPED", ok))
    if not ok:
      failures.append(
        f"canary {CANARY_CAMERA!r} produced no scene updates"
      )
  finally:
    pubsub.loopStop()
    pubsub.disconnect()

  _print_evidence(evidence)

  result = 1 if failures else 0
  for failure in failures:
    print("FAILURE:", failure)

  assert result == 0, "; ".join(failures)


if __name__ == "__main__":
  pytest.main([__file__])
