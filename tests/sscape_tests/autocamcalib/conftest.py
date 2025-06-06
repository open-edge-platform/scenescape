#!/usr/bin/env python3

# Copyright (C) 2023-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import numpy as np
import pytest

from autocalibration.atag_camera_calibration import CameraCalibrationApriltag
import tests.common_test_utils as common

TEST_NAME = "NEX-T10459"
scene_map = "sample_data/atag-calib-demo-map.png"

def pytest_sessionstart():
  """! Executes at the beginning of the session. """

  print(f"Executing: {TEST_NAME}")
  return

def pytest_sessionfinish(exitstatus):
  """! Executes at the end of the session. """

  common.record_test_result(TEST_NAME, exitstatus)
  return

@pytest.fixture(scope="module")
def relative_tolerance():
  """! Relative tolerance used during comparison of arrays. """
  return 1e-7

@pytest.fixture(scope="module")
def result_data():
  """! Expected result data for given base test map with actual 3d
    coordinates of 5 apriltags in the test scene. """
  return {'0': [2.438122272491455, 3.192995548248291, 2.384185791015625e-07],
          '1': [1.856532096862793, 0.5593911409378052, 0.0],
          '3': [3.5689048767089844, 1.2029988765716553, 0.0],
          '4': [0.9765028357505798, 2.369309425354004, 1.1920928955078125e-07],
          '2': [3.191632032394409, 2.289494037628174, 1.1920928955078125e-07]}

@pytest.fixture(scope="module")
def intrinsics():
  """! Intrinsics for a test camera. """
  return np.array([[500., 0., 320.], [0., 500., 240.], [0., 0., 1.]])

@pytest.fixture(scope="module")
def pose():
  """! Expected Pose from the calibration. """
  return [[9.99999812e-01, -3.30341658e-04, -5.16601898e-04, 2.00181944e+00],
          [-1.34154251e-04, -9.39934076e-01, 3.41355995e-01, 3.02465995e-01],
          [-5.98335833e-04, -3.41355862e-01, -9.39933943e-01, 3.00006334e+00],
          [0.00000000e+00, 0.00000000e+00, 0.00000000e+00, 1.00000000e+00]]

@pytest.fixture(scope="module")
def camcalibration():
  """! returns the camcalibration test object. """
  scale = 268.0
  name = "Test"
  return CameraCalibrationApriltag(scene_map, scale, name)

@pytest.fixture(scope="module")
def apriltags2d():
  """! Test values for apriltag centers present in test map. """
  return {'1': [295.3290322, 374.59052971], '2': [490.21324187, 119.2943957],
          '3': [570.92463555, 268.3864069], '4': [174.86040057, 109.76156221]}

@pytest.fixture(scope="module")
def actual_centers_2d():
  """! Test values for apriltag centers present in test map. """
  return {0: [653.39967769, 162.40884747],
          1: [497.6252461, 868.08079366],
          2: [855.39611243, 404.40110578],
          3: [956.48534243, 695.53466689],
          4: [261.74472792, 383.03922438]}

@pytest.fixture(scope="module")
def frustum():
  """! Test values for camera frustum. """
  return [[0, 0, 0],
          [0.32, 0.48, 1],
          [0.32, -0.48, 1],
          [-0.64, -0.48, 1],
          [-0.64, 0.48, 1]]
