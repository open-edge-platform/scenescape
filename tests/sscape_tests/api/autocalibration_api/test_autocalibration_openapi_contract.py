# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""OpenAPI contract checks for the autocalibration REST API.

``test_autocalibration_matches_openapi_contract`` calls CameraCalibrationApi
with a mocked ready context and deterministic inputs, then runs response
schema, status code, content type, and response header conformance.
Generated cases are not used: an uninitialized context returns the documented
500 before validation or success handlers run, and unconstrained IDs hit
status codes some operations do not document. ``test_flask_routes_match_spec_operations``
compares every ``/v1`` route with ``autocalibration-api.yaml``. Neither test
rewrites the spec.
"""

import base64
from dataclasses import dataclass
from pathlib import Path

import pytest
from flask import has_request_context, request

from auto_camera_calibration_api import CameraCalibrationApi
from tests.sscape_tests.api.common import (
  CONTRACT_CHECKS,
  HTTP_METHODS,
  assert_operations_match,
  assert_server_prefix_documented,
  flask_operations,
  load_openapi_document,
  load_wsgi_schema,
  skip_if_spec_missing,
  spec_operations,
)

_SPEC_RELATIVE = Path(
  "docs/user-guide/microservices/auto-calibration/_assets/autocalibration-api.yaml")
_SPEC_PATH = skip_if_spec_missing(_SPEC_RELATIVE, start=Path(__file__))

# Matches servers[].url, which already ends in /v1. Spec paths are relative to that.
API_PREFIX = "/v1"

_SUCCESS_SCENE = "302cf49a-97ec-402d-a324-c5077b280b7b"
_REGISTERING_SCENE = "11111111-1111-4111-8111-111111111111"
_BUSY_SCENE = "22222222-2222-4222-8222-222222222222"
_ERROR_SCENE = "33333333-3333-4333-8333-333333333333"
_MISSING_SCENE = "44444444-4444-4444-8444-444444444444"
_NO_STRATEGY_SCENE = "55555555-5555-4555-8555-555555555555"
_MANUAL_SCENE = "66666666-6666-4666-8666-666666666666"
_CAMERA_SCENE = "77777777-7777-4777-8777-777777777777"

_CAM_SUCCESS = "atag-qcam1"
_CAM_STORED = "atag-qcam-stored"
_CAM_BUSY = "atag-qcam-busy"
_CAM_NEW = "atag-qcam-new"
_CAM_MISSING = "atag-qcam-missing"
_CAM_FAIL = "atag-qcam-fail"
_CAM_NO_INTRINSICS = "atag-qcam-no-k"

_SENSOR_SUCCESS = "lidar-1"
_SENSOR_START = "lidar-start"
_SENSOR_NEW = "lidar-new"
_SENSOR_FAIL = "lidar-fail"
_SENSOR_BROKEN = "lidar-broken"

_APRILTAG = "AprilTag"
_MARKERLESS = "Markerless"
_FAILING = "Failing"
_MANUAL = "Manual"
_MISSING_STRATEGY = "MissingStrategy"

_INTRINSICS = [
  [1000.0, 0.0, 640.0],
  [0.0, 1000.0, 360.0],
  [0.0, 0.0, 1.0],
]
_TRANSFORM = [
  [1.0, 0.0, 0.0, 0.15],
  [0.0, 1.0, 0.0, -0.10],
  [0.0, 0.0, 1.0, 0.05],
  [0.0, 0.0, 0.0, 1.0],
]
_IMAGE = base64.b64encode(b"\xff\xd8\xff\xd9").decode("ascii")
_NOT_IMAGE = base64.b64encode(b"not-an-image").decode("ascii")
_CLOUD = base64.b64encode(b"# .PCD v0.7\n").decode("ascii")
_BAD_CLOUD = base64.b64encode(b"not-a-cloud").decode("ascii")
_NO_BODY = object()


class _Scene:
  """Scene stand-in with the attributes the REST handlers read."""

  def __init__(self, scene_id, calibration, name="Demo Scene"):
    self.id = scene_id
    self.camera_calibration = calibration
    self.name = name


class _Strategy:
  """Calibration strategy whose map and process results are fixed."""

  def __init__(self, map_updated, process_result):
    self._map_updated = map_updated
    self._process_result = process_result
    self.socketio = None
    self.socket_scene_clients = None

  def is_map_updated(self, scene):
    """Return the configured map-update flag."""
    return self._map_updated

  def process_scene_for_calibration(self, scene):
    """Return the configured registration result."""
    return self._process_result

  def reset_scene(self, scene):
    """Accept a reset without touching storage."""
    return None


class _ViewLock:
  """Busy only for the request IDs that should take the busy branch."""

  def __init__(self, busy_ids):
    self._busy_ids = busy_ids

  def locked(self):
    """Return whether the current path ID is configured as busy."""
    if not has_request_context():
      return False
    view_args = request.view_args or {}
    ident = view_args.get("sceneId") or view_args.get("cameraId")
    return ident in self._busy_ids


class _Results(dict):
  """Result store that fails closed for one sensor ID."""

  def get(self, key, default=None):
    """Return a stored result, or fail for the broken sensor."""
    if key == _SENSOR_BROKEN:
      raise RuntimeError("result store unavailable")
    return super().get(key, default)


class _DataInterface:
  """Lookup tables for scenes, cameras, and stored intrinsics."""

  def __init__(self, scenes, cameras):
    self._scenes = scenes
    self._cameras = cameras

  def scene_with_id(self, scene_id):
    """Return the scene, or None when it was not registered."""
    return self._scenes.get(scene_id)

  def scene_camera_with_id(self, camera_id):
    """Return the camera scene, or None when the camera is unknown."""
    return self._cameras.get(camera_id)

  def get_camera_intrinsics(self, camera_id):
    """Return stored intrinsics, except for the camera that has none."""
    if camera_id == _CAM_NO_INTRINSICS:
      return None
    return _INTRINSICS


class _ReadyContext:
  """Ready calibration context with deterministic scene and camera behavior."""

  def __init__(self):
    scenes = {
      _SUCCESS_SCENE: _Scene(_SUCCESS_SCENE, _APRILTAG),
      _ERROR_SCENE: _Scene(_ERROR_SCENE, _FAILING),
      _REGISTERING_SCENE: _Scene(_REGISTERING_SCENE, _MARKERLESS),
      _BUSY_SCENE: _Scene(_BUSY_SCENE, _MARKERLESS),
      _NO_STRATEGY_SCENE: _Scene(_NO_STRATEGY_SCENE, _MISSING_STRATEGY),
      _MANUAL_SCENE: _Scene(_MANUAL_SCENE, _MANUAL),
    }
    camera_scene = _Scene(_CAMERA_SCENE, _APRILTAG)
    cameras = {
      camera_id: camera_scene
      for camera_id in (
        _CAM_SUCCESS, _CAM_STORED, _CAM_BUSY, _CAM_NEW, _CAM_FAIL, _CAM_NO_INTRINSICS)
    }
    self.calibration_data_interface = _DataInterface(scenes, cameras)
    self.scene_strategies = {
      _APRILTAG: _Strategy(False, {"status": "success"}),
      _MARKERLESS: _Strategy(True, {"status": "success"}),
      _FAILING: _Strategy(False, {"status": "error", "message": "registration failed"}),
    }
    self.register_thread_lock = _ViewLock({_BUSY_SCENE})
    self.calibration_thread_lock = _ViewLock({_CAM_BUSY})
    self.calibration_results = _Results({
      _CAM_SUCCESS: {
        "status": "success",
        "message": "Calibration completed",
        "quaternion": [0.707, 0.0, 0.707, 0.0],
        "translation": [1.2, 0.5, 2.3],
        "calibration_points_3d": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        "calibration_points_2d": [[100.0, 200.0], [150.0, 250.0]],
        "spread_ratio": 0.25,
      },
      _SENSOR_SUCCESS: {
        "status": "success",
        "message": "Localization completed",
        "scene_name": "Demo Scene",
        "transform": _TRANSFORM,
        "fitness": 0.98,
        "inlier_rmse": 0.012,
      },
    })
    self.socket_clients = {}
    self.socket_scene_clients = {}

  def scene_update_thread_wrapper(self, scene, map_update=False):
    """Accept an update trigger without starting a thread."""
    return None

  def calibrate_camera_thread_wrapper(self, scene, camera_id, intrinsics, frame):
    """Accept calibration, or fail for the camera that must return 500."""
    if camera_id == _CAM_FAIL:
      raise RuntimeError("calibration failed")
    return None

  def calibrate_perceptual_sensor_thread_wrapper(self, scene, sensor_id, frame):
    """Accept localization, or fail for the sensor that must return 500."""
    if sensor_id == _SENSOR_FAIL:
      raise RuntimeError("localization failed")
    return None


_api = CameraCalibrationApi(calibrationContext=_ReadyContext())
_unready_api = CameraCalibrationApi(calibrationContext=None)
schema = load_wsgi_schema(_SPEC_PATH, _api.app)


@dataclass(frozen=True)
class _ContractInput:
  """One documented call: a success payload or an error outcome."""

  case_id: str
  operation_id: str
  outcome: str
  path_parameters: dict | None = None
  body: object = _NO_BODY
  use_unready_app: bool = False


def _input(case_id, operation_id, outcome, path_parameters=None, body=_NO_BODY,
           use_unready_app=False):
  """Build one deterministic contract input."""
  return _ContractInput(
    case_id, operation_id, outcome, path_parameters, body, use_unready_app)


_LOCALIZE_BODY = {
  "sceneId": _SUCCESS_SCENE,
  "pointcloud": _CLOUD,
  "format": "pcd",
  "modality": "lidar",
  "initialTransform": _TRANSFORM,
}
_CONTRACT_INPUTS = [
  _input("status-running", "getServiceStatus", "success"),
  _input("status-error", "getServiceStatus", "error", use_unready_app=True),
  _input("register-success", "registerScene", "success", {"sceneId": _SUCCESS_SCENE}),
  _input("register-process-error", "registerScene", "success", {"sceneId": _ERROR_SCENE}),
  _input("register-started", "registerScene", "success", {"sceneId": _REGISTERING_SCENE}),
  _input("register-busy", "registerScene", "success", {"sceneId": _BUSY_SCENE}),
  _input("register-invalid-id", "registerScene", "error", {"sceneId": "bad id"}),
  _input("register-manual", "registerScene", "error", {"sceneId": _MANUAL_SCENE}),
  _input("register-missing", "registerScene", "error", {"sceneId": _MISSING_SCENE}),
  _input("register-no-strategy", "registerScene", "error", {"sceneId": _NO_STRATEGY_SCENE}),
  _input("registration-status-success", "getSceneRegistrationStatus", "success",
         {"sceneId": _SUCCESS_SCENE}),
  _input("registration-status-registering", "getSceneRegistrationStatus", "success",
         {"sceneId": _REGISTERING_SCENE}),
  _input("registration-status-busy", "getSceneRegistrationStatus", "success",
         {"sceneId": _BUSY_SCENE}),
  _input("registration-status-missing", "getSceneRegistrationStatus", "error",
         {"sceneId": _MISSING_SCENE}),
  _input("registration-status-no-strategy", "getSceneRegistrationStatus", "error",
         {"sceneId": _NO_STRATEGY_SCENE}),
  _input("update-accepted", "updateScene", "success", {"sceneId": _REGISTERING_SCENE}),
  _input("update-missing", "updateScene", "error", {"sceneId": _MISSING_SCENE}),
  _input("update-no-strategy", "updateScene", "error", {"sceneId": _NO_STRATEGY_SCENE}),
  _input("calibrate-started", "calibrateCamera", "success", {"cameraId": _CAM_SUCCESS},
         {"image": _IMAGE, "intrinsics": _INTRINSICS}),
  _input("calibrate-stored-intrinsics", "calibrateCamera", "success",
         {"cameraId": _CAM_STORED}, {"image": _IMAGE}),
  _input("calibrate-bad-image", "calibrateCamera", "error", {"cameraId": _CAM_SUCCESS},
         {"image": _NOT_IMAGE}),
  _input("calibrate-no-intrinsics", "calibrateCamera", "error",
         {"cameraId": _CAM_NO_INTRINSICS}, {"image": _IMAGE}),
  _input("calibrate-missing", "calibrateCamera", "error", {"cameraId": _CAM_MISSING},
         {"image": _IMAGE}),
  _input("calibrate-failed", "calibrateCamera", "error", {"cameraId": _CAM_FAIL},
         {"image": _IMAGE, "intrinsics": _INTRINSICS}),
  _input("camera-status-success", "getCameraCalibrationStatus", "success",
         {"cameraId": _CAM_SUCCESS}),
  _input("camera-status-busy", "getCameraCalibrationStatus", "success",
         {"cameraId": _CAM_BUSY}),
  _input("camera-status-not-started", "getCameraCalibrationStatus", "success",
         {"cameraId": _CAM_NEW}),
  _input("camera-status-missing", "getCameraCalibrationStatus", "error",
         {"cameraId": _CAM_MISSING}),
  _input("localize-started", "localizePerceptualSensor", "success",
         {"sensorId": _SENSOR_START}, _LOCALIZE_BODY),
  _input("localize-bad-cloud", "localizePerceptualSensor", "error",
         {"sensorId": _SENSOR_START},
         {"sceneId": _SUCCESS_SCENE, "pointcloud": _BAD_CLOUD}),
  _input("localize-missing-scene", "localizePerceptualSensor", "error",
         {"sensorId": _SENSOR_START},
         {"sceneId": _MISSING_SCENE, "pointcloud": _CLOUD}),
  _input("localize-failed", "localizePerceptualSensor", "error",
         {"sensorId": _SENSOR_FAIL}, _LOCALIZE_BODY),
  _input("localization-status-success", "getPerceptualSensorLocalizationStatus", "success",
         {"sensorId": _SENSOR_SUCCESS}),
  _input("localization-status-not-started", "getPerceptualSensorLocalizationStatus", "success",
         {"sensorId": _SENSOR_NEW}),
  _input("localization-status-store-failed", "getPerceptualSensorLocalizationStatus", "error",
         {"sensorId": _SENSOR_BROKEN}),
]


def _documented_operation_ids():
  """Return every operationId in the committed autocalibration spec."""
  operation_ids = set()
  for path_item in (load_openapi_document(_SPEC_PATH).get("paths") or {}).values():
    if not isinstance(path_item, dict):
      continue
    for method, operation in path_item.items():
      if method in HTTP_METHODS and isinstance(operation, dict) and operation.get("operationId"):
        operation_ids.add(operation["operationId"])
  return operation_ids


@pytest.mark.parametrize("contract_input", _CONTRACT_INPUTS, ids=lambda item: item.case_id)
def test_autocalibration_matches_openapi_contract(contract_input):
  """Success and error inputs must satisfy the four OpenAPI response checks."""
  operation = schema.find_operation_by_id(contract_input.operation_id)
  case_kwargs = {}
  if contract_input.path_parameters:
    case_kwargs["path_parameters"] = contract_input.path_parameters
  if contract_input.body is not _NO_BODY:
    case_kwargs["body"] = contract_input.body
  case = schema.make_case(operation=operation, **case_kwargs)
  call_kwargs = {}
  if contract_input.use_unready_app:
    call_kwargs["app"] = _unready_api.app
  case.call_and_validate(checks=CONTRACT_CHECKS, **call_kwargs)


def test_contract_inputs_cover_success_and_error():
  """Every documented operation needs a success payload and an error outcome."""
  documented = _documented_operation_ids()
  covered = {item.operation_id for item in _CONTRACT_INPUTS}
  assert covered == documented
  for operation_id in sorted(documented):
    outcomes = {item.outcome for item in _CONTRACT_INPUTS if item.operation_id == operation_id}
    assert outcomes == {"success", "error"}, operation_id


def test_flask_routes_match_spec_operations():
  """Flask /v1 routes must equal the operations documented in autocalibration-api.yaml."""
  assert_server_prefix_documented(_SPEC_PATH, API_PREFIX)
  routed, outside_prefix = flask_operations(_api.app, API_PREFIX)
  documented = spec_operations(_SPEC_PATH)
  assert_operations_match(
    routed,
    documented,
    empty_message="no /v1 routes registered on CameraCalibrationApi",
    outside_prefix=outside_prefix,
    api_prefix=API_PREFIX,
  )
