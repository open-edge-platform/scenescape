# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import pytest
from scene_common.transform import CameraIntrinsics

@pytest.mark.parametrize("camIntrinsics, distortion, resolution",
                         [(80, None, [1280, 720]),
                           ([ 80], None, [1280, 720]),
                           ([45, 30], None, [1280,720])])
def test_init(camIntrinsics, distortion, resolution):
  obj = CameraIntrinsics(camIntrinsics, distortion, resolution)
  assert obj is not None
  return

@pytest.mark.parametrize("camIntrinsics, distortion, resolution",
                         [(None, None, None),
                          (None, None, [1280, 720]),
                          ([], None, None)])
def test_bad_init(camIntrinsics, distortion, resolution):
  try:
    CameraIntrinsics(camIntrinsics, distortion, resolution)
  except ValueError as e:
    assert e.args[0] == "Invalid intrinsics"
    return
  except Exception as e:
    pytest.fail(f"Unexpected exception type: {type(e)} - {e}")
  return

def test_computeIntrinsicsFromFoV():
  fov = 80
  obj = CameraIntrinsics(fov, None, [1280, 720])
  expected_intrinsics = [875, 875, 640, 360]
  intrin_mat = obj.computeIntrinsicsFromFoV([1280, 720], fov)
  assert expected_intrinsics == [int(intrin_mat[0][0]), int(intrin_mat[1, 1]), intrin_mat[0, 2], intrin_mat[1, 2]]

  fov = [72.35, 44.72]
  obj = CameraIntrinsics(fov, None, [1280, 720])
  expected_intrinsics = [1312, 1312, 960, 540]
  intrin_mat = obj.computeIntrinsicsFromFoV([1920, 1080], fov)
  assert expected_intrinsics == [int(intrin_mat[0][0]), int(intrin_mat[1, 1]), intrin_mat[0, 2], intrin_mat[1, 2]]

  return
