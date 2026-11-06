# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Service-level projection and conditioning tests with a mocked projection kernel."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from observation_processor.conditioning import InvalidRequestError, UNOBSERVABLE_SIGMA
from observation_processor.grpc_api import observation_processor_pb2 as pb
from observation_processor.scene_provider import (
  CameraNotCalibratedError, CameraNotFoundError, SceneMeshMissingError,
  SceneNotFoundError, SceneProvider, StoreUnavailableError,
)


def _assert_measurement(entry):
  assert entry.status == pb.MEASUREMENT_STATUS_OK
  assert len(entry.measurement.mean) == 7
  assert len(entry.measurement.noise_covariance) == 49
  covariance = np.asarray(entry.measurement.noise_covariance).reshape(7, 7)
  assert np.all(np.isfinite(entry.measurement.mean))
  np.testing.assert_allclose(covariance, covariance.T, atol=1e-12)
  assert np.linalg.eigvalsh(covariance).min() > 0
  np.testing.assert_allclose(covariance[3:, 3:], np.eye(4) * 0.2)
  assert entry.measurement.z_measured
  assert not entry.measurement.has_orientation
  assert entry.measurement.mean[6] == 0
  assert len(entry.frustum.covariance) == 9
  return covariance


def _ray(entry):
  return np.array([entry.frustum.ray.x, entry.frustum.ray.y, entry.frustum.ray.z])


def test_pipeline_assembles_tracker_measurement_from_kernel_output(
    process_frame, frame, projection_configuration):
  response = process_frame(frame)
  assert response.scene_id == frame.scene_id
  assert response.camera_id == frame.camera_id
  assert response.timestamp == frame.timestamp
  assert response.mode == pb.CONDITIONING_MODE_FRUSTUM_ONLY
  entry = response.measurements[0]
  assert entry.detection_id == frame.detections[0].detection_id
  assert entry.depth_source == pb.DEPTH_SOURCE_FRUSTUM
  assert not entry.HasField("amodal")
  covariance = _assert_measurement(entry)
  call = projection_configuration.projector.call_args.kwargs
  np.testing.assert_array_equal(call["boxes"], [[54, 25, 74, 71]])
  np.testing.assert_allclose(call["priors"], [[0.6, 0.5, 1.8, 0.09, 0.075, 0.27]])
  np.testing.assert_array_equal(call["intrinsics"], [100, 100, 64, 48])
  np.testing.assert_array_equal(call["img_size"], [128, 96])
  np.testing.assert_allclose(entry.frustum.depth_est, 2.0)
  np.testing.assert_allclose(entry.measurement.mean[3:6], [0.6, 0.5, 1.8])
  ray = _ray(entry)
  origin = np.array([0, 0, 3])
  np.testing.assert_allclose(ray, [0, 0, -1])
  np.testing.assert_allclose(entry.measurement.mean[:3], origin + ray * 2.0, atol=1e-6)
  np.testing.assert_allclose(ray @ covariance[:3, :3] @ ray,
                             0.1 ** 2, rtol=1e-6)
  assert entry.frustum.edge_valid_mask == 15


@pytest.mark.parametrize("mode", [pb.CONDITIONING_MODE_FRUSTUM_ONLY, pb.CONDITIONING_MODE_FULL])
def test_diagnostics_are_omitted_by_default(process_frame, frame, mode):
  frame.mode = mode
  frame.ClearField("include_diagnostics")
  entry = process_frame(frame).measurements[0]
  assert not entry.HasField("frustum")
  assert not entry.HasField("amodal")
  assert entry.HasField("measurement")


@pytest.mark.parametrize("has_mesh", [True, False])
def test_auto_resolves_mode(process_frame, frame, projection_configuration, has_mesh):
  if not has_mesh:
    projection_configuration.scene["map"] = "/media/floor.png"
    projection_configuration.provider.warm()
  frame.mode = pb.CONDITIONING_MODE_AUTO
  response = process_frame(frame)
  assert response.mode == (pb.CONDITIONING_MODE_FULL if has_mesh
                            else pb.CONDITIONING_MODE_FRUSTUM_ONLY)
  entry = response.measurements[0]
  _assert_measurement(entry)
  assert entry.HasField("amodal") == has_mesh


def test_amodal_receives_camera_origin_and_replaces_depth_variance(process_frame, frame,
                                                                  projection_configuration):
  frame.mode = pb.CONDITIONING_MODE_FULL
  reasoner = projection_configuration.provider.get_reasoner("scene", "camera")
  captured = {}

  def generate(rays):
    captured.update(rays)
    return rays["depth_est"] * 0.8, np.full(len(rays["depth_est"]), 0.00001)

  with patch.object(reasoner, "generate", side_effect=generate):
    entry = process_frame(frame).measurements[0]
  np.testing.assert_allclose(captured["mu"], [[0, 0, 3]])
  assert "origin" not in captured
  assert entry.depth_source == pb.DEPTH_SOURCE_AMODAL
  np.testing.assert_allclose(entry.amodal.depth, entry.frustum.depth_est * 0.8, rtol=1e-6)
  assert entry.amodal.depth_variance == 0.00001
  covariance = _assert_measurement(entry)
  ray = _ray(entry)
  np.testing.assert_allclose(ray @ covariance[:3, :3] @ ray, 1e-4, rtol=1e-6)


@pytest.mark.parametrize("mode", [pb.CONDITIONING_MODE_FULL, pb.CONDITIONING_MODE_FRUSTUM_ONLY])
def test_mesh_foot_uses_bottom_center_and_lifts_half_height(process_frame, frame, mode):
  frame.mode = mode
  frame.detections[0].project_to_map = True
  entry = process_frame(frame).measurements[0]
  covariance = _assert_measurement(entry)
  assert entry.depth_source == pb.DEPTH_SOURCE_MESH_FOOT
  np.testing.assert_allclose(entry.measurement.mean[:3], [0, -0.69, 0.9], atol=1e-5)
  ray = _ray(entry)
  assert ray @ covariance[:3, :3] @ ray <= 0.05 ** 2 + 1e-9
  assert entry.HasField("amodal") == (mode == pb.CONDITIONING_MODE_FULL)


def test_mesh_miss_retains_frustum_depth(process_frame, frame):
  frame.detections[0].project_to_map = True
  frame.detections[0].bounding_box_px.x = 10000
  entry = process_frame(frame).measurements[0]
  _assert_measurement(entry)
  assert entry.depth_source == pb.DEPTH_SOURCE_FRUSTUM


def test_mixed_categories_fallback_flags_and_order(
  process_frame, frame, projection_configuration):
  for category in ("car", "unknown", "person"):
    detection = frame.detections.add()
    detection.CopyFrom(frame.detections[0])
    detection.category = category
    detection.detection_id = category
  frame.detections[3].axis_aware_sizing = False
  entries = process_frame(frame).measurements
  assert [entry.detection_id for entry in entries] == ["detection", "car", "unknown", "person"]
  np.testing.assert_allclose(entries[1].measurement.mean[3:6], [2, 4.5, 1.5])
  np.testing.assert_allclose(entries[2].measurement.mean[3:6], [0.55, 0.55, 1.7])
  assert entries[1].depth_source == pb.DEPTH_SOURCE_MESH_FOOT
  call = projection_configuration.projector.call_args.kwargs
  np.testing.assert_allclose(call["priors"][:, :3], [
    [0.6, 0.5, 1.8], [2.0, 4.5, 1.5], [0.55, 0.55, 1.7], [0.6, 0.5, 1.8]])
  assert call["axis_aware"].tolist() == [True, False, True, False]
  frame.detections[1].project_to_map = False
  frame.detections[1].axis_aware_sizing = True
  updated = process_frame(frame).measurements[1]
  assert updated.depth_source == pb.DEPTH_SOURCE_FRUSTUM
  call = projection_configuration.projector.call_args.kwargs
  assert call["axis_aware"].tolist()[1] is True


@pytest.mark.parametrize("mode", [pb.CONDITIONING_MODE_AUTO, pb.CONDITIONING_MODE_FRUSTUM_ONLY])
def test_empty_frame_is_valid(process_frame, frame, mode):
  frame.mode = mode
  frame.ClearField("detections")
  response = process_frame(frame)
  assert not response.measurements
  assert response.timestamp == frame.timestamp
  assert response.mode != pb.CONDITIONING_MODE_AUTO


def test_unobservable_detection_is_not_sent_to_amodal(
  process_frame, frame, projection_configuration):
  frame.mode = pb.CONDITIONING_MODE_FULL
  zero = frame.detections.add()
  zero.CopyFrom(frame.detections[0])
  zero.bounding_box_px.width = 0
  zero.bounding_box_px.height = 0
  original_projector = projection_configuration.projector.side_effect

  def project_with_unobservable_detection(*args, **kwargs):
    observations = original_projector(*args, **kwargs)
    observations["depth_sigma"][1] = UNOBSERVABLE_SIGMA
    return observations

  projection_configuration.projector.side_effect = project_with_unobservable_detection
  reasoner = projection_configuration.provider.get_reasoner("scene", "camera")
  with patch.object(reasoner, "generate", wraps=reasoner.generate) as generate:
    entries = process_frame(frame).measurements
  assert len(generate.call_args.args[0]["depth_est"]) == 1
  _assert_measurement(entries[0])
  assert entries[1].status == pb.MEASUREMENT_STATUS_DEPTH_UNOBSERVABLE
  assert entries[1].HasField("frustum")
  assert not entries[1].HasField("measurement")
  assert not entries[1].HasField("amodal")
  assert entries[1].depth_source == pb.DEPTH_SOURCE_UNSPECIFIED


@pytest.mark.parametrize("width,height", [(0, 30), (20, 0), (0.000001, 0.000001)])
def test_degenerate_boxes_are_passed_to_projection_kernel(
    process_frame, frame, projection_configuration, width, height):
  box = frame.detections[0].bounding_box_px
  box.width, box.height = width, height
  _assert_measurement(process_frame(frame).measurements[0])
  np.testing.assert_allclose(
    projection_configuration.projector.call_args.kwargs["boxes"],
    [[box.x, box.y, box.x + box.width, box.y + box.height]])


@pytest.mark.parametrize("field", ["x", "y", "width", "height"])
@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), float("-inf"), 1e300])
def test_invalid_box_rejects_whole_frame(process_frame, frame, field, value):
  invalid = frame.detections.add()
  invalid.CopyFrom(frame.detections[0])
  setattr(invalid.bounding_box_px, field, value)
  with pytest.raises(InvalidRequestError):
    process_frame(frame)


@pytest.mark.parametrize("field", ["scene_id", "camera_id", "timestamp"])
def test_missing_frame_field(process_frame, frame, field):
  frame.ClearField(field)
  with pytest.raises(InvalidRequestError):
    process_frame(frame)


@pytest.mark.parametrize("field", ["category", "bounding_box_px"])
def test_missing_detection_field(process_frame, frame, field):
  frame.detections[0].ClearField(field)
  with pytest.raises(InvalidRequestError):
    process_frame(frame)


@pytest.mark.parametrize("seconds,nanos", [
  (-62135596801, 0), (253402300800, 0), (0, -1), (0, 1000000000),
])
def test_invalid_timestamp(process_frame, frame, seconds, nanos):
  frame.timestamp.seconds, frame.timestamp.nanos = seconds, nanos
  with pytest.raises(InvalidRequestError):
    process_frame(frame)


def test_invalid_mode(process_frame, frame):
  frame.mode = 999
  with pytest.raises(InvalidRequestError):
    process_frame(frame)


@pytest.mark.parametrize("field", ["scene_id", "camera_id"])
def test_unknown_scene_or_camera(process_frame, frame, field):
  setattr(frame, field, "missing")
  exception = SceneNotFoundError if field == "scene_id" else CameraNotFoundError
  with pytest.raises(exception):
    process_frame(frame)


@pytest.mark.parametrize("change", ["missing_intrinsics", "zero_focal", "bad_pose", "bad_distortion"])
def test_invalid_calibration_maps_to_precondition(process_frame, frame, projection_configuration, change):
  camera = projection_configuration.camera
  if change == "missing_intrinsics":
    camera.pop("intrinsics")
  elif change == "zero_focal":
    camera["intrinsics"]["fx"] = 0
  elif change == "bad_pose":
    camera["rotation"] = [float("nan"), 0, 0]
  else:
    camera["distortion"] = [0, 0, 0]
  with pytest.raises(CameraNotCalibratedError):
    process_frame(frame)


def test_full_requires_mesh(process_frame, frame, projection_configuration):
  projection_configuration.scene["map"] = "/media/floor.png"
  projection_configuration.provider.warm()
  frame.mode = pb.CONDITIONING_MODE_FULL
  with pytest.raises(SceneMeshMissingError):
    process_frame(frame)


def test_pending_refresh_rejects_requests_without_cold_loading(process_frame, frame,
                                                              projection_configuration):
  projection_configuration.provider.invalidate()
  with pytest.raises(StoreUnavailableError):
    process_frame(frame)


def test_store_unavailable_mapping(process_frame, frame, projection_configuration):
  with patch.object(projection_configuration.provider, "snapshot",
                    side_effect=StoreUnavailableError("offline")), \
       pytest.raises(StoreUnavailableError):
    process_frame(frame)


@pytest.mark.parametrize("failure", ["kernel", "amodal_exception", "amodal_nan"])
def test_computation_failures_are_internal(process_frame, frame, projection_configuration, failure):
  frame.mode = pb.CONDITIONING_MODE_FULL
  reasoner = projection_configuration.provider.get_reasoner("scene", "camera")
  if failure == "kernel":
    target = patch("observation_processor.conditioning.fg.project_frustum_batch",
                   side_effect=RuntimeError("kernel failed"))
  elif failure == "amodal_exception":
    target = patch.object(reasoner, "generate", side_effect=ValueError("conditioning failed"))
  else:
    target = patch.object(reasoner, "generate", return_value=(np.array([np.nan]), np.array([1])))
  expected_error = RuntimeError if failure == "kernel" else ValueError
  with target, pytest.raises(expected_error):
    process_frame(frame)


def test_undistortion_and_raw_clipping_mask(process_frame, frame, projection_configuration):
  camera = projection_configuration.camera
  camera["distortion"] = {"k1": 0.2, "k2": -0.03, "p1": 0.002, "p2": -0.001}
  detection = frame.detections[0]
  detection.bounding_box_px.CopyFrom(pb.BoundingBoxPx(x=1, y=20, width=25, height=40))
  process_frame(frame)
  matrix = np.array([[100, 0, 64], [0, 100, 48], [0, 0, 1]], dtype=float)
  coefficients = np.array([0.2, -0.03, 0.002, -0.001, 0])
  raw_corners = np.array([[1, 20], [26, 20], [26, 60], [1, 60]], dtype=float)
  corrected = cv2.undistortPointsIter(raw_corners.reshape(-1, 1, 2), matrix, coefficients,
                                    None, matrix, (3, 30, 1e-10)).reshape(4, 2)
  call = projection_configuration.projector.call_args.kwargs
  np.testing.assert_allclose(
    call["boxes"], [np.r_[corrected.min(axis=0), corrected.max(axis=0)]])
  assert call["clipped"].tolist() == [1]


@pytest.mark.parametrize("count", [4, 5, 8, 12, 14])
def test_supported_distortion_lengths(process_frame, frame, projection_configuration, count):
  projection_configuration.camera["distortion"] = [0.0] * count
  _assert_measurement(process_frame(frame).measurements[0])
  assert projection_configuration.projector.called


def test_clipped_full_frame_passes_edge_mask_to_projection_kernel(
    process_frame, frame, projection_configuration):
  frame.detections[0].bounding_box_px.CopyFrom(pb.BoundingBoxPx(x=0, y=0, width=128, height=96))
  entry = process_frame(frame).measurements[0]
  _assert_measurement(entry)
  assert projection_configuration.projector.call_args.kwargs["clipped"].tolist() == [15]


def test_concurrent_full_requests_reuse_preloaded_geometry(process_frame, frame, projection_configuration):
  frame.mode = pb.CONDITIONING_MODE_FULL
  provider = projection_configuration.provider
  reasoner = provider.get_reasoner("scene", "camera")
  with patch.object(SceneProvider, "_load_world_mesh", side_effect=AssertionError("cold load")), \
       patch("observation_conditioning.AmodalReasoner", side_effect=AssertionError("cold bake")):
    with ThreadPoolExecutor(max_workers=4) as executor:
      responses = list(executor.map(process_frame, [frame] * 8))
  assert provider.get_reasoner("scene", "camera") is reasoner
  for response in responses:
    _assert_measurement(response.measurements[0])
    assert response == responses[0]


@pytest.mark.parametrize("value", [0, -1, float("nan")])
def test_invalid_asset_does_not_silently_use_pedestrian_prior(process_frame, frame,
                                                            projection_configuration, value):
  projection_configuration.assets[0]["x_size"] = value
  with pytest.raises(ValueError):
    process_frame(frame)


def test_epoch_timestamp_and_empty_correlation_key_are_valid(process_frame, frame):
  frame.timestamp.seconds = 0
  frame.timestamp.nanos = 0
  frame.detections[0].detection_id = ""
  response = process_frame(frame)
  assert response.HasField("timestamp")
  assert response.timestamp.seconds == response.timestamp.nanos == 0
  assert response.measurements[0].detection_id == ""


def test_invalid_camera_is_skipped_during_warmup_and_reported_by_pipeline(process_frame, frame,
                                                                         projection_configuration):
  configuration = projection_configuration
  configuration.camera["intrinsics"]["fx"] = 0
  configuration.provider.invalidate()
  configuration.provider.warm()
  assert not configuration.provider.needs_refresh
  with pytest.raises(CameraNotCalibratedError):
    process_frame(frame)


def test_requests_only_read_the_pinned_cache(process_frame, frame, projection_configuration):
  rest = projection_configuration.rest
  rest.reset_mock()
  frame.mode = pb.CONDITIONING_MODE_FULL
  _assert_measurement(process_frame(frame).measurements[0])
  frame.scene_id = "missing"
  with pytest.raises(SceneNotFoundError):
    process_frame(frame)
  rest.getScene.assert_not_called()
  rest.getCameras.assert_not_called()
  rest.getAssets.assert_not_called()


def test_camera_pose_is_passed_to_world_transform(process_frame, frame,
                                                  projection_configuration):
  camera = projection_configuration.camera
  camera["translation"] = [5, -2, 4]
  camera["rotation"] = [20, 30, 40]
  entry = process_frame(frame).measurements[0]
  camera_info = projection_configuration.provider.snapshot().get_camera("scene", "camera")
  np.testing.assert_allclose(projection_configuration.transformer.call_args.args[1],
                             camera_info.pose_mat)
  np.testing.assert_allclose(entry.measurement.mean[:3],
                             camera_info.pose_mat[:3, 3] + np.array([0, 0, -2]), atol=1e-6)
  _assert_measurement(entry)


def test_distorted_mesh_foot_uses_separately_rectified_bottom_pixel(process_frame, frame,
                                                                 projection_configuration):
  camera = projection_configuration.camera
  camera["distortion"] = [0.2, 0, 0.001, -0.002]
  frame.detections[0].project_to_map = True
  frame.detections[0].bounding_box_px.x = 85
  entry = process_frame(frame).measurements[0]
  matrix = np.array([[100, 0, 64], [0, 100, 48], [0, 0, 1]], dtype=float)
  corrected = cv2.undistortPointsIter(np.array([[[95.0, 71.0]]]), matrix,
                                    np.array(camera["distortion"]), None, None,
                                    (3, 30, 1e-10)).reshape(2)
  expected = [corrected[0] * 3, -corrected[1] * 3, 0.9]
  assert entry.depth_source == pb.DEPTH_SOURCE_MESH_FOOT
  np.testing.assert_allclose(entry.measurement.mean[:3], expected, atol=1e-5)


def test_project_to_map_without_mesh_retains_frustum(process_frame, frame, projection_configuration):
  projection_configuration.scene["map"] = "/media/floor.png"
  projection_configuration.provider.warm()
  frame.detections[0].project_to_map = True
  entry = process_frame(frame).measurements[0]
  assert entry.depth_source == pb.DEPTH_SOURCE_FRUSTUM
  _assert_measurement(entry)
