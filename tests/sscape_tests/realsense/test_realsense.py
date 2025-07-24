#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import conftest
import numpy as np
import pyrealsense2
import pytest

from percebro import realsense
from percebro.realsense import RSImage, RSCamera
from unittest.mock import MagicMock, patch

def test_init_RSImage():
  """! Test the initialization of the realsense.RSImage class. """

  rs_image = RSImage(MagicMock())
  assert isinstance(rs_image, RSImage)
  return

def test_shape_RSImage(test_params):
  """! Test realsense.RSImage returns its shape. """

  with patch("percebro.realsense.rs.composite_frame.get_color_frame", \
            return_value=conftest.FakeColorFrame(test_params.img_height, test_params.img_width)):
    rs_image = RSImage(pyrealsense2.composite_frame(pyrealsense2.frame()))
    shape = rs_image.shape
    assert (shape[0] == test_params.img_height)
    assert (shape[1] == test_params.img_width)
  return

def test_color_RSImage(rs_image, test_params):
  """! Test realsense.RSImage returns a color frame. """

  with patch("percebro.realsense.rs.composite_frame.get_color_frame", \
            return_value=conftest.FakeColorFrame(test_params.img_height, test_params.img_width)):
    color_frame = rs_image.color
  assert isinstance(color_frame, np.ndarray)
  return

def test_depth_RSImage(rs_image):
  """! Test realsense.RSImage returns a depth frame. """

  with patch("percebro.realsense.rs.composite_frame.get_depth_frame", \
            return_value=MagicMock()):
    depth_frame = rs_image.depth
  assert depth_frame is not None
  return

def test_init_RSCamera(test_params):
  """! Test the initialization of the realsense.RSCamera class. """

  with patch("percebro.realsense.rs.pipeline", return_value=MagicMock()), \
       patch("percebro.realsense.rs.align", return_value=MagicMock()):
    rs_cam = RSCamera(test_params.cam_serial_1)
  assert rs_cam is not None
  assert rs_cam.serial == test_params.cam_serial_1
  assert rs_cam.syncMode == 1
  return

def test_set_RSCamera(rs_cam):
  """! Test realsense.RSCamera set method. """

  val = rs_cam.set("key", 0)
  assert val is None
  return

def test_read_RSCamera(rs_cam):
  """! Test realsense.RSCamera read method. """

  val, img = rs_cam.read()
  assert val == 1
  assert isinstance(img, RSImage)
  return

def test_captureFrame_RSCamera(rs_cam, rs_cam_nopipe):
  """! Test realsense.RSCamera captureFrame method. """

  val1 = rs_cam.captureFrame()
  with patch("percebro.realsense.rs.pipeline", return_value=MagicMock()), \
       patch("percebro.realsense.rs.align", return_value=MagicMock()):
    val2 = rs_cam_nopipe.captureFrame()

  assert val1.called is False
  assert val1.method_calls == []
  assert val1.mock_calls == []

  assert val2.called is False
  assert val2.method_calls == []
  assert val2.mock_calls == []
  return

def test_captureDepthImage_RSCamera(rs_cam):
  """! Test realsense.RSCamera captureDepthImage method. """

  val = rs_cam.captureDepthImage()
  assert val is not None
  return

def test_captureRGBImage_RSCamera(rs_cam):
  """! Test realsense.RSCamera captureRGBImage method. """

  val = rs_cam.captureRGBImage()
  assert isinstance(val, np.ndarray)
  return

def test_enableDepth(rs_cam, rs_cam_nopipe, test_params):
  """! Test realsense.RSCamera enableDepth method. """

  assert rs_cam.enableDepth(test_params.img_width, test_params.img_height)
  conftest.start_rs_cam(rs_cam)
  with patch("percebro.realsense.rs.pipeline", return_value=MagicMock()), \
       patch("percebro.realsense.rs.align", return_value=MagicMock()):
    assert rs_cam_nopipe.enableDepth(test_params.img_width, test_params.img_height)
  return

def test_enableColor(rs_cam, rs_cam_nopipe, test_params):
  """! Test realsense.RSCamera enableColor method. """

  rs_cam.stop = MagicMock(return_value=True)
  rs_cam.getResolution = MagicMock(return_value=(test_params.img_width, test_params.img_height))
  rs_cam_nopipe.getResolution = MagicMock(return_value=(test_params.img_width, test_params.img_height))
  assert rs_cam.enableColor((test_params.img_width, test_params.img_height))
  conftest.start_rs_cam(rs_cam)
  with patch("percebro.realsense.rs.pipeline", return_value=MagicMock()), \
       patch("percebro.realsense.rs.align", return_value=MagicMock()):
    assert rs_cam_nopipe.enableColor( (test_params.img_width, test_params.img_height) )
  return

def test_setupCVIntrinsics(rs_cam, cam_intrinsics):
  """! Test realsense.RSCamera setupCVIntrinsics method. """

  rs_cam.rgbIntrinsics = cam_intrinsics
  rs_cam.setupCVIntrinsics()
  assert np.array_equal(rs_cam.matrix, cam_intrinsics.get_intrinsics_matrix())
  assert np.array_equal(rs_cam.distortion, cam_intrinsics.get_distortion_matrix())
  return

def test_cameras(rs_cam):
  """! Test realsense.RSCamera cameras method. """

  val1 = rs_cam.cameras()
  realsense._rs_ctx = None
  val2 = rs_cam.cameras()
  assert isinstance(val1, list)
  assert isinstance(val2, list)
  return

def test_isRealSense(rs_cam, test_params):
  """! Test realsense.RSCamera isRealSense method. """

  val1 = rs_cam.isRealSense(test_params.cam_serial_1)
  out_1 = conftest.Output_v4l2_ctrl("PayCam: PayCam (usb-0000:00:14.0-1):\n\t/dev/video1")
  with patch("percebro.realsense.subprocess.run", return_value=out_1):
    val2 = rs_cam.isRealSense(test_params.cam_serial_1)
  out_2 = conftest.Output_v4l2_ctrl("RealSense: RealSense (usb-0000:00:14.0-1):\n\t/dev/video1234")
  with patch("percebro.realsense.subprocess.run", return_value=out_2):
    val3 = rs_cam.isRealSense(test_params.cam_serial_1)
  assert val1 is None
  assert val2 is None
  assert val3 is not None
  return

def test_rs_init(test_params):
  """! Test realsense.RSCamera _rs_init method. """

  cam1 = conftest.FakeCam(test_params.cam_serial_1)
  cam2 = conftest.FakeCam(test_params.cam_serial_2)
  with patch("percebro.realsense.rs.context", return_value=conftest.FakeCTX([cam1, cam2])), \
       patch("percebro.realsense.rs.pipeline", return_value=MagicMock()):
    RSCamera._rs_init()
  assert len(realsense._rs_cameras) == 1
  assert isinstance(realsense._rs_cameras[0], RSCamera)

  return

@pytest.mark.parametrize("fakeCTX, serial, clear_serial, clear_rs_ctx, expected",
                          [(False, 1, False, False, None),
                           (True, 3, False, False, "RSCamera"),
                           (False, 1, True, False, None),
                           (True, 1, False, False, None),
                           (False, 1, False, True, None)])
def test_cameraForID_2(test_params, fakeCTX, serial, clear_serial, clear_rs_ctx, expected):
  """! Test realsense.RSCamera cameraForID method. """

  if (fakeCTX) == True and serial == 1:
    fake_cam = conftest.FakeCam(test_params.cam_serial_1)
  elif (fakeCTX) == True and serial == 3:
    fake_cam = conftest.FakeCam(test_params.cam_serial_3)

  if fakeCTX == True:
    with patch("percebro.realsense.rs.context", return_value=conftest.FakeCTX([fake_cam])), \
         patch("percebro.realsense.rs.pipeline", return_value=MagicMock()):
      RSCamera._rs_init()

  if clear_serial == True:
    realsense._rs_cameras[0].serial = ""
  if clear_rs_ctx == True:
    realsense._rs_ctx = None

  val = RSCamera.cameraForID(test_params.cam_serial_1)
  if expected == "RSCamera":
    assert isinstance(val, RSCamera)
  else:
    assert val is expected
  return

def test_start(rs_cam, cam_intrinsics):
  """! Test realsense.RSCamera start method. """

  stream_1 = conftest.FakeStream(pyrealsense2.stream.color, cam_intrinsics)
  stream_2 = conftest.FakeStream(pyrealsense2.stream.depth, cam_intrinsics)
  stream_3 = conftest.FakeStream(None, cam_intrinsics)
  streams = [stream_1, stream_2, stream_3]

  profile = MagicMock()
  profile.get_streams = MagicMock(return_value=streams)
  pipeline = MagicMock()
  pipeline.start = MagicMock(return_value=profile)
  with patch("percebro.realsense.rs.pipeline", return_value=pipeline), \
    patch("percebro.realsense.RSCamera.stop", return_value=True):
    rs_cam.start()
  assert rs_cam.pipeline is not None
  return
