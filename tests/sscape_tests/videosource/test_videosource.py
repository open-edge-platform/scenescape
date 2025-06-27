# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import pytest
import numpy as np
import cv2
from percebro.videosource import VideoSource

@pytest.mark.parametrize("videoPath, distortion",
                         [("sample_data/apriltag-cam1.mp4", np.zeros(4)),
                          ("sample_data/Demo.png", np.zeros(4)),
                          ("sample_data/Demo.png", [0, 0, 0, 0])])
def test_init(camIntrinsics, videoPath, distortion):
  """! Verifies the instance of the VideoSource class

  @param    camIntrinsics     param fixture which contains CameraIntrinsics object
  @param    videoPath         path to video
  @param    distortion        list of values to be used for camera calibration
  """
  obj = VideoSource(videoPath, camIntrinsics, distortion)
  assert obj is not None

  return

@pytest.mark.parametrize("intrinsics, videoPath, distortion",
                         [([1271, 1271, 320, 240], "0", "Bad distortion"),
                          ([1271, 1271, 320, 240], "sample_data/Demo.png", np.zeros(3))])
def test_bad_init(intrinsics, videoPath, distortion):
  """! Verify ValueError thrown when initializing with bad params

  @param    intrinsics        list of values to be used as camera intrinsics
  @param    videoPath         path to video
  @param    distortion        list of values to be used for camera calibration
  """
  with pytest.raises((ValueError, TypeError)):
    VideoSource(videoPath, intrinsics, distortion)

  return

def test_setStartPosition(videoSourceObj):
  """! Verifies the output of 'setStartPosition' function

  @param    videoSourceObj     param fixture which contains camera object
  """
  videoSourceObj.setStartPosition(0)
  expected_startPosition = 0

  assert videoSourceObj.startPosition == expected_startPosition
  assert videoSourceObj.cam.get(cv2.CAP_PROP_POS_MSEC) == 0.0

  return

def test_setEndPosition(videoSourceObj):
  """! Verifies the output of 'setEndPosition' function

  @param    videoSourceObj     param fixture which contains camera object
  """
  videoSourceObj.setEndPosition(117)
  expectedEndPosition = 117000

  assert videoSourceObj.endPosition == expectedEndPosition

  return

@pytest.mark.parametrize("isFile, aspect, unwarp, cam", \
                        [(True, False, False, False), (False, \
                        True, True, True)])
def test_capture(getFrame, videoSourceObj, isFile, aspect, unwarp, cam):
  """! Verifies the output of 'capture' function

  @param    getFrame      param fixture which contains video frame
  @param    videoSourceObj     param fixture which contains camera object
  @param    isFile        videoSourceObj attribute to set for test if true/false
  @param    aspect        videoSourceObj attribute to set for test if true/false
  @param    unwarp        videoSourceObj attribute to set for test if true/false
  @param    cam           videoSourceObj attribute to set for test if true/false
  """

  if not isFile and aspect and unwarp and cam:
    videoSourceObj.isFile = False
    videoSourceObj.aspect = 10
    videoSourceObj.unwarp = True
    videoSourceObj.cam = cv2.VideoCapture(-1)

  _ = videoSourceObj.capture()

  assert pytest.frame is not None

  return

def test_setResolution(videoSourceObj):
  """! Verifies the output of 'setResolution' function

  @param    videoSourceObj     param fixture which contains camera object
  """
  videoSourceObj.unwarp = False
  expectedSize = (640, 480)
  videoSourceObj.setResolution(expectedSize)
  frameWidth, frameHeight = videoSourceObj.getResolution()
  assert frameWidth == expectedSize[0]
  assert frameHeight == expectedSize[1]

  return

@pytest.mark.parametrize("videoPath, distortion",
                         [("sample_data/apriltag-cam1.mp4", np.zeros(4))])
def test_getResolution(camIntrinsics, videoPath, distortion):
  """! Verifies the output of 'getResolution' function

  """
  obj = VideoSource(videoPath, camIntrinsics, distortion)
  expectedSize = (640, 480)
  frameWidth, frameHeight = obj.getResolution()

  assert frameWidth == float(expectedSize[0])
  assert frameHeight == float(expectedSize[1])

  return
