# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import re
import subprocess

import pyrealsense2 as rs
import numpy as np
import cv2

from scene_common import log

_rs_ctx = None

class RSImage:
  def __init__(self, frame):
    # Explicity create a copy of the depth + color data, to avoid realsense issues.
    self.depth_info = None if not frame.get_depth_frame() else np.asanyarray(frame.get_depth_frame().get_data()).copy()
    color_frame = frame.get_color_frame()
    self.color_info = None if not color_frame else np.asanyarray(color_frame.get_data()).copy()
    self.shape_info = (0,0) if not color_frame else (int(color_frame.get_height()), int(color_frame.get_width()))
    # Infrared attributes:
    if frame.get_infrared_frame():
      self.metadata = frame.get_frame_metadata(rs.pyrealsense2.frame_metadata_value.frame_laser_power_mode)
      self.infrared_info = np.asanyarray(frame.get_infrared_frame().get_data()).copy()
    else:
      self.infrared_info = None
      self.metadata = None
    return

  @property
  def shape(self):
    return self.shape_info

  @property
  def color(self):
    return self.color_info

  @property
  def infrared_metadata(self):
    return self.metadata

  @property
  def infrared(self):
    return self.infrared_info

  @property
  def depth(self):
    return self.depth_info

class RSCamera:
  MODE_DEFAULT = 0
  MODE_MASTER = 1
  MODE_SLAVE = 2

  def __init__(self, camSerial, syncMode=MODE_MASTER, resolution=None):
    global _rs_ctx

    if _rs_ctx is None:
      RSCamera._rs_init()

    self.serial = camSerial
    self.syncMode = syncMode
    self.config = rs.config()
    self.config.enable_device(self.serial)
    self.pipeline = None
    self.enableDepth(640, 480)
    self.enableColor(resolution)
    self.start()
    align_to = rs.stream.color
    self.align = rs.align(align_to)
    self.eatFrames(30)

    return

  def read(self):
    return 1, RSImage(self.captureAlignedImage())

  def set(self, key, value):
    return

  def captureFrame(self):
    if not self.pipeline:
      self.start()
    return self.pipeline.wait_for_frames()

  def captureAlignedImage(self):
    return self.align.process(self.captureFrame())

  def captureDepthImage(self):
    return self.captureFrame().get_depth_frame()

  def captureRGBImage(self):
    cFrame = self.captureFrame().get_color_frame()
    return np.asanyarray(cFrame.get_data())

  def enableDepth(self, width, height):
    if self.pipeline:
      self.stop()
    self.config.enable_stream(rs.stream.depth, width, height, rs.format.z16, 30)
    return True

  def getFramerate(self):
    """! Gets the frame rate set in the Realsense pipeline's stream

    @param    self          RS Camera object

    @return   rate
    """
    rate = 30
    # Pipeline needs to be started in order to get the pipeline profile, captureFrame takes care of that.
    _ = self.captureFrame()
    profile = self.pipeline.get_active_profile()
    streams = profile.get_streams()
    for s in streams:
      if s.stream_type() == rs.stream.color:
        rate = s.as_video_stream_profile().fps()
        break
    return rate

  def getResolution(self):
    """! Gets the resolution set in the Realsense pipeline's stream

    @param    self          RS Camera object

    @return   width, height
    """
    width = None
    height = None
    # Pipeline needs to be started in order to get the pipeline profile, captureFrame takes care of that.
    _ = self.captureFrame()
    profile = self.pipeline.get_active_profile()
    streams = profile.get_streams()
    for s in streams:
      if s.stream_type() == rs.stream.color:
        height = s.as_video_stream_profile().height()
        width = s.as_video_stream_profile().width()
        break
    return width, height

  def setFramerate(self, rate):
    """! Configure framerate for Realsense camera object

    @param    self          RS Camera object
    @param    rate          Desired framerate to apply to stream.

    @return   BOOL          True if requested rate was applied successfuly. False otherwise.
    """
    width, height = self.getResolution()
    if self.pipeline:
      self.stop()
    self.config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, int(rate))
    try:
      r = self.getFramerate()
    except RuntimeError:
      return False
    return r == rate

  def enableColor(self, resolution):
    rate = 30
    if self.pipeline:
      rate = self.getFramerate()
      self.stop()
    if resolution is not None:
      width, height = resolution
      self.config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, rate)
      try:
        w, h = self.getResolution()
      except RuntimeError:
        return False
      return w == width and h == height
    else:
      self.config.enable_stream(rs.stream.color, rs.format.bgr8, rate)
    return True

  def setupCVIntrinsics(self):
    self.matrix = np.array([ [self.rgbIntrinsics.fx, 0, self.rgbIntrinsics.ppx],
                             [0, self.rgbIntrinsics.fy, self.rgbIntrinsics.ppy],
                             [ 0, 0, 1] ])
    self.distortion = np.array([0,0,0,0,0], dtype=np.float32)
    return

  def start(self):
    if self.pipeline:
      self.stop()
    self.pipeline = rs.pipeline()
    profile = self.pipeline.start(self.config)
    depth_sensor = profile.get_device().first_depth_sensor()
    self.pipeline.stop()
    depth_sensor.set_option(rs.option.inter_cam_sync_mode, self.syncMode);
    profile = self.pipeline.start(self.config)
    streams = profile.get_streams()
    for s in streams:
      if s.stream_type() == rs.stream.color:
        self.rgbIntrinsics = s.as_video_stream_profile().get_intrinsics()
        self.setupCVIntrinsics()
      elif s.stream_type() == rs.stream.depth:
        self.depthIntrinsics = s.as_video_stream_profile().get_intrinsics()
    return

  def stop(self):
    self.pipeline.stop()
    self.pipeline = None
    return

  def eatFrames(self, count):
    for i in range(count):
      self.captureFrame()
    return

  @staticmethod
  def cameras():
    if _rs_ctx is None:
      RSCamera._rs_init()
    return _rs_cameras

  @staticmethod
  def isRealSense(camID):
    path = camID
    if isinstance(path, int) or re.match("^[0-9]+$", path):
      path = f"/dev/video{path}"
    cmd = ["v4l2-ctl", "--list-devices"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True)
    devices = result.stdout.splitlines()
    model = None
    basedevice = None
    for line in devices:
      if ':' in line:
        model = line
        basedevice = None
      if line.startswith("\t/dev/video") and "RealSense" in model:
        if basedevice is None:
          basedevice = line
        if line.endswith(path):
          name = basedevice.split('/')[2]
          if re.match("^video[0-9]+$", name):
            name = re.sub( 'video', '', name )
            return name
    return None

  @staticmethod
  def _rs_init():
    global _rs_ctx, _rs_devices, _rs_cameras

    _rs_ctx = rs.context()
    _rs_devices = _rs_ctx.query_devices()
    _rs_cameras = []
    mode = RSCamera.MODE_MASTER

    if len(_rs_ctx.devices) > 0:
      for cam in _rs_ctx.devices:
        log.info('Found RealSense device: ', cam.get_info(rs.camera_info.serial_number))
        # FIXME - Had to do this to ignore bogus device
        if len(cam.get_info(rs.camera_info.serial_number)) > 5:
          _rs_cameras.append(RSCamera(cam.get_info(rs.camera_info.serial_number), mode))
          mode = RSCamera.MODE_SLAVE
    return

  @staticmethod
  def cameraForID(camID):
    global _rs_ctx, _rs_devices, _rs_cameras

    if not _rs_ctx:
      RSCamera._rs_init()

    vbase = "video" + str(camID)
    for dev in _rs_devices:
      lpath = dev.get_info(rs.camera_info.physical_port)
      lbase = os.path.basename(lpath)
      if vbase == lbase:
        serial = dev.get_info(rs.camera_info.serial_number)
        for cam in _rs_cameras:
          if cam.serial == serial:
            return cam
    return None

class RSBag(RSCamera):
  def __init__(self, path):
    self.config = rs.config()
    # Force repeat_playback to True to avoid the 'Frame didn't arrive within 5000'
    # when we reach EOS.
    rs.config.enable_device_from_file(self.config, path, repeat_playback=True)
    self.config.enable_all_streams()
    self.pipeline = None
    self.start()
    align_to = rs.stream.color
    self.align = rs.align(align_to)
    return

  def start(self):
    self.current_frame = 0
    if self.pipeline:
      self.stop()
    self.pipeline = rs.pipeline()
    profile = self.pipeline.start(self.config)
    streams = profile.get_streams()
    rate = 30
    for s in streams:
      if s.stream_type() == rs.stream.color:
        self.rgbIntrinsics = s.as_video_stream_profile().get_intrinsics()
        # Query and save the pixel format in case we need to convert it
        self.pixel_format = s.as_video_stream_profile().format()
        log.info("Found format", self.pixel_format)
        self.setupCVIntrinsics()
        rate = s.as_video_stream_profile().fps()
      elif s.stream_type() == rs.stream.depth:
        self.depthIntrinsics = s.as_video_stream_profile().get_intrinsics()

    self.frame_count = int(profile.get_device().as_playback().get_duration().total_seconds() * rate)
    return

  def getNumberOfFrames(self):
    return self.frame_count

  def read(self):
    # Count the number of frames too, for allowing
    # preprocessing of the input file (no looping).
    if self.current_frame >= self.frame_count:
      return 0, None
    self.current_frame += 1

    rs_image = RSImage(self.captureAlignedImage())
    # Convert the image to BGR if needed.
    if rs_image and rs_image.color_info is not None and self.pixel_format == rs.format.rgb8:
      rs_image.color_info = cv2.cvtColor(rs_image.color_info, cv2.COLOR_RGB2BGR)
    return 1, rs_image
