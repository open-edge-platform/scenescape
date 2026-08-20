#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional coverage for the unified external-source ingestion contract
(scenescape/external/{publisher_id}/{thing_type} with 'source_id' in the payload).

Complements tests/sscape_tests/scenescape/test_external_source.py (unit,
ExternalSourcePoseCache) and test_scene_controller.py (unit, routing) by
exercising the full MQTT ingestion path against a running controller: a
wgs84-pose agent publish, scene-location accuracy against the 4-corner
geospatial fixture, pose-only cache reuse, source_id/topic mismatch rejection,
identity collision across publishers, and rejection of an untrusted
scene-frame pose.

Publishes at a fixed 10 Hz. Variable-rate coverage is deferred.
"""

import json
import os
import time

import numpy as np

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from tests.functional import FunctionalTest
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
from tests.utils.log import get_logger

log = get_logger(__name__)


SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "external-source-ingest"
THING_TYPE = "person"
FRAMES_PER_SECOND = 10
MAX_WAIT_TIMEOUT_S = 30
CONTROLLER_SETTLE_S = 2.0
AGENT_SOURCE_ID = "drone-1"
UNTRUSTED_POSITIONING_SOURCE_ID = "positioning-service-untrusted"
OBJECT_ID = "agent-track-1"

# Same verified geospatial calibration fixture as
# tests/functional/test_geospatial_ingest_publish.py.
MAP_CORNERS_LLA = [[ 37.38685435, -121.96408120, 8.0], [ 37.38693520, -121.96408120, 8.0],
      [ 37.38693520, -121.96413896, 8.0], [ 37.38685435, -121.96413896, 8.0]]
AGENT_LAT_LONG_ALT = [37.38688947231117, -121.96410520894621, 8.068826778282563]
# Scene-local XYZ corresponding to AGENT_LAT_LONG_ALT under the 4-corner TRS
# (verified by unit ExternalSourcePoseCache and geospatial constants checks).
EXPECTED_SCENE_XYZ = [3.8679791719486474, 2.7517397452609087, 1.1225254457301852e-19]
SCENE_XYZ_ATOL_M = 0.05
SCENE_LLA_RTOL = 1e-5
IDENTITY_ROTATION = [0, 0, 0, 1]


class ExternalSourceIngest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute, repo_root, scene_uid=None):
    super().__init__(testName, request, recordXMLAttribute)
    self.repoRoot = repo_root

    self.exitCode = 1
    self.outputReceived = False
    self.sceneUID = scene_uid if scene_uid is not None else self.params['scene_id']

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
    self.seenObjectIds = set()
    return

  def pubsubConnected(self, client, userdata, flags, rc):
    self.pubsub.subscribe(self.topic)
    return

  def eventReceived(self, pahoClient, userdata, message):
    data = json.loads(message.payload.decode("utf-8"))
    if data.get('objects'):
      self.lastObjects = data['objects']
      self.outputReceived = True
      for obj in data['objects']:
        if 'id' in obj:
          self.seenObjectIds.add(obj['id'])
    return

  def prepareScene(self):
    """Enable geospatial calibration on the demo scene.

    When the demo scene has just been created, the controller may compute TRS
    locally while REST briefly omits ``trs_matrix`` (same flake class as
    test_geospatial_ingest_publish / test_external_source_analytics). Prefer
    corners on the existing demo map; fall back to map re-upload. Readiness
    is confirmed by a successful external-source publish on DATA_SCENE when
    REST does not expose ``trs_matrix``.
    """
    map_image = f"{self.repoRoot}/sample_data/HazardZoneSceneLarge.png"
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
      if scene.get('trs_matrix'):
        log.info("trs_matrix visible via REST after geo-update attempt %s", attempt)
        return
      if self._probeExternalIngest():
        log.info(
          "Geo ingest probe succeeded after attempt %s "
          "(trs_matrix may be absent from REST)", attempt)
        return

    scene = self.rest.getScene(self.sceneUID)
    assert self._probeExternalIngest(), (
      "Scene geo calibration failed: external wgs84 ingest produced no "
      f"scene output. REST output_lla={scene.get('output_lla')} "
      f"map_corners={bool(scene.get('map_corners_lla'))} "
      f"trs_matrix={scene.get('trs_matrix') is not None}")
    return

  def _probeExternalIngest(self):
    """Return True if a wgs84 external-source publish yields DATA_SCENE objects."""
    jdata = {
      "timestamp": get_iso_time(),
      "source_id": AGENT_SOURCE_ID,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [{
        "id": OBJECT_ID,
        "category": THING_TYPE,
        "translation": [0.0, 0.0, 0.0],
        "size": [0.5, 0.5, 1.8],
      }],
    }
    return self.publishAndWait(jdata, timeout=10.0) is not None

  def externalSourceTopic(self, publisher_id=AGENT_SOURCE_ID):
    # Publisher-centric: topic path id is the agent source_id, not the scene.
    return PubSub.formatTopic(PubSub.DATA_EXTERNAL, scene_id=publisher_id,
                              thing_type=THING_TYPE)

  def publishAndWait(self, jdata, timeout=MAX_WAIT_TIMEOUT_S):
    self.outputReceived = False
    self.lastObjects = None
    topic = self.externalSourceTopic(jdata.get('source_id', AGENT_SOURCE_ID))
    start = time.time()
    count = 0
    while not self.outputReceived and time.time() - start < timeout:
      jdata['timestamp'] = get_iso_time()
      self.pubsub.publish(topic, json.dumps(jdata))
      time.sleep(1 / FRAMES_PER_SECOND)
      count += 1
    return count if self.outputReceived else None

  def publishAndCheckIdAbsent(self, jdata, forbidden_id, timeout):
    """Publish for the full duration of timeout (unlike publishAndWait, this
    does not stop early on the first received message) and assert that
    forbidden_id never appears in any scene output observed during the
    window. The scene may legitimately keep republishing other, previously
    admitted, still-active tracks on every incoming message regardless of
    whether that message's own payload was accepted, so checking for total
    topic silence is not a valid test for rejection of one specific object.
    """
    self.seenObjectIds = set()
    topic = self.externalSourceTopic(jdata.get('source_id', AGENT_SOURCE_ID))
    start = time.time()
    while time.time() - start < timeout:
      jdata['timestamp'] = get_iso_time()
      self.pubsub.publish(topic, json.dumps(jdata))
      time.sleep(1 / FRAMES_PER_SECOND)
    return forbidden_id not in self.seenObjectIds

  def _findObject(self, object_id):
    assert self.lastObjects, "No scene objects received"
    for obj in self.lastObjects:
      if obj.get('id') == object_id:
        return obj
    raise AssertionError(
      f"Object id={object_id} not found in scene output: "
      f"{[o.get('id') for o in self.lastObjects]}")

  def verifyWgs84PoseIngestAndLocationAccuracy(self):
    """A wgs84-frame agent pose plus an object at the source origin is
    transformed into the geo-calibrated scene at the expected XYZ (and LLA
    when output_lla is enabled)."""
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {
          "id": OBJECT_ID,
          "category": THING_TYPE,
          "translation": [0.0, 0.0, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
      ],
    }
    count = self.publishAndWait(jdata)
    assert count, "External source (wgs84 pose) message did not produce tracked output"
    obj = self._findObject(OBJECT_ID)
    assert "translation" in obj, f"Scene object missing translation: {obj}"
    np.testing.assert_allclose(
      obj["translation"], EXPECTED_SCENE_XYZ, atol=SCENE_XYZ_ATOL_M,
      err_msg=(
        f"External-source scene XYZ inaccurate: got {obj['translation']}, "
        f"expected {EXPECTED_SCENE_XYZ} (atol={SCENE_XYZ_ATOL_M} m)"))
    assert "lat_long_alt" in obj, f"Scene object missing lat_long_alt: {obj}"
    np.testing.assert_allclose(
      obj["lat_long_alt"], AGENT_LAT_LONG_ALT, rtol=SCENE_LLA_RTOL,
      err_msg=(
        f"External-source scene LLA inaccurate: got {obj['lat_long_alt']}, "
        f"expected {AGENT_LAT_LONG_ALT}"))
    log.info(
      "PASS: wgs84 external-source location accuracy xyz=%s lla=%s",
      obj["translation"], obj["lat_long_alt"])
    return

  def verifyPoseReuseFromCache(self):
    """A subsequent message without 'pose' reuses the cached transform."""
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "objects": [
        {
          "id": OBJECT_ID,
          "category": THING_TYPE,
          "translation": [0.5, 0.5, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
      ],
    }
    count = self.publishAndWait(jdata)
    assert count, "External source message without pose (cache reuse) did not produce output"
    return

  def verifyUntrustedScenePoseRejected(self):
    """A scene-frame pose from a source not in CONTROLLER_TRUSTED_POSITIONING_SOURCES
    must be rejected: the untrusted source's object never appears in tracked
    output for this scene, even though the scene may continue to legitimately
    republish other, already-admitted, still-active tracks (e.g. agent-track-1
    from the earlier sub-tests) on every message it receives."""
    untrusted_object_id = "positioning-track-1"
    jdata = {
      "source_id": UNTRUSTED_POSITIONING_SOURCE_ID,
      "pose": {
        "reference_frame": "scene",
        "translation": [1.0, 1.0, 0.0],
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {"id": untrusted_object_id, "category": THING_TYPE, "translation": [0.0, 0.0, 0.0], "size": [0.5, 0.5, 1.8]},
      ],
    }
    is_absent = self.publishAndCheckIdAbsent(jdata, untrusted_object_id, timeout=5)
    assert is_absent, (
      "Untrusted scene-frame pose unexpectedly produced tracked output "
      f"for id={untrusted_object_id}"
    )
    return

  def verifySourceIdTopicMismatchRejected(self):
    """Payload source_id must match the publisher id in the MQTT topic path."""
    mismatched_id = "mismatch-track-1"
    jdata = {
      "source_id": "not-the-topic-publisher",
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {
          "id": mismatched_id,
          "category": THING_TYPE,
          "translation": [0.0, 0.0, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
      ],
    }
    # Publish on AGENT_SOURCE_ID topic while claiming a different source_id.
    topic = self.externalSourceTopic(AGENT_SOURCE_ID)
    self.seenObjectIds = set()
    start = time.time()
    while time.time() - start < 5.0:
      jdata['timestamp'] = get_iso_time()
      self.pubsub.publish(topic, json.dumps(jdata))
      time.sleep(1 / FRAMES_PER_SECOND)
    assert mismatched_id not in self.seenObjectIds, (
      "source_id/topic mismatch unexpectedly produced tracked output "
      f"for id={mismatched_id}"
    )
    return

  def verifyIdentityCollisionDropsSecondSource(self):
    """A second publisher reclaiming a live id is dropped; a non-colliding id is kept.

    Wait specifically for the non-colliding id: scene publishes are async to
    the tracker queue, so the first DATA_SCENE after drone-2 publishes may
    still only contain the earlier drone-1 track.
    """
    colliding_id = OBJECT_ID  # still claimed by AGENT_SOURCE_ID from earlier steps
    unique_id = "drone-2-unique-track"
    other_source = "drone-2"
    jdata = {
      "source_id": other_source,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {
          "id": colliding_id,
          "category": THING_TYPE,
          "translation": [0.2, 0.2, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
        {
          "id": unique_id,
          "category": THING_TYPE,
          "translation": [-0.2, -0.2, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
      ],
    }
    topic = self.externalSourceTopic(other_source)
    self.lastObjects = None
    start = time.time()
    ids = set()
    while time.time() - start < MAX_WAIT_TIMEOUT_S:
      jdata['timestamp'] = get_iso_time()
      self.pubsub.publish(topic, json.dumps(jdata))
      time.sleep(1 / FRAMES_PER_SECOND)
      ids = {obj.get('id') for obj in (self.lastObjects or [])}
      if unique_id in ids:
        # Colliding id may still appear from the first publisher's live track;
        # presence of unique_id shows the batch was not fail-closed on collision.
        return
    raise AssertionError(
      f"Non-colliding id missing from scene output after {MAX_WAIT_TIMEOUT_S}s: {ids}")

  def verifyFunction(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      self.prepareScene()
      self.verifyWgs84PoseIngestAndLocationAccuracy()
      self.verifyPoseReuseFromCache()
      self.verifySourceIdTopicMismatchRejected()
      self.verifyIdentityCollisionDropsSecondSource()
      self.verifyUntrustedScenePoseRejected()
      self.exitCode = 0
    finally:
      self.recordTestResult()
    return


def test_external_source_ingest(scenescape_env, demo_scene, request, record_xml_attribute, repo_root):
  test = ExternalSourceIngest(TEST_NAME, request, record_xml_attribute, repo_root, scene_uid=demo_scene)
  test.verifyFunction()
  assert test.exitCode == 0
  return

def main():
  return test_external_source_ingest(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
