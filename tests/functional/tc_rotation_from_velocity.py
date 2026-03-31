#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import math
import time
from http import HTTPStatus

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient

from tests.functional import FunctionalTest

TEST_NAME = "NEX-T10543"
COLLECT_TIMEOUT = 10.0
MIN_MESSAGES = 5
PROPAGATION_DELAY = 0.5
IDENTITY_QUAT = (0.0, 0.0, 0.0, 1.0)
ALIGNMENT_PASS_RATIO = 0.98

# turns a vector into a unit vector
def normalize(v):
  n = math.sqrt(sum(x * x for x in v))
  if n == 0:
    return None
  return tuple(x / n for x in v)

# computes angle between two unit vectors
def angle_deg(a, b):
  dot = sum(x * y for x, y in zip(a, b))
  dot = max(-1.0, min(1.0, dot))
  return math.degrees(math.acos(dot))

# Rotates a 3D vector by a quaternion, returning the vector in world space
def quat_rotate_vector(q, v):
  # q = (x, y, z, w), v = (vx, vy, vz)
  x, y, z, w = q
  vx, vy, vz = v

  tx = 2 * (y * vz - z * vy)
  ty = 2 * (z * vx - x * vz)
  tz = 2 * (x * vy - y * vx)

  rx = vx + w * tx + (y * tz - z * ty)
  ry = vy + w * ty + (z * tx - x * tz)
  rz = vz + w * tz + (x * ty - y * tx)

  return (rx, ry, rz)

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

    # Runtime state
    self.rotations_before = []
    self.rotations_enabled = []
    self.rotations_disabled = []
    self.collect_target = None  # "before" | "enabled" | "disabled"
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
      vel = o.get("velocity")
      if not rot or len(rot) != 4:
        continue
      if not vel or len(vel) != 3:
        continue

      quat = tuple(float(v) for v in rot)
      velocity = tuple(float(v) for v in vel)

      if self.collect_target == "before":
        self.rotations_before.append(tuple(quat))
      elif self.collect_target == "enabled":
        self.rotations_enabled.append((quat, velocity))
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

    self.collect_target = None

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
      log.info("Rotation before changing settings (feature OFF):", before_set)

      assert all(all(abs(a - b) < 1e-6 for a, b in zip(q, IDENTITY_QUAT)) for q in before_set), \
        "Spec violation: When OFF, rotation must be the identity quaternion [0,0,0,1]"

      # enable rotation-from-velocity
      self.set_rotation_from_velocity(True)

      # collect AFTER enabling rotation
      self.collect("enabled")
      FORWARD_AXIS = (1.0, 0.0, 0.0)
      MIN_SPEED = 0.05
      MAX_ANGLE = 5.0

      checked = 0
      aligned = 0

      for quat, velocity in list(self.rotations_enabled):
        speed = math.sqrt(sum(x * x for x in velocity))
        if speed < MIN_SPEED:
          continue

        v_dir = normalize(velocity)
        if v_dir is None:
          continue

        forward_world = quat_rotate_vector(quat, FORWARD_AXIS)
        fwd_dir = normalize(forward_world)
        if fwd_dir is None:
          continue

        angle = angle_deg(fwd_dir, v_dir)
        checked += 1

        if angle <= MAX_ANGLE:
          aligned += 1

      assert checked > 0, "No moving objects found to verify velocity alignment"
      alignment_ratio = aligned / checked
      assert alignment_ratio >= ALIGNMENT_PASS_RATIO, (
        f"Alignment ratio too low: {alignment_ratio:.2%} (expected >= {ALIGNMENT_PASS_RATIO:.0%})"
      )

      log.info(
        f"Rotation/velocity alignment: {aligned}/{checked} ({alignment_ratio:.2%}) "
        f"samples within {MAX_ANGLE} degrees"
      )

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
