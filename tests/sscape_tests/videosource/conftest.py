#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
