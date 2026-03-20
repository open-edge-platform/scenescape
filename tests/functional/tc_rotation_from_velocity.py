#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import json
from http import HTTPStatus
from tests.functional import FunctionalTest
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub
from scene_common import log

TEST_NAME = "NEX-T10543"
COLLECT_TIMEOUT = 10.0
MIN_MESSAGES = 5
PROPAGATION_DELAY = 0.5
IDENTITY_QUAT = (0.0, 0.0, 0.0, 1.0)

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
    res = self.rest.createAsset(asset_data)
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED)
    self.asset_uid = res["uid"]
    log.info(f"Created PERSON asset UID:", self.asset_uid)

    # MQTT setup
    self.client = PubSub(self.params["auth"], None, self.params["rootcert"], self.params["broker_url"])
    self.client.connect()
    self.client.loopStart()
    
    self.topic = PubSub.formatTopic(
      PubSub.DATA_SCENE,
      scene_id=self.scene_id,
      thing_type="person"
    )

    self.client.addCallback(self.topic, self.on_message)
    self.client.subscribe(self.topic)

    # Runtime state
    self.rotations_before = []
    self.rotations_enabled = []
    self.rotations_disabled = []
    self.collect_target = None  # "before" | "after" | "disabled"
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

      quat = tuple(float(v) for v in rot)
      if self.collect_target == "before":
        self.rotations_before.append(tuple(quat))
      elif self.collect_target == "enabled":
        self.rotations_enabled.append(tuple(quat))
      elif self.collect_target == "disabled":
        self.rotations_disabled.append(tuple(quat))

  # Update asset
  def set_rotation_from_velocity(self, enable: bool):
    update = self.rest.updateAsset(
      self.asset_uid,
      {"rotation_from_velocity": bool(enable)}
    )
    assert update.statusCode == HTTPStatus.OK, f"Update failed: {update.errors}"
    log.info(f"Set rotation_from_velocity =", enable)
    time.sleep(PROPAGATION_DELAY)

  # Collect messages from the topic
  def collect(self, target_list_name: str):
    assert target_list_name in {"before", "enabled", "disabled"}
    self.collect_target = target_list_name    
    dest = {
        "before": self.rotations_before,
        "enabled": self.rotations_enabled,
        "disabled": self.rotations_disabled,
    }[target_list_name]
    dest.clear()

    start = time.time()    
    while time.time() - start < COLLECT_TIMEOUT and len(dest) < MIN_MESSAGES:
        time.sleep(0.05)

    assert len(dest) >= MIN_MESSAGES, (
        f"Collected {len(dest)} messages for phase '{target_list_name}', "
        f"expected >= {MIN_MESSAGES} from topic '{self.topic}'"
    )

  # Test flow
  def run(self):
    try:
      # ensure feature is OFF at start and verify OFF-state rotation is identity
      self.set_rotation_from_velocity(False)
      
      # collect BEFORE enabling rotation
      self.collect("before")
      before_set = set(self.rotations_before)
      log.info(f"Rotation before changing settings (feature OFF):", before_set)

      assert all(all(abs(a - b) < 1e-6 for a, b in zip(q, IDENTITY_QUAT)) for q in before_set), \
          "Spec violation: When OFF, rotation must be the identity quaternion [0,0,0,1]"

      # enable rotation-from-velocity
      self.set_rotation_from_velocity(True)

      # collect AFTER enabling rotation
      self.collect("enabled")
      enabled_set = set(self.rotations_enabled)
      log.info(f"Rotation after enabling rotation-from-velocity (feature ON):", enabled_set)
      
      assert enabled_set != before_set, \
          "Rotation values did not change after enabling rotation from velocity"            
      assert any(any(abs(a - b) > 1e-6 for a, b in zip(q, IDENTITY_QUAT)) for q in enabled_set), \
          "When ON, rotation should differ from the identity quaternion"

      # disable again and verify rotations return to identity
      self.set_rotation_from_velocity(False)
      
      self.collect("disabled")
      disabled_set = set(self.rotations_disabled)
      log.info(f"Rotation after disabling rotation-from-velocity (feature OFF):", disabled_set)
      
      assert all(all(abs(a - b) < 1e-6 for a, b in zip(q, IDENTITY_QUAT)) for q in disabled_set), \
          "Rotations did not return to identity after disabling rotation"
      
      log.info("Rotation has successfully returned to the default (identity) rotation.")

      self.exitCode = 0
    finally:
      try: self.client.removeCallback(self.topic)
      except: pass
      try: self.client.loopStop()
      except: pass
      try: self.client.disconnect()
      except: pass
      try: self.rest.deleteAsset(self.asset_uid)
      except: pass
      
      self.recordTestResult()
    return

# Pytest entrypoint
def test_rotation_from_velocity(request, record_xml_attribute):
  test = RotationFromVelocityTest(TEST_NAME, request, record_xml_attribute)
  test.run()
  assert test.exitCode == 0
  return test.exitCode
