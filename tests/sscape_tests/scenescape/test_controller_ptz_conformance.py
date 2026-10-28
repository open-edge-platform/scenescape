#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Replays the shared dwell conformance vectors through the Controller's PTZ registry.

The exact tests/data/ptz/dwell_conformance.json that the Positioning contract tests
and the Tracker use is loaded unmodified. Every event travels the Controller's real
entry points: raw MQTT bytes, schema validation, guards, topic routing and `admit`.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import orjson
import pytest

from scene_common import positioning_reasons as reasons
from scene_common.camera import Camera
from scene_common.mqtt import PubSub
from scene_common.positioning_config import load_consumer_config
from scene_common.positioning_dwell import parse_timestamp_ns
from scene_common.schema import SchemaValidation
from controller.ptz.config import MODE_ENFORCE, PTZSettings
from controller.ptz.registry import PTZPoseRegistry

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "tests" / "data" / "ptz" / "dwell_conformance.json"
SCHEMA_PATH = REPO_ROOT / "controller" / "src" / "schema" / "metadata.schema.json"

FIXTURE = json.loads(FIXTURE_PATH.read_text())
VECTORS = FIXTURE["vectors"]
SCENE_FRAME_PREFIX = "scene:"


@pytest.fixture(scope="module")
def schema():
  return SchemaValidation(str(SCHEMA_PATH), is_multi_message=True)


def _build_registry(vector, schema):
  consumer = vector["consumer"]
  frame_id = consumer["expected_frame_id"]
  assert frame_id.startswith(SCENE_FRAME_PREFIX)
  source_id = consumer["source_id"]
  calibration = {}
  if consumer["expected_calibration_version"] is not None:
    calibration["calibration_version"] = consumer["expected_calibration_version"]
  camera = Camera(source_id, {"intrinsics": 70, "width": 640, "height": 480,
                              "ptz_calibration": calibration})
  scene = SimpleNamespace(uid=frame_id[len(SCENE_FRAME_PREFIX):], cameras={source_id: camera})
  settings = PTZSettings(
    mode=MODE_ENFORCE,
    consumer=load_consumer_config(vector["config"]),
    assignments={source_id: consumer["resolver_id"]})
  registry = PTZPoseRegistry(settings, schema, lambda: (0, True))
  registry.reconcile([scene])
  return registry, camera


def _replay(vector, schema):
  registry, camera = _build_registry(vector, schema)
  source_id = vector["consumer"]["source_id"]
  pose_topic = PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id=source_id)
  checked = 0
  for index, event in enumerate(vector["events"]):
    where = f"{vector['name']} event #{index}"
    if event["type"] == "status":
      payload = event["payload"]
      topic = PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id=payload["resolver_id"])
      assert registry.on_status_message(topic, orjson.dumps(payload)) is None, where
    elif event["type"] == "pose":
      assert registry.on_pose_message(pose_topic, orjson.dumps(event["payload"])) is None, where
    else:
      admission = registry.admit(camera, parse_timestamp_ns(event["timestamp"]),
                                 local_now_ns=parse_timestamp_ns(event["local_now"]))
      expected = event["expected"]
      actual = {"admitted": admission.admitted}
      if not admission.admitted:
        actual["invalid_reason"] = admission.invalid_reason
        actual["reason_detail"] = admission.reason_detail
      assert actual == expected, where
      assert (admission.context is not None) == expected["admitted"], where
      checked += 1
  return checked


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_controller_matches_conformance_vector(vector, schema):
  assert _replay(vector, schema) > 0


def test_controller_covers_every_reason_detail_of_the_fixture():
  seen = set()
  for vector in VECTORS:
    for event in vector["events"]:
      if event["type"] == "observation" and not event["expected"]["admitted"]:
        seen.add(event["expected"]["reason_detail"])
  assert seen == set(reasons.ALL_REASON_DETAILS)
