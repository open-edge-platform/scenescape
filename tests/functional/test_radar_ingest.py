#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for first-class radar sensor MQTT ingest.

Covers:
  - Provision radar via REST with scene pose
  - Publish detector JSON on DATA_RADAR
  - Controller emits tracked objects on DATA_REGULATED
"""

import json
import time
import uuid

import pytest

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time

from tests.functional.common_service import ServiceMqttTest
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

pytestmark = pytest.mark.preserve_db

FRAME_RATE = 10
RADAR_ID = f"radar-func-{uuid.uuid4().hex[:8]}"
RADAR_NAME = f"Radar Func {RADAR_ID}"


def _radar_detection(radar_id, with_objects=True):
  payload = {
    "id": radar_id,
    "objects": {},
    "rate": float(FRAME_RATE),
    "timestamp": get_iso_time(),
  }
  if with_objects:
    # Sensor-local metres; Controller applies radar extrinsics.
    payload["objects"] = {
      "vehicle": [
        {
          "id": 1,
          "category": "vehicle",
          "translation": [5.0, 0.0, 0.0],
          "size": [2.0, 1.5, 1.5],
          "confidence": 0.9,
        }
      ]
    }
  return payload


def _publish_until_tracked(tester, radar_topic):
  end = time.time() + tester.MAX_WAIT_S
  while time.time() < end:
    tester.publish(radar_topic, json.dumps(_radar_detection(RADAR_ID)))
    time.sleep(1.0 / FRAME_RATE)
    if tester.has_objects():
      return True
  return False


@pytest.fixture
def radar_sensor(params, scene_uid):
  """Create a posed radar on the demo scene; delete on teardown."""
  rest = RESTClient(params['resturl'], rootcert=params['rootcert'])
  assert rest.authenticate(params['user'], params['password'])
  created = rest.createRadar({
    "name": RADAR_NAME,
    "sensor_id": RADAR_ID,
    "scene": scene_uid,
    "transform_type": "euler",
    "translation": [0.0, 0.0, 0.0],
    "rotation": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
  })
  assert created, (getattr(created, 'statusCode', None), getattr(created, 'errors', None))
  # Allow controller to refresh subscriptions after CMD_DATABASE.
  time.sleep(3)
  try:
    yield RADAR_ID
  finally:
    try:
      rest.deleteRadar(RADAR_ID)
    except Exception as exc:
      log.warning("Failed to delete radar %s: %s", RADAR_ID, exc)


@pytest.fixture
def mqtt_tester(params):
  h = ServiceMqttTest(params)
  try:
    yield h
  finally:
    h.disconnect()


@pytest.mark.test_name("NEX-T99001")
def test_radar_ingest_publishes_regulated(
    result_recorder, scene_uid, radar_sensor, mqtt_tester):
  """! Provision radar, publish DATA_RADAR detections, expect DATA_REGULATED tracks."""
  radar_topic = PubSub.formatTopic(PubSub.DATA_RADAR, radar_id=radar_sensor)
  reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)

  mqtt_tester.connect([reg_topic])
  ok = _publish_until_tracked(mqtt_tester, radar_topic)
  assert ok, (
    f"No DATA_REGULATED message with tracked objects on {reg_topic} "
    f"within {mqtt_tester.MAX_WAIT_S}s after publishing on {radar_topic}"
  )
  log.info("PASS: radar ingest produced regulated scene objects")
  result_recorder.success()


@pytest.mark.test_name("NEX-T99002")
def test_radar_unknown_id_ignored(result_recorder, scene_uid, mqtt_tester):
  """! Publishing on an unprovisioned radar id must not yield regulated objects."""
  bad_id = f"radar-missing-{uuid.uuid4().hex[:8]}"
  radar_topic = PubSub.formatTopic(PubSub.DATA_RADAR, radar_id=bad_id)
  reg_topic = PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_uid)

  mqtt_tester.connect([reg_topic])
  mqtt_tester.clear_messages()
  end = time.time() + 5
  while time.time() < end:
    mqtt_tester.publish(radar_topic, json.dumps(_radar_detection(bad_id)))
    time.sleep(0.2)
  assert not mqtt_tester.has_objects(), \
    "Unprovisioned radar should not produce regulated objects"
  log.info("PASS: unknown radar id ignored")
  result_recorder.success()
