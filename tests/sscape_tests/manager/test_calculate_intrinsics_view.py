# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from manager.calculate_intrinsics_view import CalculateCameraIntrinsics


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