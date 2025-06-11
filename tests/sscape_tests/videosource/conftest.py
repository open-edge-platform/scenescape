#!/usr/bin/env python3


# Copyright (C) 2021-2024 Intel Corporation
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

from scene_common.transform import CameraIntrinsics
from percebro.videosource import VideoSource
import tests.common_test_utils as common

VIDEO_PATH = "sample_data/apriltag-cam1.mp4"

TEST_NAME = "NEX-T10453"
def pytest_sessionstart():
  """! Executes at the beginning of the session. """

  print(f"Executing: {TEST_NAME}")

  return

def pytest_sessionfinish(exitstatus):
  """! Executes at the end of the session. """

  common.record_test_result(TEST_NAME, exitstatus)
  return

@pytest.fixture(scope='module')
def videoSourceObj():
  """! Creates a VideoSource object for this module """

  intrinsics = [1271, 1271, 320, 240]
  return VideoSource(VIDEO_PATH, intrinsics, None)


@pytest.fixture(scope='module')
def camIntrinsics():
  """! Creates a CameraIntrinsics object for this module """

  intrinsics = CameraIntrinsics([1271, 1271, 320, 240])
  return intrinsics

@pytest.fixture(scope='module')
def getFrame(videoSourceObj):
  """! Creates a getFrame object for this module

  @param    videoSourceObj     param fixture which contains camera object
  """

  while True:
    pytest.frame = videoSourceObj.capture()
    if pytest.frame is not None:
      break

  return pytest.frame
