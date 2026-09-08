#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional coverage: external-source objects interact with ROI and tripwire
analytics after a wgs84 geopose is transformed into a 4-corner geo-calibrated
scene.

Publishes at a fixed 10 Hz. Variable-rate coverage is deferred.
"""

from __future__ import annotations

import json
import os
import time
from http import HTTPStatus

from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient
from scene_common.timestamp import get_iso_time
from tests.functional.event_asserts import check_event_contains_data
from tests.functional import FunctionalTest
from tests.utils.log import get_logger
from tests.utils.profiles import FULL_STACK
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

TEST_NAME = "external-source-analytics"
THING_TYPE = "person"
FRAMES_PER_SECOND = 10
MAX_WAIT_TIMEOUT_S = 30
GEO_SETUP_TIMEOUT_S = 60
CONTROLLER_SETTLE_S = 2.0
AGENT_SOURCE_ID = "drone-analytics-1"
OBJECT_ID = "ext-analytics-track-1"
ROI_NAME = "ExternalSource_ROI"
TW_NAME = "ExternalSource_Tripwire"

# Same verified geospatial calibration fixture as
# tests/functional/test_geospatial_ingest_publish.py /
# test_external_source_ingest.py.
MAP_CORNERS_LLA = [
  [37.38685435, -121.96408120, 8.0], [37.38693520, -121.96408120, 8.0],
  [37.38693520, -121.96413896, 8.0], [37.38685435, -121.96413896, 8.0],
]
AGENT_LAT_LONG_ALT = [37.38688947231117, -121.96410520894621, 8.068826778282563]
# Scene XYZ for AGENT_LAT_LONG_ALT ≈ [3.87, 2.75, 0] — inside ROI below.
IDENTITY_ROTATION = [0.0, 0.0, 0.0, 1.0]

# Rectangle that contains EXPECTED_SCENE_XYZ (~3.87, 2.75); same family as
# tests/functional/common_scene_obj.py ROI geometry.
ROI_POINTS = ((0.9, 4.0), (0.9, 2.4), (8.1, 2.4), (8.1, 4.0))
# Source-local offsets relative to the wgs84 pose origin.
INSIDE_ROI_OFFSET = [0.0, 0.0, 0.0]       # scene ≈ [3.87, 2.75]
OUTSIDE_ROI_OFFSET = [0.0, -3.0, 0.0]     # scene ≈ [3.87, -0.25]

# Horizontal tripwire across demo-scene center (same as tripwire MQTT tests).
_DEMO_CX = 900 / (2 * 100)  # 4.5 m
_DEMO_CY = 643 / (2 * 100)  # 3.215 m
_DEMO_DX = _DEMO_CX * 0.8
TW_POINTS = ((_DEMO_CX - _DEMO_DX, _DEMO_CY), (_DEMO_CX + _DEMO_DX, _DEMO_CY))
# Cross the tripwire from south to north in source-local Y.
TW_SOUTH_OFFSET = [0.0, -1.5, 0.0]  # scene y ≈ 1.25
TW_NORTH_OFFSET = [0.0, 1.5, 0.0]   # scene y ≈ 4.25

RIGHT = 1
LEFT = -1


class ExternalSourceAnalytics(FunctionalTest):
  def __init__(self, testName, request, recordXMLAttribute, repo_root):
    super().__init__(testName, request, recordXMLAttribute)
    self.repoRoot = repo_root
    self.exitCode = 1
    self.sceneUID = self.params['scene_id']

    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    assert self.rest.authenticate(self.params['user'], self.params['password'])

    self.pubsub = PubSub(
      self.params['auth'], None, self.params['rootcert'],
      self.params['broker_url'], port=int(self.params['broker_port']))
    self.pubsub.connect()
    self.pubsub.loopStart()

    self.roi_uid = None
    self.tw_uid = None
    self.roi_entered = False
    self.roi_exited = False
    self.tw_right = 0
    self.tw_left = 0
    self.tw_points = None
    self.scene_objects_seen = False
    return

  def prepareGeoScene(self):
    """Enable geospatial calibration on the demo scene.

    After inter-test DB restore, the controller may compute TRS locally while
    REST briefly omits ``trs_matrix`` (same flake class as
    test_geospatial_ingest_publish). Prefer corners on the existing demo map;
    fall back to map re-upload. Readiness is confirmed by a successful
    external-source publish that appears on DATA_SCENE, not solely by REST.
    """
    map_image = f"{self.repoRoot}/tests/resources/maps/HazardZoneSceneLarge.png"
    with open(map_image, "rb") as f:
      map_bytes = f.read()

    # JSON body first (native list), then multipart with map re-upload.
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
        return scene
      if self._probeExternalIngest():
        log.info(
          "Geo ingest probe succeeded after attempt %s "
          "(trs_matrix may be absent from REST)", attempt)
        return scene

    scene = self.rest.getScene(self.sceneUID)
    assert self._probeExternalIngest(), (
      "Scene geo calibration failed: external wgs84 ingest produced no "
      f"scene output. REST output_lla={scene.get('output_lla')} "
      f"map_corners={bool(scene.get('map_corners_lla'))} "
      f"trs_matrix={scene.get('trs_matrix') is not None}")
    return scene

  def _probeExternalIngest(self):
    """Return True if a wgs84 external-source publish yields DATA_SCENE objects."""
    self.scene_objects_seen = False
    scene_topic = PubSub.formatTopic(
      PubSub.DATA_SCENE, scene_id=self.sceneUID, thing_type=THING_TYPE)
    self.pubsub.addCallback(scene_topic, self._onSceneData)
    topic = self.externalTopic()
    deadline = time.time() + 10.0
    while time.time() < deadline:
      payload = self.buildPayload(INSIDE_ROI_OFFSET, include_pose=True)
      self.pubsub.publish(topic, json.dumps(payload))
      time.sleep(1.0 / FRAMES_PER_SECOND)
      if self.scene_objects_seen:
        return True
    return False

  def _onSceneData(self, _client, _userdata, message):
    data = json.loads(message.payload.decode("utf-8"))
    if data.get('objects'):
      self.scene_objects_seen = True
    return

  def externalTopic(self):
    return PubSub.formatTopic(
      PubSub.DATA_EXTERNAL, scene_id=AGENT_SOURCE_ID, thing_type=THING_TYPE)

  def buildPayload(self, translation, include_pose=True):
    payload = {
      "timestamp": get_iso_time(),
      "source_id": AGENT_SOURCE_ID,
      "objects": [{
        "id": OBJECT_ID,
        "category": THING_TYPE,
        "translation": list(translation),
        "size": [0.5, 0.5, 1.8],
      }],
    }
    if include_pose:
      payload["pose"] = {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      }
    return payload

  def publishSequence(self, translations, frames_each=5, include_pose_first=True):
    topic = self.externalTopic()
    first = True
    for translation in translations:
      for _ in range(frames_each):
        payload = self.buildPayload(
          translation, include_pose=(include_pose_first and first))
        first = False
        self.pubsub.publish(topic, json.dumps(payload))
        time.sleep(1.0 / FRAMES_PER_SECOND)
    return

  def onRegionEvent(self, _client, _userdata, message):
    event = json.loads(message.payload.decode("utf-8"))
    check_event_contains_data(event, "region")
    for entered in event.get("entered", []):
      if entered.get("id") == OBJECT_ID:
        self.roi_entered = True
        log.info("External object %s entered ROI", OBJECT_ID)
    for exited in event.get("exited", []):
      obj = exited.get("object") or exited
      if obj.get("id") == OBJECT_ID:
        self.roi_exited = True
        log.info("External object %s exited ROI", OBJECT_ID)
    return

  def onTripwireEvent(self, _client, _userdata, message):
    event = json.loads(message.payload.decode("utf-8"))
    check_event_contains_data(event, "tripwire")
    objects = event.get("objects") or []
    if not objects or self.tw_points is None:
      return
    curr = objects[0].get("translation")
    if not curr:
      return
    direction = self._sideOfLine(self.tw_points[0], self.tw_points[1], curr)
    if direction == RIGHT:
      self.tw_right = RIGHT
    elif direction == LEFT:
      self.tw_left = LEFT
    log.info("Tripwire event direction=%s translation=%s", direction, curr)
    return

  @staticmethod
  def _sideOfLine(a, b, point):
    cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
    if cross > 0:
      return RIGHT
    if cross < 0:
      return LEFT
    return 0

  def setupRoi(self):
    res = self.rest.createRegion({
      "scene": self.sceneUID,
      "name": ROI_NAME,
      "points": ROI_POINTS,
    })
    assert res.statusCode == HTTPStatus.CREATED, (res.statusCode, res.errors)
    self.roi_uid = res["uid"]
    topic = PubSub.formatTopic(
      PubSub.EVENT, event_type="count", scene_id=self.sceneUID,
      region_id=self.roi_uid, region_type="region")
    self.pubsub.addCallback(topic, self.onRegionEvent)
    time.sleep(CONTROLLER_SETTLE_S)
    return

  def setupTripwire(self):
    res = self.rest.createTripwire({
      "scene": self.sceneUID,
      "name": TW_NAME,
      "points": TW_POINTS,
    })
    assert res.statusCode in (HTTPStatus.OK, HTTPStatus.CREATED), (
      res.statusCode, res.errors)
    self.tw_uid = res["uid"]
    self.tw_points = res["points"]
    topic = PubSub.formatTopic(
      PubSub.EVENT, event_type="objects", scene_id=self.sceneUID,
      region_id=self.tw_uid, region_type="tripwire")
    self.pubsub.addCallback(topic, self.onTripwireEvent)
    time.sleep(CONTROLLER_SETTLE_S)
    return

  def verifyRoiInteraction(self):
    self.roi_entered = False
    self.roi_exited = False
    # Enter ROI at the geopose origin, then leave south of the rectangle.
    self.publishSequence([INSIDE_ROI_OFFSET], frames_each=15)
    deadline = time.time() + MAX_WAIT_TIMEOUT_S
    while time.time() < deadline and not self.roi_entered:
      time.sleep(0.1)
    assert self.roi_entered, (
      f"Expected ROI enter event for external object id={OBJECT_ID}")

    self.publishSequence([OUTSIDE_ROI_OFFSET], frames_each=15, include_pose_first=False)
    deadline = time.time() + MAX_WAIT_TIMEOUT_S
    while time.time() < deadline and not self.roi_exited:
      time.sleep(0.1)
    assert self.roi_exited, (
      f"Expected ROI exit event for external object id={OBJECT_ID}")
    log.info("PASS: external-source ROI enter/exit")
    return

  def verifyTripwireInteraction(self):
    self.tw_right = 0
    self.tw_left = 0
    # Move south → north across the horizontal tripwire at ~10 Hz.
    path = [
      TW_SOUTH_OFFSET,
      [0.0, -0.5, 0.0],
      [0.0, 0.0, 0.0],
      [0.0, 0.5, 0.0],
      TW_NORTH_OFFSET,
    ]
    self.publishSequence(path, frames_each=4, include_pose_first=False)
    deadline = time.time() + MAX_WAIT_TIMEOUT_S
    while time.time() < deadline and not (self.tw_right or self.tw_left):
      time.sleep(0.1)
    assert self.tw_right or self.tw_left, (
      f"Expected tripwire crossing event for external object id={OBJECT_ID}")
    log.info(
      "PASS: external-source tripwire interaction right=%s left=%s",
      self.tw_right, self.tw_left)
    return

  def cleanup(self):
    if self.roi_uid:
      self.rest.deleteRegion(self.roi_uid)
    if self.tw_uid:
      self.rest.deleteTripwire(self.tw_uid)
    try:
      self.pubsub.loopStop()
    except Exception:
      pass
    return

  def verifyFunction(self):
    if self.testName and self.recordXMLAttribute:
      self.recordXMLAttribute("name", self.testName)
    try:
      self.prepareGeoScene()
      self.setupRoi()
      self.verifyRoiInteraction()
      self.setupTripwire()
      self.verifyTripwireInteraction()
      self.exitCode = 0
    finally:
      self.cleanup()
      self.recordTestResult()
    return


def test_external_source_analytics(
    scenescape_env, demo_scene, request, record_xml_attribute, repo_root):
  test = ExternalSourceAnalytics(
    TEST_NAME, request, record_xml_attribute, repo_root)
  test.verifyFunction()
  assert test.exitCode == 0
  return


def main():
  return test_external_source_analytics(None, None)


if __name__ == '__main__':
  os._exit(main() or 0)
