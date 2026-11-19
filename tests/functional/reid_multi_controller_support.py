#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Drive the three-controller ReID stack and check schema-rejection outcomes."""

import base64
import json
import re
import struct
import time
from contextlib import contextmanager

import numpy as np

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time

from tests.functional.reid_vdms_state import (
  assert_snapshots_equal,
  snapshot_vdms_state,
  vdms_client,
)
from tests.utils.log import get_logger

log = get_logger(__name__)

CONTROLLERS = ("scene", "scene-b", "scene-c")
REID_DIMENSIONS = 256
REID_MODEL = "person-reidentification-retail-0287"
PERSON_BBOX = {"x": 100, "y": 100, "width": 120, "height": 240}
SCHEMA_ATTEMPT_TIMEOUT_S = 30

# Any of these in a controller log means a timeout could be a connectivity failure.
VDMS_CONNECTION_ERRORS = (
  "Failed to connect to VDMS",
  "Cannot send query to VDMS",
  "VDMS reconnect failed",
  "Failed to receive a complete VDMS query response",
)
SCHEMA_READY_LOG = re.compile(r"ensureSchema: (Created|Verified existing) VDMS descriptor set")


def make_embedding(seed=0):
  """Return a deterministic unit-norm 256-float embedding."""
  vec = np.random.default_rng(seed).standard_normal(REID_DIMENSIONS)
  return (vec / np.linalg.norm(vec)).astype(np.float32)


def person_frame(camera_id, embedding):
  """Camera-frame payload with one person carrying a ReID embedding."""
  packed = struct.pack(f"{REID_DIMENSIONS}f", *embedding)
  return {
    "id": camera_id,
    "timestamp": get_iso_time(),
    "rate": 10.0,
    "objects": {"person": [{
      "id": 1,
      "category": "person",
      "bounding_box_px": PERSON_BBOX,
      "metadata": {"reid": {
        "embedding_vector": base64.b64encode(packed).decode("utf-8"),
        "model_name": REID_MODEL,
      }},
    }]},
  }


@contextmanager
def mqtt_client(params):
  """Yield a connected, looping PubSub client."""
  pubsub = PubSub(
    params["auth"], None, params["rootcert"], params["broker_url"],
    port=int(params["broker_port"]), keepalive=60)
  pubsub.connect()
  pubsub.loopStart()
  try:
    for _ in range(100):
      if pubsub.isConnected():
        break
      time.sleep(0.1)
    assert pubsub.isConnected(), "Failed to connect to MQTT broker"
    yield pubsub
  finally:
    pubsub.loopStop()
    pubsub.disconnect()


def get_camera_id(params):
  """Return the id of the first camera of the first scene that has one."""
  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), "Auth failed"
  scenes = rest.getScenes({}).get("results", [])
  for scene in scenes:
    cameras = rest.getCameras({"scene": scene["uid"]}).get("results", [])
    if cameras:
      return cameras[0]["uid"]
  raise AssertionError("No scene with a configured camera found")


def publish_embedding_frames(pubsub, camera_id, embedding, frames=5, interval=0.1):
  """Publish *frames* copies of one embedded person detection."""
  topic = PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera_id)
  for _ in range(frames):
    pubsub.publish(topic, json.dumps(person_frame(camera_id, embedding)))
    time.sleep(interval)


def controller_logs(env, service):
  return env.docker.compose.logs(services=[service], no_log_prefix=True)


def wait_for_controller_logs(env, publish, pattern, min_count,
                             timeout=SCHEMA_ATTEMPT_TIMEOUT_S):
  """Call *publish* repeatedly until every controller logged *pattern* min_count times.

  @return  Service name -> match count.
  @raise   AssertionError naming each controller short of min_count when *timeout* elapses.
  """
  regex = re.compile(pattern)
  deadline = time.monotonic() + timeout
  while True:
    publish()
    counts = {s: len(regex.findall(controller_logs(env, s))) for s in CONTROLLERS}
    if all(n >= min_count for n in counts.values()):
      return counts
    if time.monotonic() >= deadline:
      short = [s for s, n in counts.items() if n < min_count]
      tails = "\n".join(
        f"--- {s} ---\n" + "\n".join(controller_logs(env, s).splitlines()[-15:])
        for s in short)
      raise AssertionError(
        f"controllers {short} logged fewer than {min_count} match(es) of /{pattern}/ "
        f"within {timeout}s (counts: {counts})\n{tails}")


def assert_no_ready_or_connection_errors(env):
  """No controller reported schema ready or hit a VDMS connection failure."""
  for service in CONTROLLERS:
    text = controller_logs(env, service)
    ready = SCHEMA_READY_LOG.search(text)
    assert not ready, f"{service} reported schema ready: {ready.group(0)}"
    for error in VDMS_CONNECTION_ERRORS:
      assert error not in text, f"{service} logged a VDMS connection error: {error}"


def assert_schema_rejected(env, params, set_name, diagnostic):
  """Check every controller rejects the seeded schema and leaves VDMS untouched.

  @param diagnostic  Text that follows "ensureSchema: '<set_name>' " in the
                     controller's rejection message.
  """
  failure = re.escape(
    f"ReID schema initialization failed: ensureSchema: '{set_name}' {diagnostic}")

  with vdms_client(set_name=set_name) as db:
    seeded = snapshot_vdms_state(db, set_name)

  with mqtt_client(params) as pubsub:
    camera_id = get_camera_id(params)
    embedding = make_embedding()
    publish = lambda: publish_embedding_frames(pubsub, camera_id, embedding)
    wait_for_controller_logs(env, publish, failure, min_count=1)
    assert_no_ready_or_connection_errors(env)
    wait_for_controller_logs(env, publish, failure, min_count=2)

  time.sleep(1)  # let in-flight handlers finish before the final snapshot
  assert_no_ready_or_connection_errors(env)
  with vdms_client(set_name=set_name) as db:
    assert_snapshots_equal(seeded, snapshot_vdms_state(db, set_name))
