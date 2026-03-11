#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import json
from http import HTTPStatus
from tests.functional import FunctionalTest
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub

TEST_NAME = "NEX-T10543"
THING_TYPE = "person"
COLLECT_TIMEOUT = 5.0
MIN_MESSAGES = 5

class RotationFromVelocityTest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    # REST setup
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    res = self.rest.authenticate(self.params['user'], self.params['password'])
    assert res, (res.errors)

    self.scene_id = self.params['scene_id']

    # Create asset
    asset_data = {"name": "person"}
    created = self.rest.createAsset(asset_data)
    assert created.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED)
    self.person_uid = created["uid"]
    print(f"Created PERSON asset UID:", self.person_uid)

    # MQTT setup
    self.client = PubSub(
      self.params.get("auth"),
      None,
      self.params.get("rootcert"),
      self.params["broker_url"],
      int(self.params["broker_port"])
    )

    self.client.onMessage = self.on_message
    self.client.connect()
    self.client.loopStart()

    self.topic = PubSub.formatTopic(
      PubSub.DATA_SCENE,
      scene_id=self.scene_id,
      thing_type="person"
    )
    self.client.subscribe(self.topic)

    # Runtime state
    self.rotations_before = []
    self.rotations_after = []
    self.collect_target = None  # "before" or "after"
    self.exitCode = 1

  # MQTT callback
  def on_message(self, _client, _obj, msg):
    try:
      payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
      return

    for o in payload.get("objects", []):
      if o.get("category") != "person":
        continue
      rot = o.get("rotation")
      if not rot or len(rot) != 4:
        continue

      if self.collect_target == "before":
        self.rotations_before.append(tuple(rot))
      elif self.collect_target == "after":
        self.rotations_after.append(tuple(rot))

  # Update asset
  def set_rotation_from_velocity(self, enable: bool):
    update = self.rest.updateAsset(
      self.person_uid,
      {"rotation_from_velocity": bool(enable)}
    )
    assert update.statusCode == HTTPStatus.OK, f"Update failed: {update.errors}"
    print(f"Set rotation_from_velocity =", enable)

  # Collect messages from the topic
  def collect(self, target_list_name):
    self.collect_target = target_list_name

    start = time.time()
    dest = self.rotations_before if target_list_name == "before" else self.rotations_after
    dest.clear()

    while time.time() - start < COLLECT_TIMEOUT and len(dest) < MIN_MESSAGES:
      time.sleep(0.1)

    assert dest, f"No rotation samples collected during {target_list_name} phase"

  # Test flow
  def run(self):
    try:
      # collect BEFORE enabling rotation-from-velocity
      self.collect("before")

      # enable rotation-from-velocity
      self.set_rotation_from_velocity(True)

      # collect AFTER enabling
      self.collect("after")

      # check for change in rotation
      before_set = set(self.rotations_before)
      after_set = set(self.rotations_after)

      print(f"BEFORE rotation samples:", before_set)
      print(f"AFTER rotation samples:", after_set)

      assert after_set != before_set, \
        "Rotation values did not change after enabling rotation from velocity"

      self.exitCode = 0

    finally:
      try: self.client.removeCallback(self.topic)
      except: pass
      try: self.client.loopStop()
      except: pass
      try: self.client.disconnect()
      except: pass

      self.recordTestResult()
    return

# Pytest entrypoint
def test_rotation_from_velocity(request, record_xml_attribute):
  test = RotationFromVelocityTest(TEST_NAME, request, record_xml_attribute)
  test.run()
  assert test.exitCode == 0
  return test.exitCode
