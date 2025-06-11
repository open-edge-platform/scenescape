#!/usr/bin/env python3


# Copyright (C) 2022-2024 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

import pytest
import numpy as np

from percebro.realsense import RSImage, RSCamera
from unittest.mock import MagicMock, patch
import tests.common_test_utils as common

TEST_NAME = "NEX-T10455"

################################################################
# Methods
################################################################
def pytest_sessionstart():
  """! Executes at the beginning of the session. """
  print("Executing: " + TEST_NAME)
  return

def pytest_sessionfinish(exitstatus):
  """! Executes at the end of the session. """

  common.record_test_result(TEST_NAME, exitstatus)
  return

realsensePipeline = "percebro.realsense.rs.pipeline"
realsenseAlign = "percebro.realsense.rs.align"
def start_rs_cam(cam):
  """! Executes the method start() on camera object RSCamera """
  with patch(realsensePipeline, return_value=MagicMock()), \
       patch(realsenseAlign, return_value=MagicMock()):
    cam.start()
  return

################################################################
# Fixtures
################################################################
@pytest.fixture(scope="module")
def rs_image():
  """! Returns a RSImage object. """
  return RSImage(MagicMock())

@pytest.fixture(scope="module")
def rs_cam(test_params):
  """! Returns a RSCamera object. """
  with patch(realsensePipeline, return_value=MagicMock()), \
       patch(realsenseAlign, return_value=MagicMock()):
    rs_cam = RSCamera(test_params.cam_serial_1)
  return rs_cam

@pytest.fixture(scope="module")
def rs_cam_nopipe(test_params):
  """! Returns a RSCamera object with pipeline set to None. """
  with patch(realsensePipeline, return_value=MagicMock()), \
       patch(realsenseAlign, return_value=MagicMock()):
    rs_cam = RSCamera(test_params.cam_serial_1)
  rs_cam.pipeline = None
  return rs_cam

@pytest.fixture(scope="module")
def cam_intrinsics():
  """! Returns a camera intrinsics object with fixed parameters. """
  return CamIntrinsics(0.01, 0.01, 0.2, 0.1)

@pytest.fixture(scope="module")
def test_params():
  """! Returns predefined test parameters object. """
  return TestParams()

################################################################
# Classes
################################################################
class TestParams:
  """! Data structure for predefined test parameters. """

  def __init__(self):
    self.cam_serial_1 = "1234"
    self.cam_serial_2 = "123456789"
    self.cam_serial_3 = "video1234"
    self.img_height = 1080
    self.img_width = 1920
    return

class CamIntrinsics:
  """! Test class defining the camera intrinsics for a test. """

  def __init__(self, fx, fy, ppx, ppy):
    """!
      Initializing CamIntrinsics object.
      fx: FLOAT focal length along the x-dimension.
      fy: FLOAT focal length along the y-dimension.
      ppx: FLOAT sensor size in the x-dimension.
      ppy: FLOAT sensor size in the y-dimension.
    """
    self.fx = fx
    self.fy = fy
    self.ppx = ppx
    self.ppy = ppy
    return

  def get_distortion_matrix(self):
    """! Returns a numpy array representing camera distortion. """
    return np.array([0,0,0,0,0], dtype=np.float32)

  def get_intrinsics_matrix(self):
    """! Returns a numpy array representing camera intrinsics. """
    return np.array([ [self.fx, 0, self.ppx], [0, self.fy, self.ppy], [ 0, 0, 1] ])

class Output_v4l2_ctrl:
  """! Returns STDOUT for CMD v4l2_ctrl. """
  def __init__(self, stdout):
    self.stdout = stdout
    return

class FakeCTX:
  """! Fakes a realsense context. """
  def __init__(self, devices):
    self._devices = devices
    return

  def query_devices(self):
    return self._devices

  @property
  def devices(self):
    return self._devices

class FakeCam:
  """! Fakes a realsense camera. """
  def __init__(self, info):
    self._info = info
    return

  def get_info(self, serial_num):
    return self._info

class FakeStreamProfile:
  """! Fakes a stream profile. """
  def __init__(self, cam_intrinsics):
    self.intrinsics = cam_intrinsics
    return

  def get_intrinsics(self):
    return self.intrinsics

class FakeStream:
  """! Fakes a stream. """
  def __init__(self, type, cam_intrinsics):
    self.type = type
    self.profile = FakeStreamProfile(cam_intrinsics)
    return

  def stream_type(self):
    return self.type

  def as_video_stream_profile(self):
    return self.profile

class FakeColorFrame:
  """! Fakes a color frame. """
  def __init__(self, height, width):
    self.height = height
    self.width = width
    return

  def get_height(self):
    return self.height

  def get_width(self):
    return self.width

  def get_data(self):
    return np.zeros(1)
