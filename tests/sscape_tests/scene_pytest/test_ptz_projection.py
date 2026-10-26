#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""PTZ per-frame projection, visibility and the ingress gate at Controller scene level."""

import copy
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import orjson
import pytest

from controller.ptz import provider
from controller.ptz.config import MODE_ENFORCE, MODE_SHADOW, PTZSettings
from controller.ptz.ingress import PTZIngress
from controller.ptz.projection import ProjectedCamera
from controller.ptz.registry import PTZPoseRegistry
from controller.ptz.shadow import ShadowRecorder, candidate_residuals
from scene_common.camera import Camera
from scene_common.detections_builder import computeCameraBounds
from scene_common.geometry import Point
from scene_common.mqtt import PubSub
from scene_common.positioning_config import ConsumerPositioningConfig
from scene_common.positioning_dwell import NS_PER_S, PoseSnapshot, parse_timestamp_ns
from scene_common.schema import SchemaValidation
from tests.sscape_tests.scene_pytest.config import jdata, when
from tests.utils.ptz_pose import iso, pose_context, rotated_matrix, status_payload

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "controller" / "src" / "schema" \
  / "metadata.schema.json"

SOURCE = "camera1"
RESOLVER = "positioning-a"
SCENE_UID = "scene-1"
FRAME = f"scene:{SCENE_UID}"
VERSION = "ptz-v1"
T0 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)
POSE_TOPIC = PubSub.formatTopic(PubSub.POSITIONING_POSE, source_id=SOURCE)
STATUS_TOPIC = PubSub.formatTopic(PubSub.POSITIONING_STATUS, resolver_id=RESOLVER)
CONSUMER = ConsumerPositioningConfig(
  max_pose_age_s=0.5, max_clock_offset_s=0.05, max_detection_pipeline_latency_s=1.0,
  max_detection_timestamp_uncertainty_s=0.05)
# Double-precision round-off tolerance for the home-pose-as-PoseContext check; not a hardware budget
EPSILON_SYNTHETIC_PX = 1e-6
LAST_POSE_OFFSET_S = 2.9
OBSERVATION_OFFSET_S = 2.5
LOCAL_NOW_OFFSET_S = 2.95


def _at(offset_s):
  return T0 + timedelta(seconds=offset_s)


def _ns(offset_s):
  return parse_timestamp_ns(iso(_at(offset_s)))


def _ptz_camera(camera):
  camera.ptz_calibration = {"calibration_version": VERSION}
  return camera


def _euler_camera():
  info = {"intrinsics": 70, "width": 640, "height": 480, "translation": [2.0, 3.0, 3.0],
          "rotation": [-40.0, 5.0, 25.0], "scale": [1.0, 1.0, 1.0]}
  return Camera("euler-cam", info)


@pytest.fixture(autouse=True)
def _reset_provider():
  provider.set_active_registry(None)
  yield
  provider.set_active_registry(None)


@pytest.fixture(scope="module")
def schema():
  return SchemaValidation(str(SCHEMA_PATH), is_multi_message=True)


@pytest.fixture
def ptz_scene(scene_obj, camera_obj):
  scene_obj.uid = SCENE_UID
  scene_obj.cameras[SOURCE] = _ptz_camera(camera_obj)
  return scene_obj


def _make_registry(schema, scene, mode=MODE_ENFORCE, now_offset_s=LOCAL_NOW_OFFSET_S):
  settings = PTZSettings(mode=mode, consumer=CONSUMER, assignments={SOURCE: RESOLVER})
  registry = PTZPoseRegistry(settings, schema, lambda: (_ns(now_offset_s), True))
  registry.reconcile([scene])
  return registry


def _feed(registry, matrix, count=30, first_sequence=1):
  registry.on_status_message(STATUS_TOPIC, orjson.dumps(status_payload(RESOLVER, _at(-100))))
  for index in range(count):
    payload = pose_context(SOURCE, first_sequence + index, _at(index * 0.1), FRAME, VERSION,
                           matrix=matrix)
    assert registry.on_pose_message(POSE_TOPIC, orjson.dumps(payload)) is None


def _frame(offset_s=OBSERVATION_OFFSET_S):
  frame = copy.deepcopy(jdata)
  frame["id"] = SOURCE
  frame["timestamp"] = iso(_at(offset_s))
  return frame


def _snapshot(matrix, sequence=1):
  payload = pose_context(SOURCE, sequence, _at(0), FRAME, VERSION, matrix=matrix)
  return PoseSnapshot.from_payload(payload)


def _reference_pixels(camera, point):
  """Pixels of a world point from the static pose alone (point-correspondence cameras lack
  CameraPose's own world-to-pixel projection)."""
  inverse = np.linalg.inv(camera.pose.pose_mat)
  rvec = cv2.Rodrigues(inverse[:3, :3])[0]
  pixels, _ = cv2.projectPoints(point.asNumpyCartesian, rvec, inverse[:3, 3:4],
                                camera.pose.intrinsics.intrinsics,
                                camera.pose.intrinsics.distortion)
  return np.squeeze(pixels.reshape(-1, 2))


def _pixel_probe_points(camera):
  pose = camera.pose
  return [pose.cameraPointToWorldPoint(Point(x, y)) for x in (-0.2, 0.0, 0.25)
          for y in (0.1, 0.3)]


class TestHomePoseEquivalence:
  """The home pose fed as a synthetic PoseContext must equal the static projection."""

  @pytest.fixture(params=["point_correspondence", "euler"])
  def static_camera(self, request, camera_obj):
    return camera_obj if request.param == "point_correspondence" else _euler_camera()

  def test_pixels_match_the_static_projection(self, static_camera):
    projected = ProjectedCamera(static_camera, _snapshot(static_camera.pose.pose_mat.tolist()))
    for point in _pixel_probe_points(static_camera):
      expected = _reference_pixels(static_camera, point)
      actual = projected.pose.projectWorldPointToCameraPixels(point)
      assert abs(actual.x - expected[0]) <= EPSILON_SYNTHETIC_PX
      assert abs(actual.y - expected[1]) <= EPSILON_SYNTHETIC_PX

  def test_ray_projection_to_the_ground_matches(self, static_camera):
    projected = ProjectedCamera(static_camera, _snapshot(static_camera.pose.pose_mat.tolist()))
    for x in (-0.2, 0.0, 0.25):
      expected = static_camera.pose.cameraPointToWorldPoint(Point(x, 0.2))
      actual = projected.pose.cameraPointToWorldPoint(Point(x, 0.2))
      np.testing.assert_allclose(actual.asNumpyCartesian, expected.asNumpyCartesian, atol=1e-9)

  def test_intrinsics_distortion_and_region_are_static(self, static_camera):
    projected = ProjectedCamera(static_camera, _snapshot(static_camera.pose.pose_mat.tolist()))
    assert projected.pose.intrinsics is static_camera.pose.intrinsics
    assert projected.pose.resolution == static_camera.pose.resolution
    np.testing.assert_allclose(projected.pose.translation.asNumpyCartesian,
                               static_camera.pose.translation.asNumpyCartesian, atol=1e-12)

  def test_a_rotated_pose_changes_the_projection(self, static_camera):
    rotated = rotated_matrix(static_camera.pose.pose_mat.tolist(), 15.0)
    projected = ProjectedCamera(static_camera, _snapshot(rotated))
    point = static_camera.pose.cameraPointToWorldPoint(Point(0.1, 0.2))
    moved = projected.pose.cameraPointToWorldPoint(Point(0.1, 0.2))
    assert np.linalg.norm(moved.asNumpyCartesian - point.asNumpyCartesian) > 0.05
    np.testing.assert_allclose(projected.pose.translation.asNumpyCartesian,
                               static_camera.pose.translation.asNumpyCartesian, atol=1e-9)

  def test_the_stored_camera_is_untouched(self, static_camera):
    before = static_camera.pose.pose_mat.copy()
    ProjectedCamera(static_camera, _snapshot(rotated_matrix(before.tolist(), 30.0)))
    np.testing.assert_array_equal(static_camera.pose.pose_mat, before)


class TestProcessCameraData:
  def _tracked(self, scene):
    return scene.tracker.trackers["person"].curObjects

  def test_context_projects_with_the_per_frame_pose(self, schema, ptz_scene, camera_obj):
    rotated = rotated_matrix(camera_obj.pose.pose_mat.tolist(), 20.0)
    registry = _make_registry(schema, ptz_scene)
    _feed(registry, rotated)
    context = registry.admit(camera_obj, _ns(OBSERVATION_OFFSET_S)).context
    assert context is not None

    assert ptz_scene.processCameraData(_frame(), when=when, pose_context=context)
    moving = self._tracked(ptz_scene)[0]
    assert moving.camera is context.camera
    assert moving.camera.cameraID == SOURCE

    assert ptz_scene.processCameraData(_frame(), when=when)
    static = self._tracked(ptz_scene)[0]
    assert static.camera is camera_obj
    assert np.linalg.norm(
      moving.sceneLoc.asNumpyCartesian - static.sceneLoc.asNumpyCartesian) > 0.05

  def test_home_pose_context_matches_the_static_path(self, schema, ptz_scene, camera_obj):
    registry = _make_registry(schema, ptz_scene)
    _feed(registry, camera_obj.pose.pose_mat.tolist())
    context = registry.admit(camera_obj, _ns(OBSERVATION_OFFSET_S)).context

    ptz_scene.processCameraData(_frame(), when=when, pose_context=context)
    dynamic = self._tracked(ptz_scene)[0].sceneLoc.asNumpyCartesian
    ptz_scene.processCameraData(_frame(), when=when)
    static = self._tracked(ptz_scene)[0].sceneLoc.asNumpyCartesian
    np.testing.assert_allclose(dynamic, static, atol=1e-9)

  def test_unknown_camera_still_fails(self, ptz_scene):
    frame = _frame()
    frame["id"] = "missing"
    assert ptz_scene.processCameraData(frame, when=when) is False


class TestVisibility:
  @staticmethod
  def _object(scene):
    class _Object:
      sceneLoc = Point(1.5, 4.0, 0.0)
    return _Object()

  def test_static_cameras_are_unaffected_by_the_provider(self, schema, ptz_scene, camera_obj):
    ptz_scene.cameras[SOURCE] = camera_obj  # not PTZ
    camera_obj.ptz_calibration = None
    provider.set_active_registry(_make_registry(schema, ptz_scene))
    obj = self._object(ptz_scene)
    ptz_scene._updateVisible([obj])
    assert obj.visibility == [SOURCE]

  def test_ptz_camera_without_a_pose_sees_nothing(self, schema, ptz_scene):
    provider.set_active_registry(_make_registry(schema, ptz_scene))
    obj = self._object(ptz_scene)
    ptz_scene._updateVisible([obj])
    assert obj.visibility == []

  def test_ptz_camera_with_a_fresh_pose_is_visible(self, schema, ptz_scene, camera_obj):
    registry = _make_registry(schema, ptz_scene)
    _feed(registry, camera_obj.pose.pose_mat.tolist())
    provider.set_active_registry(registry)
    obj = self._object(ptz_scene)
    ptz_scene._updateVisible([obj])
    assert obj.visibility == [SOURCE]

  def test_ptz_camera_with_a_stale_pose_sees_nothing(self, schema, ptz_scene, camera_obj):
    registry = _make_registry(schema, ptz_scene, now_offset_s=LAST_POSE_OFFSET_S + 0.6)
    _feed(registry, camera_obj.pose.pose_mat.tolist())
    provider.set_active_registry(registry)
    obj = self._object(ptz_scene)
    ptz_scene._updateVisible([obj])
    assert obj.visibility == []

  def test_flags_off_keeps_the_static_view_region(self, ptz_scene):
    obj = self._object(ptz_scene)
    ptz_scene._updateVisible([obj])
    assert obj.visibility == [SOURCE]

  def test_camera_lookup_for_bounds(self, schema, ptz_scene, camera_obj):
    registry = _make_registry(schema, ptz_scene)
    provider.set_active_registry(registry)
    assert ptz_scene.visibilityCameraWithID("missing") is None
    assert ptz_scene.visibilityCameraWithID(SOURCE) is None
    _feed(registry, camera_obj.pose.pose_mat.tolist())
    assert isinstance(ptz_scene.visibilityCameraWithID(SOURCE), ProjectedCamera)

  def test_regulated_bounds_skip_a_ptz_camera_without_a_pose(self, schema, ptz_scene, camera_obj):
    registry = _make_registry(schema, ptz_scene)
    provider.set_active_registry(registry)
    obj_dict = {"visibility": [SOURCE], "translation": [1.5, 4.0, 0.0],
                "bb_meters": {"width": 0.5, "height": 1.7}}
    computeCameraBounds(ptz_scene, None, obj_dict)
    assert obj_dict["camera_bounds"] == {}

    _feed(registry, camera_obj.pose.pose_mat.tolist())
    obj_dict = {"visibility": [SOURCE], "translation": [1.5, 4.0, 0.0],
                "bb_meters": {"width": 0.5, "height": 1.7}}
    computeCameraBounds(ptz_scene, None, obj_dict)
    assert obj_dict["camera_bounds"][SOURCE]["projected"] is True


class TestIngress:
  @pytest.fixture
  def stream(self):
    return io.StringIO()

  def _ingress(self, schema, scene, stream, mode, matrix=None, feed=True, every_n=1):
    registry = _make_registry(schema, scene, mode=mode)
    if feed:
      _feed(registry, matrix or scene.cameras[SOURCE].pose.pose_mat.tolist())
    settings = registry.settings
    recorder = ShadowRecorder("run-7", every_n, stream)
    return PTZIngress(settings, registry, recorder)

  def _records(self, stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]

  def test_static_camera_passes_through_without_a_record(self, schema, ptz_scene, stream):
    ingress = self._ingress(schema, ptz_scene, stream, MODE_ENFORCE)
    static = Camera("static-cam", {"intrinsics": 70, "width": 640, "height": 480})
    ptz_scene.cameras["static-cam"] = static
    assert ingress.filter(ptz_scene, "static-cam", _frame(), when) == (True, None)
    assert ingress.filter(ptz_scene, "unknown", _frame(), when) == (True, None)
    assert stream.getvalue() == ""

  def test_enforcing_drops_a_rejected_message_and_records_why(self, schema, ptz_scene, stream):
    ingress = self._ingress(schema, ptz_scene, stream, MODE_ENFORCE, feed=False)
    with patch("controller.ptz.ingress.metrics.inc_ptz_rejected") as rejected:
      process, context = ingress.filter(ptz_scene, SOURCE, _frame(), when)
    assert (process, context) == (False, None)
    rejected.assert_called_once_with({"mode": "enforce", "reason_detail": "no_sample"})
    record = self._records(stream)[0]
    assert (record["admitted"], record["reason_detail"]) == (False, "no_sample")
    assert record["invalid_reason"] == "no_pose_available"

  def test_enforcing_admits_with_a_projection_context(self, schema, ptz_scene, stream):
    ingress = self._ingress(schema, ptz_scene, stream, MODE_ENFORCE)
    with patch("controller.ptz.ingress.metrics.inc_ptz_admitted") as admitted:
      process, context = ingress.filter(ptz_scene, SOURCE, _frame(), when)
    assert process is True and context.source_id == SOURCE and context.sequence == 30
    admitted.assert_called_once_with({"mode": "enforce"})
    record = self._records(stream)[0]
    assert record["profile"] == "controller" and record["mode"] == "enforce"
    assert record["run_id"] == "run-7" and record["scene_id"] == SCENE_UID
    assert record["sequence"] == 30 and record["calibration_version"] == VERSION
    assert record["dwell_elapsed_s"] == pytest.approx(LAST_POSE_OFFSET_S)
    assert record["detections"] == []

  def test_shadow_never_changes_the_live_path(self, schema, ptz_scene, stream):
    ingress = self._ingress(schema, ptz_scene, stream, MODE_SHADOW)
    assert ingress.filter(ptz_scene, SOURCE, _frame(), when) == (True, None)
    rejecting = self._ingress(schema, ptz_scene, io.StringIO(), MODE_SHADOW, feed=False)
    assert rejecting.filter(ptz_scene, SOURCE, _frame(), when) == (True, None)

  def test_shadow_record_has_zero_residual_at_the_home_pose(self, schema, ptz_scene, stream):
    ingress = self._ingress(schema, ptz_scene, stream, MODE_SHADOW)
    ingress.filter(ptz_scene, SOURCE, _frame(), when)
    record = self._records(stream)[0]
    assert record["mode"] == "shadow" and record["admitted"] is True
    assert len(record["detections"]) == len(jdata["objects"]["person"])
    for detection in record["detections"]:
      assert detection["residual_m"] == pytest.approx(0.0, abs=1e-9)
      assert len(detection["static_xyz"]) == len(detection["candidate_xyz"]) == 3

  def test_shadow_record_reports_the_residual_of_an_off_home_pose(self, schema, ptz_scene, stream):
    rotated = rotated_matrix(ptz_scene.cameras[SOURCE].pose.pose_mat.tolist(), 20.0)
    ingress = self._ingress(schema, ptz_scene, stream, MODE_SHADOW, matrix=rotated)
    frame = _frame()
    ingress.filter(ptz_scene, SOURCE, frame, when)
    record = self._records(stream)[0]
    assert all(d["residual_m"] > 0.05 for d in record["detections"])
    assert frame == _frame(), "shadow projection must not modify the message"

  def test_shadow_does_not_touch_tracker_state(self, schema, ptz_scene, stream):
    ingress = self._ingress(schema, ptz_scene, stream, MODE_SHADOW)
    ingress.filter(ptz_scene, SOURCE, _frame(), when)
    assert ptz_scene.tracker.trackers == {}

  def test_shadow_failure_is_contained(self, schema, ptz_scene, stream):
    ingress = self._ingress(schema, ptz_scene, stream, MODE_SHADOW)
    with patch.object(ptz_scene, "createMovingObjectsForDetection", side_effect=ValueError("x")):
      assert ingress.filter(ptz_scene, SOURCE, _frame(), when) == (True, None)
    assert self._records(stream)[0]["detections"] == []

  def test_candidate_residuals_returns_none_on_failure(self, ptz_scene, camera_obj):
    with patch.object(ptz_scene, "createMovingObjectsForDetection", side_effect=ValueError("x")):
      assert candidate_residuals(ptz_scene, _frame(), when, camera_obj, camera_obj) is None

  def test_missing_timestamp_falls_back_to_the_message_time(self, schema, ptz_scene, stream):
    ingress = self._ingress(schema, ptz_scene, stream, MODE_ENFORCE)
    frame = _frame()
    del frame["timestamp"]
    process, _ = ingress.filter(ptz_scene, SOURCE, frame, _ns(OBSERVATION_OFFSET_S) / NS_PER_S)
    assert process is True

  def test_message_newer_than_the_latest_pose_is_dropped(self, schema, ptz_scene, stream):
    ingress = self._ingress(schema, ptz_scene, stream, MODE_ENFORCE)
    process, _ = ingress.filter(ptz_scene, SOURCE, _frame(LAST_POSE_OFFSET_S + 0.01), when)
    assert process is False
    assert self._records(stream)[0]["reason_detail"] == "no_sample"


class TestShadowRecorder:
  class _Admission:
    def __init__(self, admitted, detail=None):
      self.admitted, self.reason_detail = admitted, detail
      self.managed, self.invalid_reason = True, None
      self.sequence = self.calibration_version = None
      self.pose_age_s = self.timestamp_uncertainty_s = self.dwell_elapsed_s = None

  def _record(self, recorder, admission, source="cam"):
    scene = type("S", (), {"uid": "s"})()
    return recorder.record("shadow", scene, source, {"timestamp": "t"}, admission)

  def test_samples_every_nth_decision_and_every_change(self):
    stream = io.StringIO()
    recorder = ShadowRecorder("r", 3, stream)
    admitted = self._Admission(True)
    emitted = [self._record(recorder, admitted) for _ in range(7)]
    assert emitted == [True, False, False, True, False, False, True]
    assert self._record(recorder, self._Admission(False, "moving")) is True
    assert self._record(recorder, self._Admission(False, "moving")) is False
    assert self._record(recorder, self._Admission(False, "settling")) is True

  def test_sources_are_sampled_independently(self):
    recorder = ShadowRecorder("r", 100, io.StringIO())
    admitted = self._Admission(True)
    assert self._record(recorder, admitted, "a") is True
    assert self._record(recorder, admitted, "b") is True
    assert self._record(recorder, admitted, "a") is False

  def test_records_are_single_line_json(self):
    stream = io.StringIO()
    recorder = ShadowRecorder("r", 1, stream)
    self._record(recorder, self._Admission(True))
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["record_type"] == "ptz_shadow"

  def test_detections_are_bounded(self):
    stream = io.StringIO()
    recorder = ShadowRecorder("r", 1, stream)
    scene = type("S", (), {"uid": "s"})()
    recorder.record("shadow", scene, "cam", {}, self._Admission(True), [{"n": i} for i in range(80)])
    assert len(json.loads(stream.getvalue())["detections"]) == 50
