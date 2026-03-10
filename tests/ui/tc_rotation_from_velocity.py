#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import json
import math
from http import HTTPStatus
from tests.functional import FunctionalTest
from scene_common.rest_client import RESTClient
from scene_common.mqtt import PubSub

TEST_NAME = "NEX-00000"
THING_TYPE = "person"

# configuration
WARMUP_SEC = 2.0            # time for controller to apply asset change
COLLECT_TIMEOUT_SEC = 12.0  # max time to wait for messages per phase
MIN_MESSAGES = 10           # min scene/person messages per phase
VEL_EPS = 1e-6              # zero-velocity threshold
TOL_OFF = 3e-2              # quaternion tolerance (OFF)
TOL_ON  = 4e-2              # quaternion tolerance (ON)
IDENTITY_Q = (0.0, 0.0, 0.0, 1.0)

class RotationFromVelocity(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    res = self.rest.authenticate(self.params['user'], self.params['password'])
    assert res, (res.errors)

    self.scene_id = self.params['scene_id']
    self.person_asset_uid = self.params['person_asset_uid']

    # MQTT client wiring
    self.client = PubSub(
      self.params.get("auth"),
      None,
      self.params.get("rootcert"),
      self.params["broker_url"],
      int(self.params["broker_port"])
    )
    # Set callbacks and connect
    self.client.onMessage = self.on_message
    self.client.connect()
    self.client.loopStart()

    # Build topic
    self.topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=self.scene_id, thing_type=THING_TYPE)  # scenescape/data/scene/<id>/person
    self.client.subscribe(self.topic)

    # Runtime state
    self.samples = []     # collected (vx, vy, q) per phase
    self.exitCode = 1

  # MQTT callback
  def on_message(self, _client, _obj, msg):
    try:
      payload = json.loads(msg.payload.decode("utf-8"))
    except Exception:
      return
    for o in payload.get("objects", []):
      if o.get("category") != THING_TYPE:
        continue
      rot = o.get("rotation")
      vel = o.get("velocity")
      if not rot or not vel or len(rot) != 4 or len(vel) < 2:
        continue
      vx, vy = float(vel[0]), float(vel[1])
      q = (float(rot[0]), float(rot[1]), float(rot[2]), float(rot[3]))
      self.samples.append((vx, vy, q))

  def set_rotation_from_velocity(self, enable: bool):
    res = self.rest.updateAsset(self.person_asset_uid, {"rotation_from_velocity": bool(enable)})
    assert res.statusCode == HTTPStatus.OK, f"Failed to update asset: {getattr(res, 'errors', res)}"

  def _quat_close(self, q, p, tol):
    # handle double-cover (q and -q represent the same rotation)
    same = all(abs(q[i] - p[i]) <= tol for i in range(4))
    neg  = all(abs(-q[i] - p[i]) <= tol for i in range(4))
    return same or neg

  def _expected_quat_from_vel(self, vx: float, vy: float):
    if abs(vx) < VEL_EPS and abs(vy) < VEL_EPS:
      return None
    yaw = math.atan2(vy, vx)
    return (0.0, 0.0, math.sin(yaw/2.0), math.cos(yaw/2.0))

  def _validate_off(self) -> bool:
    validated = False
    for vx, vy, q in list(self.samples):
      if abs(vx) < VEL_EPS and abs(vy) < VEL_EPS:
        continue  # skip stationary samples
      if not self._quat_close(q, IDENTITY_Q, TOL_OFF):
        raise AssertionError(f"[OFF] Expected {IDENTITY_Q}, got {q} for v=({vx},{vy})")
      validated = True
    return validated

  def _validate_on(self) -> bool:
    validated = False
    for vx, vy, q in list(self.samples):
      exp = self._expected_quat_from_vel(vx, vy)
      if exp is None:
        continue  # skip stationary samples
      if not self._quat_close(q, exp, TOL_ON):
        raise AssertionError(f"[ON] Quaternion {q} != {exp} for v=({vx},{vy})")
      validated = True
    return validated

  def run_phase(self, enable_rotation: bool):
    self.set_rotation_from_velocity(enable_rotation)
    time.sleep(WARMUP_SEC)

    # Collect a window of scene/person messages
    self.samples.clear()
    start = time.time()
    while time.time() - start < COLLECT_TIMEOUT_SEC and len(self.samples) < MIN_MESSAGES:
      time.sleep(0.1)

    if len(self.samples) == 0:
      raise AssertionError("No person objects received on scene topic.")

    # Validate this phase
    ok = self._validate_on() if enable_rotation else self._validate_off()
    if not ok:
      raise AssertionError("No suitable moving sample found to validate this phase.")

  def run(self):
    try:
      # Phase 1: Rotation OFF
      self.run_phase(False)
      # Phase 2: Rotation ON
      self.run_phase(True)
      self.exitCode = 0
    finally:
      try:
        self.client.removeCallback(self.topic)
      except Exception:
        pass
      try:
        self.client.loopStop()
      except Exception:
        pass
      try:
        self.client.disconnect()
      except Exception:
        pass
      self.recordTestResult()
    return

def test_rotation_from_velocity_api_mqtt(request, record_xml_attribute):
  test = RotationFromVelocity(TEST_NAME, request, record_xml_attribute)
  test.run()
  assert test.exitCode == 0
  return test.exitCode
