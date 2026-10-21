#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional end-to-end coverage for non-planar (z) tracking.

Publishes external-source detections with rising agent-frame Z through the
live controller and asserts DATA_SCENE track translation[2] follows the climb.
Complements robot_vision unit tests in tracking_test.py / TrackingTests.cpp.
"""

import json
import time

import numpy as np
import pytest

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from tests.functional import FunctionalTest
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "z-tracking"
THING_TYPE = "person"
FRAMES_PER_SECOND = 10
MAX_WAIT_TIMEOUT_S = 30
CONTROLLER_SETTLE_S = 2.0
AGENT_SOURCE_ID = "drone-1"
OBJECT_ID = "z-climb-1"

# Same geospatial fixture as test_external_source_ingest.py.
MAP_CORNERS_LLA = [[37.38685435, -121.96408120, 8.0], [37.38693520, -121.96408120, 8.0],
                   [37.38693520, -121.96413896, 8.0], [37.38685435, -121.96413896, 8.0]]
AGENT_LAT_LONG_ALT = [37.38688947231117, -121.96410520894621, 8.068826778282563]
EXPECTED_SCENE_XYZ = [3.8679791719486474, 2.7517397452609087, 1.1225254457301852e-19]
SCENE_XYZ_ATOL_M = 0.05
IDENTITY_ROTATION = [0, 0, 0, 1]

# Climb ~2 m over 5 s in the agent frame (identity rotation → scene Z ≈ agent Z).
# Filter has no vz: tracked z lags the measurement ramp, so tolerances allow lag.
CLIMB_DURATION_S = 5.0
CLIMB_VZ_MPS = 0.4
MIN_Z_GAIN_M = 0.5
# Live controller lag is larger than unit-test lag; require nearer truth than ground.
MAX_Z_ERROR_RATIO = 0.65


class ZTracking(FunctionalTest):
  def __init__(self, testName, request, repo_root):
    super().__init__(testName, request, None)
    self.repoRoot = repo_root
    self.exitCode = 1
    self.outputReceived = False
    self.sceneUID = self.params['scene_id']

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

    self.pubsub = PubSub(self.params['auth'], None, self.params['rootcert'],
                         self.params['broker_url'],
                         port=int(self.params['broker_port']))
    self.topic = PubSub.formatTopic(PubSub.DATA_SCENE, scene_id=self.sceneUID,
                                    thing_type=THING_TYPE)
    self.pubsub.onConnect = self.pubsubConnected
    self.pubsub.addCallback(self.topic, self.eventReceived)
    self.pubsub.connect()
    self.pubsub.loopStart()
    self.lastObjects = None
    return

  def pubsubConnected(self, client, userdata, flags, rc):
    self.pubsub.subscribe(self.topic)
    return

  def eventReceived(self, pahoClient, userdata, message):
    data = json.loads(message.payload.decode("utf-8"))
    if data.get('objects'):
      self.lastObjects = data['objects']
      self.outputReceived = True
    return

  def prepareScene(self):
    map_image = f"{self.repoRoot}/tests/resources/maps/HazardZoneSceneLarge.png"
    with open(map_image, "rb") as f:
      map_bytes = f.read()

    updates = [
      {'output_lla': True, 'map_corners_lla': MAP_CORNERS_LLA},
      {
        'output_lla': True,
        'map_corners_lla': json.dumps(MAP_CORNERS_LLA),
        'map': (map_image, map_bytes),
      },
    ]
    for attempt, update in enumerate(updates, start=1):
      res = self.rest.updateScene(self.sceneUID, update)
      assert res, (res.statusCode, res.errors)
      time.sleep(CONTROLLER_SETTLE_S)
      scene = self.rest.getScene(self.sceneUID)
      if scene.get('trs_matrix') or self._probeExternalIngest():
        log.info("Geo calibration ready after attempt %s", attempt)
        return

    assert self._probeExternalIngest(), "Scene geo calibration failed for z-tracking"
    return

  def externalSourceTopic(self):
    return PubSub.formatTopic(PubSub.DATA_EXTERNAL, scene_id=AGENT_SOURCE_ID,
                              thing_type=THING_TYPE)

  def _basePose(self):
    return {
      "reference_frame": "wgs84",
      "lat_long_alt": AGENT_LAT_LONG_ALT,
      "rotation": IDENTITY_ROTATION,
    }

  def _probeExternalIngest(self):
    jdata = {
      "timestamp": get_iso_time(),
      "source_id": AGENT_SOURCE_ID,
      "pose": self._basePose(),
      "objects": [{
        "id": "z-probe-1",
        "category": THING_TYPE,
        "translation": [0.0, 0.0, 0.0],
        "size": [0.5, 0.5, 1.8],
      }],
    }
    return self._publishUntilObjects(jdata, timeout=10.0) is not None

  def _publishUntilObjects(self, jdata, timeout=MAX_WAIT_TIMEOUT_S):
    self.outputReceived = False
    self.lastObjects = None
    topic = self.externalSourceTopic()
    start = time.time()
    while not self.outputReceived and time.time() - start < timeout:
      jdata['timestamp'] = get_iso_time()
      self.pubsub.publish(topic, json.dumps(jdata))
      time.sleep(1 / FRAMES_PER_SECOND)
    return self.lastObjects if self.outputReceived else None

  def _trackedPerson(self):
    assert self.lastObjects, "No scene objects received"
    for obj in self.lastObjects:
      if obj.get('type') == THING_TYPE or obj.get('category') == THING_TYPE:
        return obj
      # Scene output uses 'type'; fall back to any non-empty translation.
      if 'translation' in obj:
        return obj
    raise AssertionError(
      f"No tracked person in scene output: {[o.get('id') for o in self.lastObjects]}")

  def verifyConstantZStaysNearGround(self):
    """Negative: fixed agent-frame z=0 stays near the geospatial ground height."""
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "pose": self._basePose(),
      "objects": [{
        "id": "z-flat-1",
        "category": THING_TYPE,
        "translation": [0.0, 0.0, 0.0],
        "size": [0.5, 0.5, 1.8],
      }],
    }
    assert self._publishUntilObjects(jdata), "Flat-z external publish produced no scene output"
    obj = self._trackedPerson()
    np.testing.assert_allclose(
      obj["translation"], EXPECTED_SCENE_XYZ, atol=SCENE_XYZ_ATOL_M,
      err_msg=f"Flat-z track left the ground plane: {obj['translation']}")
    log.info("PASS: constant z≈0 scene translation=%s", obj["translation"])
    return

  def verifyClimbingZTrackedEndToEnd(self):
    """Positive: rising agent-frame z is tracked into scene translation[2]."""
    topic = self.externalSourceTopic()
    z_samples = []
    start = time.time()
    while time.time() - start < CLIMB_DURATION_S:
      elapsed = time.time() - start
      agent_z = CLIMB_VZ_MPS * elapsed
      # Small xy drift so the track remains dynamic while climbing.
      jdata = {
        "timestamp": get_iso_time(),
        "source_id": AGENT_SOURCE_ID,
        "pose": self._basePose(),
        "objects": [{
          "id": OBJECT_ID,
          "category": THING_TYPE,
          "translation": [0.05 * elapsed, 0.02 * elapsed, agent_z],
          "size": [0.5, 0.5, 1.8],
        }],
      }
      self.pubsub.publish(topic, json.dumps(jdata))
      time.sleep(1 / FRAMES_PER_SECOND)
      if self.lastObjects:
        try:
          obj = self._trackedPerson()
          z_samples.append(float(obj["translation"][2]))
        except AssertionError:
          pass

    assert len(z_samples) >= 5, f"Too few z samples collected: {len(z_samples)}"
    final_z = z_samples[-1]
    expected_z = EXPECTED_SCENE_XYZ[2] + CLIMB_VZ_MPS * CLIMB_DURATION_S
    assert final_z > MIN_Z_GAIN_M, (
      f"Tracked z did not climb off the ground plane: final_z={final_z}, "
      f"samples={z_samples[:3]}..{z_samples[-3:]}")
    assert abs(final_z - expected_z) < abs(0.0 - expected_z) * MAX_Z_ERROR_RATIO, (
      f"Tracked z farther from climb truth than allowed: got {final_z}, "
      f"expected ~{expected_z}")
    q = max(1, len(z_samples) // 4)
    assert np.mean(z_samples[-q:]) > np.mean(z_samples[:q]) + 0.3, (
      f"Tracked z did not increase over the climb: early={z_samples[:q]} "
      f"late={z_samples[-q:]}")
    log.info("PASS: climbing z tracked final_z=%.3f expected~%.3f samples=%d",
             final_z, expected_z, len(z_samples))
    return

  def verifyFunction(self):
    self.prepareScene()
    self.verifyConstantZStaysNearGround()
    self.verifyClimbingZTrackedEndToEnd()
    self.exitCode = 0
    return


@pytest.mark.test_name("NEX-T29370")
def test_z_tracking(scenescape_env, demo_scene, request, repo_root, result_recorder):
  test = ZTracking(TEST_NAME, request, repo_root)
  test.verifyFunction()
  result_recorder.success()
  return
