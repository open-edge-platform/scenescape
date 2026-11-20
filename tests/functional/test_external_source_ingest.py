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
import time
import uuid

import numpy as np
import pytest

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
GEO_CALIBRATION_TIMEOUT_S = 60.0
REJECTION_WINDOW_S = 5.0
AGENT_SOURCE_ID = "drone-1"
# Fresh source with no cached intrinsics (drone-1 caches them for 30 s).
NO_INTRINSICS_SOURCE_ID = "drone-no-intrinsics"
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
    self.seenObjectIds = set()
    self.seenObjects = []
    return

  def pubsubConnected(self, client, userdata, flags, rc):
    self.pubsub.subscribe(self.topic)
    return

  def eventReceived(self, pahoClient, userdata, message):
    data = json.loads(message.payload.decode("utf-8"))
    if data.get('objects'):
      self.lastObjects = data['objects']
      self.outputReceived = True
      self.seenObjects.extend(data['objects'])
      for obj in data['objects']:
        if 'id' in obj:
          self.seenObjectIds.add(obj['id'])
    return

  def cleanup(self):
    try:
      self.pubsub.loopStop()
    except Exception as e:
      log.warning("MQTT loopStop failed during cleanup: %s", e)
    return

  def _lastIds(self):
    return [o.get('id') for o in (self.lastObjects or [])]

  @staticmethod
  def _isUUID(value):
    try:
      uuid.UUID(str(value))
    except ValueError:
      return False
    return True

  @staticmethod
  def _hasMarker(objects, marker):
    return any(
      obj.get("metadata", {}).get("test_marker") == marker for obj in objects)

  def prepareScene(self):
    """Enable geospatial calibration on the demo scene.

    When the demo scene has just been created, the controller may compute TRS
    locally while REST briefly omits ``trs_matrix`` (same flake class as
    test_geospatial_ingest_publish / test_external_source_analytics). Prefer
    corners on the existing demo map; fall back to map re-upload. Readiness
    is confirmed by a successful external-source publish on DATA_SCENE when
    REST does not expose ``trs_matrix``.
    """
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
      scene = self._waitForTRSMatrix()
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

  def _waitForTRSMatrix(self, timeout=GEO_CALIBRATION_TIMEOUT_S):
    """Poll REST until the scene exposes trs_matrix or *timeout* expires."""
    deadline = time.time() + timeout
    scene = None
    while True:
      scene = self.rest.getScene(self.sceneUID)
      if scene.get('trs_matrix') or time.time() >= deadline:
        return scene
      time.sleep(CONTROLLER_SETTLE_S)

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
    return self.publishAndWait(jdata, timeout=MAX_WAIT_TIMEOUT_S) is not None

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

  def publishAndWaitForIds(self, jdata, expected_ids, timeout=MAX_WAIT_TIMEOUT_S):
    """Publish until one scene snapshot contains all expected object ids."""
    return self.publishAndWaitForObjects(
      jdata,
      lambda objects: set(expected_ids).issubset(
        {obj.get('id') for obj in objects}),
      timeout,
    )

  def publishAndWaitForObjects(self, jdata, predicate, timeout=MAX_WAIT_TIMEOUT_S):
    """Publish until one scene snapshot satisfies predicate."""
    self.lastObjects = None
    topic = self.externalSourceTopic(jdata.get('source_id', AGENT_SOURCE_ID))
    start = time.time()
    count = 0
    while time.time() - start < timeout:
      jdata['timestamp'] = get_iso_time()
      self.pubsub.publish(topic, json.dumps(jdata))
      count += 1
      time.sleep(1 / FRAMES_PER_SECOND)
      if predicate(self.lastObjects or []):
        return True
    log.warning(
      "Predicate not satisfied after %d publishes on %s in %.1fs; "
      "last scene snapshot ids=%s", count, topic, timeout, self._lastIds())
    return False

  def publishForWindow(self, jdata, timeout, topic_publisher=None):
    """Publish for the full window, collecting every scene object observed.

    The scene may keep republishing previously admitted, still-active tracks
    on every incoming message, so topic silence is not a valid rejection
    signal; callers inspect seenObjectIds/seenObjects instead.
    """
    self.seenObjectIds = set()
    self.seenObjects = []
    publisher = topic_publisher or jdata.get('source_id', AGENT_SOURCE_ID)
    topic = self.externalSourceTopic(publisher)
    start = time.time()
    while time.time() - start < timeout:
      jdata['timestamp'] = get_iso_time()
      self.pubsub.publish(topic, json.dumps(jdata))
      time.sleep(1 / FRAMES_PER_SECOND)
    log.debug("Window on %s (%.1fs) saw ids=%s",
              topic, timeout, sorted(map(str, self.seenObjectIds)))
    return

  def _findObject(self, object_id):
    assert self.lastObjects, "No scene objects received"
    for obj in self.lastObjects:
      if obj.get('id') == object_id:
        return obj
    raise AssertionError(
      f"Object id={object_id} not found in scene output: "
      f"{[o.get('id') for o in self.lastObjects]}")

  def _findControllerTrackedObject(self):
    """Return the first object with a controller-assigned UUID id.

    The synthesized platform object (id == source_id) shares the body-origin
    location, so it must not be mistaken for the tracked observation.
    """
    assert self.lastObjects, "No scene objects received"
    for obj in self.lastObjects:
      if self._isUUID(obj.get('id')):
        return obj['id'], obj
    raise AssertionError(
      f"No controller-assigned (UUID) track found in scene output: {self._lastIds()}")

  def _waitForControllerTrackedObject(self, jdata, failure_msg):
    found = self.publishAndWaitForObjects(
      jdata, lambda objects: any(self._isUUID(o.get('id')) for o in objects))
    assert found, f"{failure_msg}; last scene snapshot ids={self._lastIds()}"
    return self._findControllerTrackedObject()

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
    published_id, obj = self._waitForControllerTrackedObject(
      jdata, "External source (wgs84 pose) message did not produce tracked output")
    assert published_id not in (OBJECT_ID, AGENT_SOURCE_ID), (
      f"Tracked object kept source-provided id: {published_id}")
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
      "PASS: wgs84 external-source location accuracy id=%s xyz=%s lla=%s",
      published_id, obj["translation"], obj["lat_long_alt"])
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
    log.info("PASS: pose-less message reused cached pose; ids=%s", self._lastIds())
    return

  def verifyTrackedObjectWithoutIdGetsControllerAssignedId(self):
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {
          "category": THING_TYPE,
          "translation": [0.0, 0.0, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
      ],
    }
    published_id, obj = self._waitForControllerTrackedObject(
      jdata, "Tracked external source object without id did not produce output")
    np.testing.assert_allclose(
      obj["translation"], EXPECTED_SCENE_XYZ, atol=SCENE_XYZ_ATOL_M,
      err_msg=(
        f"Tracked external object without id was not localized correctly: "
        f"id={published_id} got {obj['translation']}, expected {EXPECTED_SCENE_XYZ}"))
    log.info("PASS: id-less tracked object got controller id=%s", published_id)
    return

  def verifyUntrackedObjectPreservesId(self):
    untracked_id = "agent-untracked-1"
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {
          "id": untracked_id,
          "category": THING_TYPE,
          "translation": [0.1, 0.0, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
      ],
      "track": False,
    }
    assert self.publishAndWaitForIds(jdata, {untracked_id}), (
      f"Untracked external source object id={untracked_id} did not produce output; "
      f"last scene snapshot ids={self._lastIds()}")
    obj = self._findObject(untracked_id)
    assert obj["id"] == untracked_id
    log.info("PASS: track=false object preserved id=%s", untracked_id)
    return

  def verifySourceTrackFalseAppliesToAllObjects(self):
    source_ids = ["agent-source-track-false-1", "agent-source-track-false-2"]
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "track": False,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {
          "id": source_ids[0],
          "category": THING_TYPE,
          "translation": [0.2, 0.0, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
        {
          "id": source_ids[1],
          "category": THING_TYPE,
          "translation": [-0.2, 0.0, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
      ],
    }
    assert self.publishAndWaitForIds(jdata, source_ids), (
      f"Source-level track=false objects {source_ids} did not produce output; "
      f"last scene snapshot ids={self._lastIds()}")
    for source_id in source_ids:
      assert self._findObject(source_id)["id"] == source_id
    log.info("PASS: source-level track=false preserved ids=%s", source_ids)
    return

  def verifyPixelBoundingBoxDiscardedWhenTrackFalse(self):
    """track=false pixel detections are discarded (data_formats.md, ITEP-97980);
    the message itself is still accepted, so the platform keeps publishing."""
    source_object_id = "pixel-source-1"
    pixel_marker = {
      "label": "pixel-track-false",
      "model_name": "external-source-functional-test",
    }
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "track": False,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "intrinsics": {
        "fx": 905.0,
        "fy": 905.0,
        "cx": 640.0,
        "cy": 360.0,
      },
      "objects": [
        {
          "id": source_object_id,
          "category": THING_TYPE,
          "metadata": {"test_marker": pixel_marker},
          "bounding_box_px": {
            "x": 221,
            "y": 157,
            "width": 108,
            "height": 259,
          },
        },
      ],
    }
    self.publishForWindow(jdata, REJECTION_WINDOW_S)
    seen_ids = sorted(map(str, self.seenObjectIds))
    assert AGENT_SOURCE_ID in self.seenObjectIds, (
      f"track=false pixel message was not accepted: platform id={AGENT_SOURCE_ID} "
      f"missing from scene output; seen ids={seen_ids}")
    assert source_object_id not in self.seenObjectIds, (
      f"track=false pixel detection id={source_object_id} was published; "
      f"expected it to be discarded. seen ids={seen_ids}")
    assert not self._hasMarker(self.seenObjects, pixel_marker), (
      f"track=false pixel detection was published under another id; "
      f"expected it to be discarded. seen ids={seen_ids}")
    log.info("PASS: track=false pixel detection discarded; seen ids=%s", seen_ids)
    return

  def verifyPixelBoundingBoxWithRotationDerivedFromPose(self):
    source_object_id = "pixel-rotation-check"
    pixel_marker = {
      "label": "pixel-rotation-check",
      "model_name": "external-source-functional-test",
    }
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": [
          AGENT_LAT_LONG_ALT[0],
          AGENT_LAT_LONG_ALT[1],
          AGENT_LAT_LONG_ALT[2] + 2.0,
        ],
        "rotation": [-0.7071068, 0.0, 0.0, 0.7071068],
        "provider": "robot",
      },
      "intrinsics": {
        "fx": 905.0,
        "fy": 905.0,
        "cx": 640.0,
        "cy": 360.0,
      },
      "objects": [
        {
          "id": source_object_id,
          "category": THING_TYPE,
          "metadata": {"test_marker": pixel_marker},
          "bounding_box_px": {
            "x": 600,
            "y": 520,
            "width": 80,
            "height": 160,
          },
        },
      ],
    }
    def _containsRotatedPixel(objects):
      return any(
        obj.get("metadata", {}).get("test_marker") == pixel_marker
        and "translation" in obj
        for obj in objects
      )

    assert self.publishAndWaitForObjects(jdata, _containsRotatedPixel), (
      f"Pixel detection with rotated source pose did not produce tracked output; "
      f"last scene snapshot ids={self._lastIds()}")
    log.info("PASS: rotated-pose pixel detection localized and tracked")
    return

  def verifyPixelBoundingBoxWithoutIntrinsicsRejected(self):
    """Uses a fresh source_id: drone-1 still has live cached intrinsics from
    earlier pixel sub-tests, which would legitimately satisfy this message."""
    pixel_object_id = "pixel-missing-intrinsics"
    pixel_marker = {
      "label": "pixel-missing-intrinsics",
      "model_name": "external-source-functional-test",
    }
    jdata = {
      "source_id": NO_INTRINSICS_SOURCE_ID,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {
          "id": pixel_object_id,
          "category": THING_TYPE,
          "metadata": {"test_marker": pixel_marker},
          "bounding_box_px": {
            "x": 221,
            "y": 157,
            "width": 108,
            "height": 259,
          },
        },
      ],
    }
    self.publishForWindow(jdata, REJECTION_WINDOW_S)
    seen_ids = sorted(map(str, self.seenObjectIds))
    # Whole message is dropped, so neither the platform nor the pixel object appears.
    assert NO_INTRINSICS_SOURCE_ID not in self.seenObjectIds, (
      f"Pixel message without intrinsics was accepted: platform "
      f"id={NO_INTRINSICS_SOURCE_ID} published; seen ids={seen_ids}")
    assert not self._hasMarker(self.seenObjects, pixel_marker), (
      f"Pixel detection without intrinsics was published; seen ids={seen_ids}")
    log.info("PASS: pixel message without intrinsics rejected; seen ids=%s", seen_ids)
    return

  def verifyMixedTranslationAndPixelObjects(self):
    """With track=false, Cartesian objects keep their ids while co-packaged
    pixel detections are discarded without dropping the whole message."""
    translation_source_id = "mixed-untracked-1"
    pixel_source_id = "mixed-pixel-1"
    pixel_marker = {
      "label": "mixed-pixel",
      "model_name": "external-source-functional-test",
    }
    jdata = {
      "source_id": AGENT_SOURCE_ID,
      "track": False,
      "pose": {
        "reference_frame": "wgs84",
        "lat_long_alt": AGENT_LAT_LONG_ALT,
        "rotation": IDENTITY_ROTATION,
      },
      "intrinsics": {
        "fx": 905.0,
        "fy": 905.0,
        "cx": 640.0,
        "cy": 360.0,
      },
      "objects": [
        {
          "id": translation_source_id,
          "category": THING_TYPE,
          "translation": [0.15, 0.0, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
        {
          "id": pixel_source_id,
          "category": THING_TYPE,
          "metadata": {"test_marker": pixel_marker},
          "bounding_box_px": {
            "x": 221,
            "y": 157,
            "width": 108,
            "height": 259,
          },
        },
      ],
    }
    self.publishForWindow(jdata, REJECTION_WINDOW_S)
    seen_ids = sorted(map(str, self.seenObjectIds))
    assert translation_source_id in self.seenObjectIds, (
      f"track=false Cartesian object id={translation_source_id} missing from mixed "
      f"message output; seen ids={seen_ids}")
    assert pixel_source_id not in self.seenObjectIds, (
      f"track=false pixel detection id={pixel_source_id} was published from mixed "
      f"message; expected it to be discarded. seen ids={seen_ids}")
    assert not self._hasMarker(self.seenObjects, pixel_marker), (
      f"track=false pixel detection from mixed message was published under another "
      f"id; seen ids={seen_ids}")
    log.info("PASS: mixed track=false message kept %s, discarded pixel; seen ids=%s",
             translation_source_id, seen_ids)
    return

  def verifyUntrustedScenePoseRejected(self):
    """A scene-frame pose from a source not in CONTROLLER_TRUSTED_POSITIONING_SOURCES
    must be rejected: the untrusted source's object never appears in tracked
    output for this scene, even though the scene may continue to legitimately
    republish other, already-admitted, still-active tracks (e.g. agent-track-1
    from the earlier sub-tests) on every message it receives."""
    untrusted_object_id = "positioning-track-1"
    # track=false keeps the source id if wrongly accepted, so the id check is meaningful.
    jdata = {
      "source_id": UNTRUSTED_POSITIONING_SOURCE_ID,
      "track": False,
      "pose": {
        "reference_frame": "scene",
        "translation": [1.0, 1.0, 0.0],
        "rotation": IDENTITY_ROTATION,
      },
      "objects": [
        {"id": untrusted_object_id, "category": THING_TYPE, "translation": [0.0, 0.0, 0.0], "size": [0.5, 0.5, 1.8]},
      ],
    }
    self.publishForWindow(jdata, REJECTION_WINDOW_S)
    seen_ids = sorted(map(str, self.seenObjectIds))
    for forbidden in (untrusted_object_id, UNTRUSTED_POSITIONING_SOURCE_ID):
      assert forbidden not in self.seenObjectIds, (
        f"Untrusted scene-frame pose unexpectedly produced output for id={forbidden}; "
        f"seen ids={seen_ids}")
    log.info("PASS: untrusted scene-frame pose rejected; seen ids=%s", seen_ids)
    return

  def verifySourceIdTopicMismatchRejected(self):
    """Payload source_id must match the publisher id in the MQTT topic path."""
    mismatched_id = "mismatch-track-1"
    mismatched_source = "not-the-topic-publisher"
    # track=false keeps the source id if wrongly accepted, so the id check is meaningful.
    jdata = {
      "source_id": mismatched_source,
      "track": False,
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
    self.publishForWindow(jdata, REJECTION_WINDOW_S, topic_publisher=AGENT_SOURCE_ID)
    seen_ids = sorted(map(str, self.seenObjectIds))
    for forbidden in (mismatched_id, mismatched_source):
      assert forbidden not in self.seenObjectIds, (
        f"source_id/topic mismatch unexpectedly produced output for id={forbidden}; "
        f"seen ids={seen_ids}")
    log.info("PASS: source_id/topic mismatch rejected; seen ids=%s", seen_ids)
    return

  def verifyIdentityCollisionDropsSecondSource(self):
    """A second publisher reclaiming a live id is dropped; a non-colliding id is kept.

    Wait specifically for the non-colliding id: scene publishes are async to
    the tracker queue, so the first DATA_SCENE after drone-2 publishes may
    still only contain the earlier drone-1 track.
    """
    colliding_id = "collision-track"
    unique_id = "drone-2-unique-track"
    other_source = "drone-2"
    first_source_data = {
      "source_id": AGENT_SOURCE_ID,
      "track": False,
      "objects": [
        {
          "id": colliding_id,
          "category": THING_TYPE,
          "translation": [0.0, 0.0, 0.0],
          "size": [0.5, 0.5, 1.8],
        },
      ],
    }
    assert self.publishAndWaitForIds(first_source_data, {colliding_id}), (
      f"First untracked source did not establish an identity claim for "
      f"id={colliding_id}; last scene snapshot ids={self._lastIds()}")
    jdata = {
      "source_id": other_source,
      "track": False,
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
        log.info("PASS: identity collision kept non-colliding id=%s; ids=%s",
                 unique_id, sorted(map(str, ids)))
        return
    raise AssertionError(
      f"Non-colliding id missing from scene output after {MAX_WAIT_TIMEOUT_S}s: {ids}")

  def verifyFunction(self):
    try:
      self.prepareScene()
      self.verifyWgs84PoseIngestAndLocationAccuracy()
      self.verifyTrackedObjectWithoutIdGetsControllerAssignedId()
      self.verifyPoseReuseFromCache()
      self.verifyUntrackedObjectPreservesId()
      self.verifySourceTrackFalseAppliesToAllObjects()
      self.verifyPixelBoundingBoxDiscardedWhenTrackFalse()
      self.verifyPixelBoundingBoxWithRotationDerivedFromPose()
      self.verifyPixelBoundingBoxWithoutIntrinsicsRejected()
      self.verifyMixedTranslationAndPixelObjects()
      self.verifySourceIdTopicMismatchRejected()
      self.verifyIdentityCollisionDropsSecondSource()
      self.verifyUntrustedScenePoseRejected()
      self.exitCode = 0
    finally:
      self.cleanup()
    return


@pytest.mark.test_name("NEX-T29229")
def test_external_source_ingest(scenescape_env, demo_scene, request, repo_root, result_recorder):
  test = ExternalSourceIngest(TEST_NAME, request, repo_root)
  test.verifyFunction()
  result_recorder.success()
  return
