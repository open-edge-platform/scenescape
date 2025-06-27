# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import math

import cv2
import numpy as np

from conftest import scene_map

def verify_findApriltagsInFrame(camcalibration, src_image, intrinsics, \
                                  actual_centers_2d, relative_tolerance):
  """! Test for function that computes apriltag centers in an image.
  @param    camcalibration       controller test class object.
  @param    src_image            input image to compute apriltags.
  @param    intrinsics           camera intrinsics.
  @param    actual_centers_2d    centers of the detected april tags
  @param    relative_tolerance   measure of tolerated closeness

  @return None
  """
  img = cv2.imread(src_image)
  apriltag2d_centers = camcalibration.findApriltagsInFrame(
      img, store=True, intrinsics=intrinsics)

  assert len(apriltag2d_centers) == 5
  for tag_id, tag in apriltag2d_centers.items():
    for r, e in zip(tag, actual_centers_2d[int(tag_id)]):
      assert math.isclose(r, e, rel_tol=relative_tolerance)
  return

def verify_getCameraPoseInScene(camcalibration, apriltags2d, result_data, \
                               pose, intrinsics, relative_tolerance):
  """! Test for function that computes real world pose based on apriltag centers.
  @param    camcalibration       controller test class object.
  @param    apriltags2d          input image to compute apriltags.
  @param    result_data          ground truth values of apriltags.
  @param    pose                 camera pose.
  @param    intrinsics           camera intrinsics.
  @param    relative_tolerance   measure of tolerated closeness

  @return None
  """
  camcalibration.intrinsic_matrix_2d = intrinsics
  camcalibration.result_data_3d = result_data
  camcalibration.apriltags_2d_data = apriltags2d
  response = camcalibration.getCameraPoseInScene()
  assert len(response) == len(pose)
  for r, e in zip(response, pose):
    assert len(r) == len(e)
    for i, j in zip(r, e):
      assert math.isclose(i, j, rel_tol=relative_tolerance)
  return

def verify_getCameraFrustum(camcalibration, frustum, relative_tolerance):
  """! Test for function that computes real world pose based on apriltag centers.
  @param    camcalibration       controller test class object.
  @param    frustum              camera frustum
  @param    relative_tolerance   measure of tolerated closeness

  @return None
  """
  result_2d = camcalibration.getCameraFrustum()
  assert len(result_2d) == len(frustum)
  for r, e in zip(result_2d, frustum):
    assert len(r) == len(e)
    for i, j in zip(r, e):
      assert math.isclose(i, j, rel_tol=relative_tolerance)
  return

def test_cameraCalibrationApriltag(camcalibration, apriltags2d, result_data, \
                                   pose, intrinsics, actual_centers_2d, frustum, relative_tolerance):
  verify_findApriltagsInFrame(camcalibration, scene_map, intrinsics, \
                                actual_centers_2d, relative_tolerance)
  verify_getCameraPoseInScene(camcalibration, apriltags2d, result_data, \
                             pose, intrinsics, relative_tolerance)
  verify_getCameraFrustum(camcalibration, frustum, relative_tolerance)

  return
