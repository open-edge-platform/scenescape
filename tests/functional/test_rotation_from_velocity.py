#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import math
import threading
import time
from http import HTTPStatus

from tests.utils.log import get_logger
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient

from tests.functional import FunctionalTest
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK_WITH_RETAIL_VIDEO

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_WITH_RETAIL_VIDEO,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "NEX-T10543"
COLLECT_TIMEOUT = 30.0
MIN_MESSAGES = 5
PROPAGATION_DELAY = 0.5
WARMUP_TIMEOUT = 60.0
DETECTION_WAIT_TIMEOUT = 90.0
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

    # Demo DB already has a "person" asset; reuse it (create only if missing).
    assets = self.rest.getAssets(None)
    assert assets, (getattr(assets, "statusCode", None), getattr(assets, "errors", None))
    results = assets.get("results") or []
    person = next((a for a in results if a.get("name") == "person"), None)
    if person:
      self.asset_uid = person["uid"]
      log.info(f"Using existing PERSON asset UID: {self.asset_uid}")
    else:
      res = self.rest.createAsset({"name": "person"})
      assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), (
        res.statusCode, res.errors)
      self.asset_uid = res["uid"]
      log.info(f"Created PERSON asset UID: {self.asset_uid}")

    # MQTT setup — subscribe from onConnect so the session is ready.
    self.topic = PubSub.formatTopic(
      PubSub.DATA_SCENE,
      scene_id=self.scene_id,
      thing_type="person"
    )
    self._mqtt_ready = threading.Event()
    self.client = PubSub(self.params["auth"], None, self.params["rootcert"],
                         self.params["broker_url"],
                         port=int(self.params["broker_port"]))
    self.client.onConnect = self._on_mqtt_connect
    self.client.onMessage = self.on_message
    self.client.connect()
    self.client.loopStart()
    assert self._mqtt_ready.wait(30), "MQTT failed to connect/subscribe"

    # Runtime state
    self.rotations_before = []
    self.rotations_enabled = []
    self.rotations_disabled = []
    self.collect_target = None  # "before" | "enabled" | "disabled"
    self.exitCode = 1

  def _on_mqtt_connect(self, mqttc, _obj, _flags, rc):
    if rc == 0:
      mqttc.subscribe(self.topic)
      self._mqtt_ready.set()
    return

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
    log.info(f"Set rotation_from_velocity = {enable}")
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
      # Wait for retail-video detections before measuring rotations.
      log.info("Waiting for person detections on %s ...", self.topic)
      self.collect_target = "before"
      start = time.time()
      while time.time() - start < DETECTION_WAIT_TIMEOUT and not self.rotations_before:
        time.sleep(0.2)
      self.collect_target = None
      assert self.rotations_before, (
        f"No person detections with rotation/velocity within {DETECTION_WAIT_TIMEOUT}s "
        f"on topic '{self.topic}'")

      # ensure feature is OFF at start and verify OFF-state rotation is identity
      self.set_rotation_from_velocity(False)

      # collect BEFORE enabling rotation
      self.collect("before")
      before_set = set(self.rotations_before)
      log.info(f"Rotation before changing settings (feature OFF): {before_set}")

      assert all(all(abs(a - b) < 1e-6 for a, b in zip(q, IDENTITY_QUAT)) for q in before_set), \
        "Spec violation: When OFF, rotation must be the identity quaternion [0,0,0,1]"

      # enable rotation-from-velocity
      self.set_rotation_from_velocity(True)

      # wait until feature is active (first non-identity rotation appears)
      log.info("Waiting for rotation-from-velocity to take effect (warmup)...")
      self.collect_target = "enabled"
      start = time.time()
      while time.time() - start < WARMUP_TIMEOUT:
        if self.rotations_enabled:
          quat, _ = self.rotations_enabled[-1]
          if not all(abs(a - b) < 1e-6 for a, b in zip(quat, IDENTITY_QUAT)):
            log.info(f"Feature active after {time.time() - start:.2f}s — first non-identity rotation: {quat}")
            break
        time.sleep(0.1)
      else:
        log.info("WARNING: warmup timed out without observing a non-identity rotation")
      self.collect_target = None

      # collect AFTER enabling rotation
      self.collect("enabled")
      log.info(f"Collected {len(self.rotations_enabled)} samples for alignment check")
      FORWARD_AXIS = (1.0, 0.0, 0.0)
      MIN_SPEED = 0.15
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
        else:
          log.info(f"Misaligned sample: angle={angle:.1f}° vel={velocity} fwd={forward_world}")

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
      log.info(f"Rotation after disabling rotation-from-velocity (feature OFF): {disabled_set}")

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
def test_rotation_from_velocity(scenescape_env, demo_scene, request, record_xml_attribute):
  test = RotationFromVelocityTest(TEST_NAME, request, record_xml_attribute)
  test.run()
  assert test.exitCode == 0
