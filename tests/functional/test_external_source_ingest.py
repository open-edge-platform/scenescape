#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional coverage for the unified external-source ingestion contract
(scenescape/external/{scene_id}/{thing_type} with 'source_id' in the payload).

Complements tests/sscape_tests/scenescape/test_external_source.py (unit,
ExternalSourcePoseCache) and test_scene_controller.py (unit, routing) by
exercising the full MQTT ingestion path against a running controller: a
wgs84-pose agent publish, pose-only cache reuse, and rejection of an
untrusted scene-frame pose.
"""

import json
import os
import time

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
AGENT_SOURCE_ID = "drone-1"
UNTRUSTED_POSITIONING_SOURCE_ID = "positioning-service-untrusted"

# Same verified geospatial calibration fixture as
# tests/functional/test_geospatial_ingest_publish.py.
MAP_CORNERS_LLA = [[ 37.38685435, -121.96408120, 8.0], [ 37.38693520, -121.96408120, 8.0],
      [ 37.38693520, -121.96413896, 8.0], [ 37.38685435, -121.96413896, 8.0]]
AGENT_LAT_LONG_ALT = [37.38688947231117, -121.96410520894621, 8.068826778282563]
IDENTITY_ROTATION = [0, 0, 0, 1]


class ExternalSourceIngest(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute, repo_root):
    super().__init__(testName, request, recordXMLAttribute)
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
    map_image = f"{self.repoRoot}/sample_data/HazardZoneSceneLarge.png"
    with open(map_image, "rb") as f:
      map_data = f.read()
    res = self.rest.updateScene(self.sceneUID, {
      'output_lla': True,
      'map_corners_lla': json.dumps(MAP_CORNERS_LLA),
      'map': (map_image, map_data),
    })
    assert res, (res.statusCode, res.errors)
    scene = self.waitForSceneCondition(
      lambda s: bool(s.get('trs_matrix')),
      "trs_matrix to be computed for external-source geospatial ingest",
    )
    assert scene.get('trs_matrix'), "trs_matrix not populated; scene is not geo-referenced"
    return

  def waitForSceneCondition(self, predicate, description,
                            timeout=MAX_WAIT_TIMEOUT_S, interval=1.0):
    start = time.time()
    scene = self.rest.getScene(self.sceneUID)
    while True:
      scene = self.rest.getScene(self.sceneUID)
      try:
        if predicate(scene):
          return scene
      except Exception as e:
        log.debug("Predicate raised while waiting for %s: %s", description, e)
      if time.time() - start >= timeout:
        break
      time.sleep(interval)
    log.error("Timed out after %ss waiting for %s", timeout, description)
    return scene

  def externalSourceTopic(self):
    return PubSub.formatTopic(PubSub.DATA_EXTERNAL, scene_id=self.sceneUID,
                              thing_type=THING_TYPE)

  def publishAndWait(self, jdata, timeout=MAX_WAIT_TIMEOUT_S):
    self.outputReceived = False
    self.lastObjects = None
    topic = self.externalSourceTopic()
    start = time.time()
    count = 0
    while not self.outputReceived and time.time() - start < timeout:
      jdata['timestamp'] = get_iso_time()
      self.pubsub.publish(topic, json.dumps(jdata))
      time.sleep(1 / FRAMES_PER_SECOND)
      count += 1
    return count if self.outputReceived else None

  def verifyWgs84PoseIngest(self):
    """A wgs84-frame agent pose plus an object observation is transformed
    into the scene and produces tracked output."""
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {"category": THING_TYPE, "translation": [0.0, 0.0, 0.0], "size": [0.5, 0.5, 1.8]},
      ],
    }
    count = self.publishAndWait(jdata)
    assert count, "External source (wgs84 pose) message did not produce tracked output"
    assert self.lastObjects and len(self.lastObjects) > 0
    return

  def verifyPoseReuseFromCache(self):
    """A subsequent message without 'pose' reuses the cached transform."""
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "objects": [
        {"category": THING_TYPE, "translation": [0.5, 0.5, 0.0], "size": [0.5, 0.5, 1.8]},
      ],
    }
    count = self.publishAndWait(jdata)
    assert count, "External source message without pose (cache reuse) did not produce output"
    return

  def verifyUntrustedScenePoseRejected(self):
    """A scene-frame pose from a source not in CONTROLLER_TRUSTED_POSITIONING_SOURCES
    must be rejected: no tracked output is produced for this source."""
    jdata = {
      "source_id": UNTRUSTED_POSITIONING_SOURCE_ID,
      "pose": {
        "reference_frame": "scene",
        "translation": [1.0, 1.0, 0.0],
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {"category": THING_TYPE, "translation": [0.0, 0.0, 0.0], "size": [0.5, 0.5, 1.8]},
      ],
    }
    count = self.publishAndWait(jdata, timeout=5)
    assert count is None, (
      "Untrusted scene-frame pose unexpectedly produced tracked output"
    )
    return

  def verifyFunction(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)

    try:
      self.prepareScene()
      self.verifyWgs84PoseIngest()
      self.verifyPoseReuseFromCache()
      self.verifyUntrustedScenePoseRejected()
      self.exitCode = 0
    finally:
      self.recordTestResult()
    return


def test_external_source_ingest(scenescape_env, demo_scene, request, record_xml_attribute, repo_root):
  test = ExternalSourceIngest(TEST_NAME, request, record_xml_attribute, repo_root)
  test.verifyFunction()
  assert test.exitCode == 0
  return

def main():
  return test_external_source_ingest(None, None)

if __name__ == '__main__':
  os._exit(main() or 0)
