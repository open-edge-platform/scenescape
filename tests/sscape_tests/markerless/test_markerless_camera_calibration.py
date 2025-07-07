#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from types import NoneType

import open3d as o3d
import numpy as np
import pytest

from markerless_camera_calibration import CameraCalibrationMonocularPoseEstimate, getPoseMatrix
from scene_common.mesh_util import extractMeshFromGLB, extractMeshFromImage
from scene_common.transform import convertToTransformMatrix

def test_extractMeshFromGLB(getGlbFile):
  """! Tests loading mesh from glb file. """
  mesh, _ = extractMeshFromGLB(getGlbFile)
  assert isinstance(mesh,o3d.t.geometry.TriangleMesh)

def test_extractMeshFromImage(getImageFile):
  """! Tests loading mesh from image file. """
  assert isinstance(extractMeshFromImage(getImageFile),o3d.t.geometry.TriangleMesh)

def test_camCalibObject(createCamCalibObject):
  """! Tests Creation of a CameraCalibrationMonocularPoseEstimate object. """
  assert isinstance(createCamCalibObject, CameraCalibrationMonocularPoseEstimate)

def test_decodeImage(createCamCalibObject ,convertImageToBase64,
                     convertBadImageToBase64):
  """! Tests if the images being sent via mqtt is decoded right. """
  cam_obj = createCamCalibObject
  assert isinstance(cam_obj.decodeImage(convertImageToBase64), np.ndarray)
  assert isinstance(cam_obj.decodeImage(convertBadImageToBase64), NoneType)

def test_getPoseMatrix(createSceneObject, expectedPoseMat):
  """! Tests if basic Pose Matrix generated is correct. """
  scene_obj = createSceneObject
  pose_mat = getPoseMatrix(scene_obj)
  assert pose_mat.shape == (4, 4)
  assert np.allclose(expectedPoseMat, pose_mat)

def test_convertYUpToYDown(createCamCalibObject, createSceneObject, rotAndTrans,
                           expectedMatForYupToYDown):
  """! Tests upon rotation and translation, do we get the right matrix in
       Scenescape co-ordinate system. """
  rot, trans = rotAndTrans
  cam_obj = createCamCalibObject
  cam_obj.scene_pose_mat = getPoseMatrix(createSceneObject)
  val = createCamCalibObject.convertYUpToYDown(rot, trans)
  assert val.shape == (4, 4)
  assert np.allclose(expectedMatForYupToYDown, val)

def test_convertToTransformMatrix(createCamCalibObject, rotAndTrans,
                                  expectedMatForTransformMatrix):
  """! Test markerless.convertToTransformMatrix returns 4x4 shaped matrix. """
  rot, trans = rotAndTrans
  val = convertToTransformMatrix(createCamCalibObject.scene_pose_mat, rot, trans)
  assert val.shape == (4, 4)
  assert np.allclose(expectedMatForTransformMatrix, val)

def test_getMarkerlessConfig(createCamCalibObject, createSceneObject, hlocConfig):
  """! Test to check if hloc config generated is right. """
  cfg = createCamCalibObject.generateMarkerlessConfig(createSceneObject)
  assert isinstance(cfg, dict)
  assert cfg['hloc']['global_feature'] == "netvlad"
  assert cfg['hloc']['min_matches'] == 20
  assert len(cfg['hloc']) == 6
  assert cfg['hloc'] == hlocConfig

def test_extractMeshFromGLBBad(getBadGlbFile, getImageFile):
  """! Tests loading bad glb file. """
  with pytest.raises(ValueError) as valueerror:
    extractMeshFromGLB(getBadGlbFile)
  assert str(valueerror.value) == "Loaded mesh is empty or invalid."

  with pytest.raises(FileNotFoundError) as filenotfounderror:
    extractMeshFromGLB(getImageFile[0])
  assert str(filenotfounderror.value) == "Glb file not found."
