# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from manager.calculate_intrinsics_view import (
  CalculateCameraIntrinsics,
  MAX_CALIBRATION_CORRESPONDENCES,
  MAX_IMAGE_DIMENSION_PX,
  as_distortion_column,
  assess_calibration_geometry,
  assess_image_point_coverage,
  assess_map_point_geometry,
  fit_pose_fixed_intrinsics,
  needs_pose_only_fit,
  parse_outlier_threshold_px,
  parse_pixels_per_meter,
  parse_reject_outliers,
  validate_correspondence_arrays,
  validate_distortion_coefficients,
  validate_image_size,
  validate_intrinsics_matrix,
)
from scene_common.transform import (
  RANSAC_REPROJECTION_THRESHOLD_PX,
  RANSAC_THRESHOLD_MAX_PX,
  RANSAC_THRESHOLD_MIN_PX,
  scaled_reprojection_threshold_px,
  solve_pnpransac,
)


def _calibration_payload(**overrides):
  payload = {
    "mapPoints": [
      [0.0, 0.0, 0.0],
      [1.0, 0.0, 0.0],
      [1.0, 1.0, 0.0],
      [0.0, 1.0, 0.0],
      [2.0, 1.0, 0.0],
    ],
    "camPoints": [
      [320.0, 240.0],
      [480.0, 240.0],
      [480.0, 400.0],
      [320.0, 400.0],
      [640.0, 400.0],
    ],
    "intrinsics": [
      [800.0, 0.0, 320.0],
      [0.0, 800.0, 240.0],
      [0.0, 0.0, 1.0],
    ],
    "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
    "imageSize": [640, 480],
    "rejectOutliers": True,
  }
  payload.update(overrides)
  return payload


def _post_calculate_intrinsics(payload):
  request = APIRequestFactory().post(
    "/api/v1/calculateintrinsics", payload, format="json")
  force_authenticate(
    request,
    user=SimpleNamespace(is_authenticated=True, is_superuser=True),
  )
  return CalculateCameraIntrinsics.as_view()(request)


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize(
  ("inlier_mask", "reject_outliers", "expected_applied", "expected_count",
   "expected_rejected"),
  [
    (None, True, False, None, []),
    (None, False, False, None, []),
    (np.array([True, True, True, False, False]), True, False, 3, [3, 4]),
    (np.array([True, True, True, True, False]), True, True, 4, [4]),
  ],
)
def test_calculate_intrinsics_reports_rejection_and_fit_counts(
    inlier_mask, reject_outliers, expected_applied, expected_count,
    expected_rejected):
  """Response distinguishes applied rejection from all-points fallback."""
  intrinsic_matrix = np.array([
    [800.0, 0.0, 320.0],
    [0.0, 800.0, 240.0],
    [0.0, 0.0, 1.0],
  ])
  rotation = np.zeros((3, 1))
  translation = np.array([[0.0], [0.0], [5.0]])
  distortion = np.zeros(5)
  payload = _calibration_payload(
    intrinsics=intrinsic_matrix.tolist(),
    distortion=distortion.tolist(),
    rejectOutliers=reject_outliers,
  )

  with patch(
      "manager.calculate_intrinsics_view.solve_pnpransac",
      return_value=(None, None, inlier_mask)), patch(
      "cv2.calibrateCamera",
      return_value=(0.75, intrinsic_matrix, distortion, [rotation], [translation])):
    response = _post_calculate_intrinsics(payload)

  assert response.status_code == 200
  assert response.data["rejectionRequested"] is reject_outliers
  assert response.data["rejectionApplied"] is expected_applied
  assert response.data["ransacInlierCount"] == expected_count
  assert response.data["fitPointCount"] == (4 if expected_applied else 5)
  assert response.data["rejectedIndices"] == expected_rejected
  assert len(response.data["perPointErrors"]) == 5
  assert "geometryWarnings" in response.data
  assert "imageCoverage" in response.data
  assert "mapInPlaneSpreadRatio" in response.data
  pose_matrix = response.data["poseMatrix"]
  assert len(pose_matrix) == 4 and all(len(row) == 4 for row in pose_matrix)
  assert len(response.data["euler"]) == 3
  assert len(response.data["position"]) == 3


@pytest.mark.test_name("NEX-T10426")
def test_assess_map_point_geometry_flags_collinear_planar_points():
  """Nearly collinear floor-plan points produce a map geometry warning."""
  map_points = [
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [2.0, 0.01, 0.0],
    [3.0, -0.01, 0.0],
  ]
  assessment = assess_map_point_geometry(map_points)
  assert assessment["mapNearlyPlanar"] is True
  assert assessment["mapInPlaneSpreadRatio"] < 0.05
  assert any("thin line" in warning for warning in assessment["warnings"])
  assert any("triangle or rectangle" in warning
             for warning in assessment["warnings"])


@pytest.mark.test_name("NEX-T10426")
def test_assess_map_point_geometry_accepts_well_spread_planar_square():
  """A wide planar square should not warn about collinearity."""
  map_points = [
    [0.0, 0.0, 0.0],
    [2.0, 0.0, 0.0],
    [2.0, 2.0, 0.0],
    [0.0, 2.0, 0.0],
  ]
  assessment = assess_map_point_geometry(map_points)
  assert assessment["mapNearlyPlanar"] is True
  assert assessment["warnings"] == []


@pytest.mark.test_name("NEX-T10426")
def test_assess_image_point_coverage_flags_concentrated_cluster():
  """Camera points bunched in a small patch should warn about coverage."""
  cam_points = [
    [300.0, 220.0],
    [310.0, 225.0],
    [305.0, 230.0],
    [315.0, 228.0],
  ]
  assessment = assess_image_point_coverage(cam_points, (640, 480))
  assert assessment["imageCoverage"] < 0.12
  assert any("too little of the frame" in warning
             for warning in assessment["warnings"])


@pytest.mark.test_name("NEX-T10426")
def test_assess_calibration_geometry_flags_shallow_depth_cluster():
  """Points at similar camera depth should warn even with a planar square."""
  map_points = np.array([
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [1.0, 1.0, 0.0],
    [0.0, 1.0, 0.0],
  ], dtype=float)
  cam_points = np.array([
    [100.0, 100.0],
    [500.0, 100.0],
    [500.0, 400.0],
    [100.0, 400.0],
  ], dtype=float)
  # Identity rotation, translation puts the plane at z=5 (uniform depth).
  rvec = np.zeros((3, 1))
  tvec = np.array([[0.0], [0.0], [5.0]])
  geometry = assess_calibration_geometry(
    map_points, cam_points, (640, 480), rvec, tvec)
  assert geometry["depthRangeRatio"] == pytest.approx(1.0)
  assert any("similar depth" in warning
             for warning in geometry["geometryWarnings"])


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize(
  ("payload", "expected"),
  [
    ({}, True),
    ({"rejectOutliers": True}, True),
    ({"rejectOutliers": False}, False),
  ],
)
def test_parse_reject_outliers_accepts_booleans(payload, expected):
  value, error = parse_reject_outliers(payload)
  assert error is None
  assert value is expected


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize(
  "reject_outliers",
  ["false", "true", 0, 1, None],
)
def test_parse_reject_outliers_rejects_non_booleans(reject_outliers):
  value, error = parse_reject_outliers({"rejectOutliers": reject_outliers})
  assert value is None
  assert "boolean" in error


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize(
  ("payload", "expected"),
  [
    ({}, float(RANSAC_REPROJECTION_THRESHOLD_PX)),
    ({"outlierThresholdPx": 10}, 10.0),
    ({"outlierThresholdPx": 2.5}, 2.5),
    # Explicit threshold wins over pixelsPerMeter.
    ({"outlierThresholdPx": 7.0, "pixelsPerMeter": 50.0}, 7.0),
    # At the reference ppm the scaled default matches the base threshold.
    ({"pixelsPerMeter": 100.0}, float(RANSAC_REPROJECTION_THRESHOLD_PX)),
    # Low ppm → stricter threshold (few pixels are a larger world distance).
    ({"pixelsPerMeter": 50.0}, 5.0),
    # High ppm → looser threshold.
    ({"pixelsPerMeter": 200.0}, 20.0),
  ],
)
def test_parse_outlier_threshold_px_accepts_positive_finite(payload, expected):
  value, error = parse_outlier_threshold_px(payload)
  assert error is None
  assert value == pytest.approx(expected)


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize(
  "threshold",
  ["10", True, False, 0, -1, float("nan"), float("inf")],
)
def test_parse_outlier_threshold_px_rejects_invalid_values(threshold):
  value, error = parse_outlier_threshold_px({"outlierThresholdPx": threshold})
  assert value is None
  assert "positive finite" in error


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize(
  "pixels_per_meter",
  ["100", True, False, 0, -1, float("nan"), float("inf")],
)
def test_parse_pixels_per_meter_rejects_invalid_values(pixels_per_meter):
  value, error = parse_pixels_per_meter({"pixelsPerMeter": pixels_per_meter})
  assert value is None
  assert "positive finite" in error


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize(
  ("ppm", "expected"),
  [
    (None, float(RANSAC_REPROJECTION_THRESHOLD_PX)),
    (100.0, 10.0),
    (50.0, 5.0),
    (200.0, 20.0),
    (1.0, float(RANSAC_THRESHOLD_MIN_PX)),
    (10000.0, float(RANSAC_THRESHOLD_MAX_PX)),
  ],
)
def test_scaled_reprojection_threshold_px(ppm, expected):
  assert scaled_reprojection_threshold_px(ppm) == pytest.approx(expected)


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize(
  ("overrides", "error_fragment"),
  [
    ({"rejectOutliers": "false"}, "boolean"),
    ({"outlierThresholdPx": 0}, "positive finite"),
    ({"outlierThresholdPx": "10"}, "positive finite"),
    ({"pixelsPerMeter": 0}, "positive finite"),
    ({"pixelsPerMeter": "100"}, "positive finite"),
  ],
)
def test_calculate_intrinsics_rejects_invalid_outlier_controls(
    overrides, error_fragment):
  """Non-boolean flags and non-positive thresholds are rejected before OpenCV."""
  response = _post_calculate_intrinsics(_calibration_payload(**overrides))
  assert response.status_code == 400
  assert error_fragment in response.data["error"]


@pytest.mark.test_name("NEX-T10426")
def test_calculate_intrinsics_scales_threshold_from_pixels_per_meter():
  """When pixelsPerMeter is set, the response reports the scaled threshold."""
  intrinsic_matrix = np.array([
    [800.0, 0.0, 320.0],
    [0.0, 800.0, 240.0],
    [0.0, 0.0, 1.0],
  ])
  rotation = np.zeros((3, 1))
  translation = np.array([[0.0], [0.0], [5.0]])
  distortion = np.zeros(5)
  payload = _calibration_payload(pixelsPerMeter=50.0)

  with patch(
      "manager.calculate_intrinsics_view.solve_pnpransac",
      return_value=(None, None, None)) as find_inliers, patch(
      "cv2.calibrateCamera",
      return_value=(0.75, intrinsic_matrix, distortion, [rotation], [translation])):
    response = _post_calculate_intrinsics(payload)

  assert response.status_code == 200
  assert response.data["outlierThresholdPx"] == pytest.approx(5.0)
  assert find_inliers.call_args.kwargs["reprojection_threshold_px"] == pytest.approx(
    5.0)


@pytest.mark.test_name("NEX-T10426")
def test_solve_pnpransac_uses_sqpnp_for_coplanar_points():
  """Floor-plan (coplanar) map points use SQPNP RANSAC for outlier rejection."""
  obj_points = np.array([
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [1.0, 1.0, 0.0],
    [0.0, 1.0, 0.0],
    [2.0, 1.0, 0.0],
  ], dtype=np.float32)
  img_points = np.array([
    [320.0, 240.0],
    [480.0, 240.0],
    [480.0, 400.0],
    [320.0, 400.0],
    [640.0, 400.0],
  ], dtype=np.float32)
  intrinsics = np.array([
    [800.0, 0.0, 320.0],
    [0.0, 800.0, 240.0],
    [0.0, 0.0, 1.0],
  ])
  distortion = np.zeros(5)
  mock_rvec = np.zeros((3, 1))
  mock_tvec = np.array([[0.0], [0.0], [5.0]])
  inliers = np.array([[0], [1], [2], [3]], dtype=np.int32)

  with patch(
      "cv2.solvePnPRansac",
      return_value=(True, mock_rvec, mock_tvec, inliers)) as mock_ransac:
    _, _, mask = solve_pnpransac(
      obj_points, img_points, intrinsics, distortion,
      reprojection_threshold_px=RANSAC_REPROJECTION_THRESHOLD_PX)

  mock_ransac.assert_called_once()
  assert mock_ransac.call_args.kwargs["flags"] == cv2.SOLVEPNP_SQPNP
  assert mask is not None
  assert mask.tolist() == [True, True, True, True, False]


@pytest.mark.test_name("NEX-T10426")
def test_solve_pnpransac_uses_ap3p_for_non_coplanar_points():
  """Non-coplanar map points use AP3P RANSAC via the shared helper."""
  obj_points = np.array([
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [0.0, 1.0, 0.0],
    [0.0, 0.0, 1.0],
    [1.0, 1.0, 1.0],
  ], dtype=np.float32)
  img_points = np.array([
    [320.0, 240.0],
    [480.0, 240.0],
    [320.0, 400.0],
    [400.0, 300.0],
    [500.0, 350.0],
  ], dtype=np.float32)
  intrinsics = np.array([
    [800.0, 0.0, 320.0],
    [0.0, 800.0, 240.0],
    [0.0, 0.0, 1.0],
  ])
  distortion = np.zeros(5)
  mock_rvec = np.zeros((3, 1))
  mock_tvec = np.array([[0.0], [0.0], [5.0]])
  inliers = np.array([[0], [1], [2], [3]], dtype=np.int32)

  with patch(
      "cv2.solvePnPRansac",
      return_value=(True, mock_rvec, mock_tvec, inliers)) as mock_ransac:
    _, _, mask = solve_pnpransac(
      obj_points, img_points, intrinsics, distortion,
      reprojection_threshold_px=RANSAC_REPROJECTION_THRESHOLD_PX)

  mock_ransac.assert_called_once()
  assert mock_ransac.call_args.kwargs["flags"] == cv2.SOLVEPNP_AP3P
  assert mask is not None
  assert mask.tolist() == [True, True, True, True, False]


def _projected_non_coplanar_correspondences(num_points):
  """Synthesize a non-coplanar set that calibrateCamera rejects for count < 6."""
  map_points = np.array([
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [0.0, 1.0, 0.0],
    [0.0, 0.0, 1.0],
    [1.0, 1.0, 0.5],
    [0.5, 0.0, 0.8],
  ], dtype=np.float32)[:num_points]
  intrinsics = np.array([
    [800.0, 0.0, 320.0],
    [0.0, 800.0, 240.0],
    [0.0, 0.0, 1.0],
  ], dtype=np.float64)
  distortion = np.zeros(5)
  rvec = np.array([[0.1], [-0.2], [0.05]])
  tvec = np.array([[0.0], [0.0], [5.0]])
  cam_points, _ = cv2.projectPoints(map_points, rvec, tvec, intrinsics, distortion)
  return (map_points, cam_points.reshape(-1, 2).astype(np.float32),
          intrinsics, distortion)


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize("num_points", [4, 5])
def test_needs_pose_only_fit_for_small_non_coplanar_sets(num_points):
  map_points, _, _, _ = _projected_non_coplanar_correspondences(num_points)
  assert needs_pose_only_fit(map_points)
  planar = np.array([
    [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
  ], dtype=np.float32)
  assert not needs_pose_only_fit(planar)


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize("num_points", [4, 5])
def test_calculate_intrinsics_pose_only_path_for_small_non_coplanar_sets(
    num_points):
  """Four/five non-coplanar pairs must succeed without mocking calibrateCamera."""
  map_points, cam_points, intrinsics, distortion = (
    _projected_non_coplanar_correspondences(num_points))
  payload = _calibration_payload(
    mapPoints=map_points.tolist(),
    camPoints=cam_points.tolist(),
    intrinsics=intrinsics.tolist(),
    distortion=distortion.tolist(),
    rejectOutliers=False,
  )

  with patch("cv2.calibrateCamera") as mock_calibrate:
    response = _post_calculate_intrinsics(payload)

  assert response.status_code == 200, response.data
  mock_calibrate.assert_not_called()
  assert response.data["fitPointCount"] == num_points
  assert response.data["rejectionApplied"] is False
  assert len(response.data["perPointErrors"]) == num_points
  assert response.data["rmsError"] < 1.0
  np.testing.assert_allclose(response.data["mtx"], intrinsics, atol=1e-6)
  dist = np.asarray(response.data["dist"])
  assert dist.ndim == 2 and dist.shape[1] == 1
  np.testing.assert_allclose(dist.ravel(), distortion.ravel(), atol=1e-6)


@pytest.mark.test_name("NEX-T10426")
def test_fit_pose_fixed_intrinsics_uses_sqpnp_for_non_coplanar():
  map_points, cam_points, intrinsics, distortion = (
    _projected_non_coplanar_correspondences(4))
  with patch("cv2.solvePnP", wraps=cv2.solvePnP) as spy:
    rms, mtx, dist, rvecs, tvecs = fit_pose_fixed_intrinsics(
      map_points, cam_points, intrinsics, distortion)
  assert spy.call_args.kwargs["flags"] == cv2.SOLVEPNP_SQPNP
  assert rms < 1.0
  assert len(rvecs) == 1 and len(tvecs) == 1
  np.testing.assert_allclose(mtx, intrinsics)
  assert dist.shape == (len(distortion), 1)
  np.testing.assert_allclose(dist.ravel(), distortion)


@pytest.mark.test_name("NEX-T10426")
def test_as_distortion_column_normalizes_shapes():
  assert as_distortion_column([1.0, 2.0, 3.0]).shape == (3, 1)
  assert as_distortion_column(np.array([[1.0, 2.0]])).shape == (2, 1)


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize(
  ("map_points", "cam_points", "expected_error"),
  [
    ([[0, 0], [1, 0], [1, 1], [0, 1]],
     [[0, 0], [1, 0], [1, 1]],
     "same length"),
    ([[0, 0, 0, 0], [1, 0, 0, 0], [1, 1, 0, 0], [0, 1, 0, 0]],
     [[0, 0], [1, 0], [1, 1], [0, 1]],
     "2D or 3D"),
    ([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
     [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
     "2D image"),
    ([[0, 0, float("nan")], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
     [[0, 0], [1, 0], [1, 1], [0, 1]],
     "finite"),
  ],
)
def test_validate_correspondence_arrays_rejects_bad_input(
    map_points, cam_points, expected_error):
  obj, img, error = validate_correspondence_arrays(map_points, cam_points)
  assert obj is None and img is None
  assert expected_error in error


@pytest.mark.test_name("NEX-T10426")
def test_validate_correspondence_arrays_pads_2d_map_points():
  obj, img, error = validate_correspondence_arrays(
    [[0, 0], [1, 0], [1, 1], [0, 1]],
    [[10, 10], [20, 10], [20, 20], [10, 20]])
  assert error is None
  assert obj.shape == (4, 3)
  assert img.shape == (4, 2)
  np.testing.assert_array_equal(obj[:, 2], 0)


@pytest.mark.test_name("NEX-T10426")
def test_calculate_intrinsics_rejects_bad_point_dimensions():
  # Keep count matched with default camPoints so the length gate does not fire first.
  payload = _calibration_payload(
    mapPoints=[
      [0, 0, 0, 0], [1, 0, 0, 0], [1, 1, 0, 0], [0, 1, 0, 0], [2, 1, 0, 0],
    ],
  )
  response = _post_calculate_intrinsics(payload)
  assert response.status_code == 400
  assert "mapPoints" in response.data["error"]


@pytest.mark.test_name("NEX-T10426")
@pytest.mark.parametrize(
  ("overrides", "expected_error"),
  [
    ({"intrinsics": [[800.0, 0.0], [0.0, 800.0]]}, "3x3"),
    ({"intrinsics": [
      [-1.0, 0.0, 320.0], [0.0, 800.0, 240.0], [0.0, 0.0, 1.0],
    ]}, "fx and fy"),
    ({"distortion": [0.0, 0.0, 0.0]}, "4, 5, 8, 12, or 14"),
    ({"imageSize": [640]}, "imageSize"),
    ({"imageSize": [0, 480]}, "positive"),
    ({"imageSize": [MAX_IMAGE_DIMENSION_PX + 1, 480]},
     str(MAX_IMAGE_DIMENSION_PX)),
  ],
)
def test_calculate_intrinsics_rejects_invalid_camera_model(overrides, expected_error):
  response = _post_calculate_intrinsics(_calibration_payload(**overrides))
  assert response.status_code == 400
  assert expected_error in response.data["error"]


@pytest.mark.test_name("NEX-T10426")
def test_calculate_intrinsics_rejects_too_many_correspondences():
  point_count = MAX_CALIBRATION_CORRESPONDENCES + 1
  payload = _calibration_payload(
    mapPoints=[[float(i), 0.0, 0.0] for i in range(point_count)],
    camPoints=[[float(i), 0.0] for i in range(point_count)],
  )
  response = _post_calculate_intrinsics(payload)
  assert response.status_code == 400
  assert "Invalid number of points" in response.data["error"]


@pytest.mark.test_name("NEX-T10426")
def test_validate_intrinsics_matrix_accepts_valid_3x3():
  matrix, error = validate_intrinsics_matrix([
    [800.0, 0.0, 320.0], [0.0, 800.0, 240.0], [0.0, 0.0, 1.0],
  ])
  assert error is None
  assert matrix.shape == (3, 3)


@pytest.mark.test_name("NEX-T10426")
def test_validate_distortion_coefficients_coerces_nan_to_zero():
  coeffs, error = validate_distortion_coefficients(
    [float("nan"), 0.1, 0.0, 0.0, 0.0])
  assert error is None
  assert coeffs.shape == (5, 1)
  assert coeffs[0, 0] == 0.0
  assert coeffs[1, 0] == pytest.approx(0.1)


@pytest.mark.test_name("NEX-T10426")
def test_validate_distortion_coefficients_rejects_infinity():
  # Inf cannot round-trip through JSON request bodies; exercise the helper.
  coeffs, error = validate_distortion_coefficients(
    [0.0, 0.0, float("inf"), 0.0, 0.0])
  assert coeffs is None
  assert "finite" in error


@pytest.mark.test_name("NEX-T10426")
def test_validate_image_size_accepts_positive_pair():
  size, error = validate_image_size([1920, 1080])
  assert error is None
  assert size == (1920, 1080)
