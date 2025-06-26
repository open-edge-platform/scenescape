#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import cv2
import base64

import numpy as np
import pytest

from autocalibration.auto_camera_calibration_model import CalibrationScene
from autocalibration.markerless_camera_calibration import CameraCalibrationMonocularPoseEstimate
from scene_common.options import MARKERLESS

import tests.common_test_utils as common

TEST_NAME = "NEX-T10497"
SCENE_MAP = "sample_data/atag-calib-demo-map.png"
SCENE_ID = "f1b9b1b0-1b1b-1b1b-1b1b-1b1b1b1b1b1b"
DATASET_DIR = os.path.abspath(os.path.join(__file__ ,"../test_markerless/test_dataset"))
OUTPUT_DIR = os.path.abspath(os.path.join(__file__ ,"../test_markerless/output_dir"))
TEST_MEDIA_PATH = os.path.abspath(os.path.join(__file__ ,"../../../ui/test_media/"))
GLB_PATH = TEST_MEDIA_PATH + "/box.glb"
BAD_GLB_PATH = TEST_MEDIA_PATH + "/box_invalid.glb"

def pytest_sessionstart():
  """! Executes at the beginning of the session. """

  print(f"Executing: {TEST_NAME}")
  return

def pytest_sessionfinish(exitstatus):
  """! Executes at the end of the session. """

  common.record_test_result(TEST_NAME, exitstatus)
  return

def sceneData():
  """! Returns a dictionary containing scene data. """
  return {'uid': SCENE_ID,
          'name': 'test',
          'map': SCENE_MAP,
          'scale': 268.0,
          'camera_calibration': MARKERLESS}

@pytest.fixture(scope="module")
def createSceneObject():
  """! Creates a Scene Object named test. """
  scene = CalibrationScene.deserialize(sceneData())
  return scene

@pytest.fixture(scope="module")
def createCamCalibObject():
  """! Creates a CameraCalibrationMonocularPoseEstimate object named
       based on scene object. """
  sceneobj = CalibrationScene.deserialize(sceneData())
  dataset_dir = DATASET_DIR
  output_dir = OUTPUT_DIR
  camCalibobj = CameraCalibrationMonocularPoseEstimate(sceneobj, dataset_dir,
                                                       output_dir)
  return camCalibobj

@pytest.fixture(scope="module")
def getGlbFile():
  """! Returns a local glb file. """
  return GLB_PATH

@pytest.fixture(scope="module")
def getBadGlbFile():
  """! Returns a bad local glb file. """
  return BAD_GLB_PATH

@pytest.fixture(scope="module")
def getImageFile():
  """! Returns map image along with it's scale in a list format. """
  map_info = [SCENE_MAP, 268.0]
  return map_info

@pytest.fixture(scope='module')
def rotAndTrans():
  """! Returns a Rotation and Translation values. """
  rotation = [-0.5484958212397865,
              0.4647060363091052,
              -0.46525622312670134,
              0.5164661467533471]
  translation = [-0.6064744486244756,
                 -0.03662228698077811,
                 -0.07810122057350662]
  return rotation, translation

@pytest.fixture(scope="module")
def convertImageToBase64():
  """! Converts a base64 image to cv2/numpy format. """
  img_path = SCENE_MAP
  frame = cv2.imread(img_path)
  _, jpeg = cv2.imencode(".jpg", frame)
  jpeg = base64.b64encode(jpeg).decode('utf-8')
  return jpeg

@pytest.fixture(scope="module")
def convertBadImageToBase64():
  """! Converts a base64 image to cv2/numpy format. """
  jpeg = base64.b64encode(bytes('This is a bad string to test.', 'utf-8'))
  return jpeg

@pytest.fixture(scope="module")
def expectedMatForYupToYDown():
  """! Returns an expected matrix for YupToYDown computation. """
  return np.asarray([[ 0.13516989, 0.02920046, -0.99039206, -0.60647445],
                     [-0.99035682, 0.03462204, -0.1341443, -0.03662229],
                     [ 0.03037232,  0.9989738, 0.03359873, -0.07810122],
                     [ 0.0, 0.0, 0.0, 1.0]])

@pytest.fixture(scope="module")
def expectedPoseMat():
  """! Returns an identity pose matrix"""
  return np.asarray([[1.0,0.0,0.0,0.0],
                     [0.0,1.0,0.0,0.0],
                     [0.0,0.0,1.0,0.0],
                     [0.0,0.0,0.0,1.0]])

@pytest.fixture(scope="module")
def expectedMatForTransformMatrix():
  """! Returns an pose matrix after rotation and translations are applied."""
  return np.asarray([[ 0.13516989,-0.02920046, 0.99039206,-0.60647445],
                     [-0.99035682,-0.03462204, 0.1341443, -0.03662229],
                     [ 0.03037232,-0.9989738, -0.03359873, -0.07810122],
                     [ 0.0, 0.0, 0.0, 1.0 ]])

@pytest.fixture(scope='module')
def hlocConfig():
  """! Returns a sample HLOC object. """
  return {'num_loc': 50, 'global_feature': 'netvlad', 'local_feature': {'sift': {}},
          'matcher': {'NN-ratio': {}}, 'min_matches': 20, 'inlier_threshold': 0.5}
