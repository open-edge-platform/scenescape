#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time
import pytest
import requests

from tests.functional import FunctionalTest
from scene_common.rest_client import RESTClient
import tests.common_test_utils as common
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK_AUTOCALIBRATION

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK_AUTOCALIBRATION,
  auth=AUTH_CONTROLLER,
)

pytestmark = pytest.mark.preserve_db

POLL_INTERVAL_S = 5
POLL_TIMEOUT_S = 300
REST_RETRY_COUNT = 3
REST_RETRY_INTERVAL_S = 2
REGISTRATION_RETRY_INTERVAL_S = 90
BASE_URL = "https://autocalibration.scenescape.intel.com:8443"

MAP_APRILTAG_COUNT = 7  # number of apriltags present in Queuing scene


class ApriltagRegistration(FunctionalTest):
  """Verify that re-registration creates/updates calibration markers and
  sets map_processed after an apriltag update"""

  def __init__(self, testName, request, recordXMLAttribute):
    super().__init__(testName, request, recordXMLAttribute)
    self.scene_id = self.params['scene_id']
    self.original_apriltag_size = None
    self.autocalib_base = f"{self.params['weburl']}/api/v1/autocalibration"

    self.rootcert = self.params['rootcert']
    self.rest = RESTClient(self.params['resturl'], rootcert=self.params['rootcert'])
    res = self.rest.authenticate(self.params['user'], self.params['password'])
    assert res, res.errors

    r = requests.get(f"{self.autocalib_base}/status", verify=self.rootcert, timeout=10)
    assert r.ok, f"Autocalibration status check failed: {r.status_code} {r.text}"
    status = r.json()
    assert status.get('status') == 'running', \
      f"Autocalibration service not ready: {status}"

  def _get_scene(self):
    response = self.rest.getScene(self.scene_id)
    assert response, (response.statusCode, response.errors)
    return response

  def _update_scene_with_retries(self, update_payload):
    """Update scene with a small retry budget for transient disconnects."""

    last_error = None
    for attempt in range(REST_RETRY_COUNT):
      try:
        response = self.rest.updateScene(self.scene_id, update_payload)
        assert response, (response.statusCode, response.errors)
        return response
      except Exception as err:
        last_error = err
        if attempt < REST_RETRY_COUNT - 1:
          time.sleep(REST_RETRY_INTERVAL_S)
    raise AssertionError(f"Failed to update scene after retries: {last_error}")

  def _force_scene_unregistered(self):
    """Change apriltag_size to trigger map_processed = None"""

    scene = self._get_scene()
    current_size = scene.get('apriltag_size')
    assert current_size is not None, "Scene missing apriltag_size"
    if self.original_apriltag_size is None:
      self.original_apriltag_size = current_size
    new_size = round(current_size + 0.001, 6)
    self._update_scene_with_retries({'apriltag_size': new_size})

    # DB/UI propagation is asynchronous; poll until map_processed is cleared.
    deadline = time.time() + 30
    while time.time() < deadline:
      if self._get_scene().get('map_processed') is None:
        return
      time.sleep(POLL_INTERVAL_S)
    raise AssertionError("map_processed was not cleared after apriltag_size update")

  def _trigger_registration(self):
    """Explicitly POST to the autocalibration service to start scene registration"""

    url = f"{self.autocalib_base}/scenes/{self.scene_id}/registration"
    last_error = None
    for attempt in range(REST_RETRY_COUNT):
      try:
        r = requests.post(url, json={}, verify=self.rootcert, timeout=10)
        assert r.status_code in (200, 202), \
          f"POST registration returned {r.status_code}: {r.text}"
        return
      except Exception as err:
        last_error = err
        if attempt < REST_RETRY_COUNT - 1:
          time.sleep(REST_RETRY_INTERVAL_S)
    raise AssertionError(f"Failed to trigger registration: {last_error}")

  def _poll_for_registration(self):
    """Poll until map_processed is not null."""

    start = time.time()
    last_retrigger = start
    while time.time() - start < POLL_TIMEOUT_S:
      try:
        if self._get_scene().get('map_processed') is not None:
          return
      except Exception:
        pass

      if time.time() - last_retrigger >= REGISTRATION_RETRY_INTERVAL_S:
        self._trigger_registration()
        last_retrigger = time.time()

      time.sleep(POLL_INTERVAL_S)
    raise AssertionError(f"Registration did not complete within {POLL_TIMEOUT_S}s")

  def _clear_calibration_markers(self):
    """Delete all calibration markers for the test scene"""

    response = self.rest.getCalibrationMarkers({'scene': self.scene_id})
    assert response, (response.statusCode, response.errors)
    assert 'results' in response, f"Invalid calibration marker response: {response}"
    for marker in response['results']:
      r = self.rest.deleteCalibrationMarker(marker['marker_id'])
      assert r, (r.statusCode, r.errors)
      assert self.rest.getCalibrationMarker(marker['marker_id']).statusCode == 404, \
        f"Failed to delete marker {marker['marker_id']}"

  def _restore_scene(self):
    """Restore original apriltag_size after the test"""
    if self.original_apriltag_size is not None:
      try:
        self._update_scene_with_retries({'apriltag_size': self.original_apriltag_size})
      except Exception as err:
        # Cleanup should not hide the primary test failure.
        print(f"WARNING: scene restore failed: {err}")

  def runApriltagRegistrationUpdate(self):
    """when apriltag parameters are updated, registration creates/updates
    markers and sets map_processed"""
    try:
      self._clear_calibration_markers()
      self._force_scene_unregistered()
      self._trigger_registration()
      self._poll_for_registration()

      # Calibration markers must exist and carry the expected fields
      markers_response = self.rest.getCalibrationMarkers({'scene': self.scene_id})
      assert markers_response, (markers_response.statusCode, markers_response.errors)
      markers = markers_response.get('results', [])
      assert len(markers) == MAP_APRILTAG_COUNT, \
        f"Expected {MAP_APRILTAG_COUNT} calibration markers, got {len(markers)}"
      for marker in markers:
        assert 'apriltag_id' in marker, \
          f"Marker missing apriltag_id: {marker}"
        assert marker.get('dims') is not None, \
          f"Marker has null dims: {marker}"

      # map_processed must be updated in the DB
      updated_scene = self._get_scene()
      assert updated_scene.get('map_processed') is not None, \
        "map_processed was not set after registration"

      self.exitCode = 0
    finally:
      self._restore_scene()

  def runApriltagRegistrationDelete(self):
    """when DB has more markers than the scan finds, all markers are deleted"""
    try:
      # Ensure the DB has exactly MAP_APRILTAG_COUNT real markers by running
      # a fresh registration, then add 1 extra so DB count exceeds scan count.
      self._clear_calibration_markers()
      self._force_scene_unregistered()
      self._trigger_registration()
      self._poll_for_registration()

      real_markers = self.rest.getCalibrationMarkers({'scene': self.scene_id})
      assert real_markers and len(real_markers.get('results', [])) == MAP_APRILTAG_COUNT, \
        f"Expected {MAP_APRILTAG_COUNT} markers after initial registration, got {real_markers}"

      extra_marker = {
        'marker_id': f"{self.scene_id}_999",
        'apriltag_id': "999",
        'dims': [0.0, 0.0, 0.0],
        'scene': self.scene_id,
      }
      response = self.rest.createCalibrationMarker(extra_marker)
      assert response, (response.statusCode, response.errors)

      self._force_scene_unregistered()
      self._trigger_registration()
      self._poll_for_registration()

      # all markers must have been deleted because scan found fewer than DB had
      markers_response = self.rest.getCalibrationMarkers({'scene': self.scene_id})
      assert markers_response, (markers_response.statusCode, markers_response.errors)
      markers = markers_response.get('results', [])
      assert len(markers) == 0, \
        f"Expected 0 markers after delete branch, got {len(markers)}"

      # map_processed must still be updated even on the delete path
      updated_scene = self._get_scene()
      assert updated_scene.get('map_processed') is not None, \
        "map_processed was not set after registration"

      self.exitCode = 0
    finally:
      self._restore_scene()


def test_apriltag_registration_update(request, record_xml_attribute, params):
  TEST_NAME = "NEX-T10483"
  record_xml_attribute("name", TEST_NAME)
  test = ApriltagRegistration(
    "test_apriltag_registration_update",
    request,
    record_xml_attribute,
  )
  test.runApriltagRegistrationUpdate()
  common.record_test_result(TEST_NAME, test.exitCode)


def test_apriltag_registration_delete(request, record_xml_attribute, params):
  TEST_NAME = "NEX-T22419"
  record_xml_attribute("name", TEST_NAME)
  test = ApriltagRegistration(
    "test_apriltag_registration_delete",
    request,
    record_xml_attribute,
  )
  test.runApriltagRegistrationDelete()
  common.record_test_result(TEST_NAME, test.exitCode)
