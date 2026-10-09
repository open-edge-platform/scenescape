# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from manager.calculate_intrinsics_view import (
  CalculateCameraIntrinsics,
  assess_calibration_geometry,
  assess_image_point_coverage,
  assess_map_point_geometry,
)


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
    "intrinsics": intrinsic_matrix.tolist(),
    "distortion": distortion.tolist(),
    "imageSize": [640, 480],
    "rejectOutliers": reject_outliers,
  }
  request = APIRequestFactory().post(
    "/api/v1/calculateintrinsics", payload, format="json")
  force_authenticate(
    request,
    user=SimpleNamespace(is_authenticated=True, is_superuser=True),
  )

  with patch(
      "manager.calculate_intrinsics_view.find_inlier_mask",
      return_value=inlier_mask), patch(
      "cv2.calibrateCamera",
      return_value=(0.75, intrinsic_matrix, distortion, [rotation], [translation])):
    response = CalculateCameraIntrinsics.as_view()(request)

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
