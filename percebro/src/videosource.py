# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import re, os, cv2

from realsense import RSBag

from scene_common.transform import CameraIntrinsics
from scene_common.timestamp import get_epoch_time
from scene_common import log

# RealSense will segfault if /dev/bus/usb doesn't exist
if os.path.exists("/dev/bus/usb") and os.path.isdir("/dev/bus/usb"):
  from realsense import RSCamera
  REALSENSE_AVAIL=True
else:
  REALSENSE_AVAIL=False

MIN_64BIT_INT = -0x8000000000000000

class VideoSource:
  def __init__(self, path, intrinsics, distortion, uniqueID=None, loop=False,
               cvSubsystem='ANY', resolution=None, max_distance=None):

    self.isFile = False
    self.isStream = False
    self.realTime = True
    self.loop = loop
    self.frameCount = None
    self.is_bag = False
    self.cv_subsystem = cvSubsystem
    # Keep distance squared to avoid square roots per detection
    self.max_distance_squared = None
    if max_distance and max_distance >= 0:
      self.max_distance_squared = max_distance ** 2

    self.url = path
    if path.startswith(("rtsp://", "http://", "https://")):
      path = f"uridecodebin uri={path}" \
        " ! videoconvert" \
        " ! appsink max-buffers=1 drop=true"
    elif re.match("^[0-9]+$", path):
      path = f"/dev/video{path}"

    self.camID = path
    self.isStream = not os.path.exists(self.camID)
    if not self.isStream:
      self.isFile = os.path.isfile(self.camID)
      self.is_bag = self.camID.endswith('.bag')
      self.modifiedTime = os.path.getmtime(self.camID)

    if not uniqueID:
      uniqueID = str(self.camID)[0][-2:]
    self.uniqueID = uniqueID
    self.realsense_id = None
    if REALSENSE_AVAIL:
      self.realsense_id = RSCamera.isRealSense(self.camID)
    self.open()

    if resolution is None:
      width, height = self.getResolution()
      resolution = (width, height)
    else:
      ret = self.setResolution(resolution)
      if not ret:
        raise Exception("Unable to set resolution")

    if self.isRealSense or self.is_bag:
      intrinsics = self.cam.matrix

    if isinstance(intrinsics, CameraIntrinsics):
      self._intrinsics = intrinsics
    elif intrinsics is not None:
      self._intrinsics = CameraIntrinsics(intrinsics, distortion, resolution)

    if self.isRealSense or self.is_bag:
      self.fps = self.cam.getFramerate()
    else:
      self.fps = self.cam.get(cv2.CAP_PROP_FPS)
    # If any of the pipelines does not work, reports default value = 30
    if self.fps == 0.0:
      self.fps = 30

    if self.isFile and not self.is_bag:
      self.frameCount = int(self.cam.get(cv2.CAP_PROP_FRAME_COUNT))

      # opencv can use jpg as a video just fine, but freaks out on png
      if self.frameCount < 0:
        self.frameCount = 1
      self.length = (self.frameCount * 1000) / self.fps

      self.startTime = self.modifiedTime - self.length / 1000
      # print("LENGTH", self.camID, self.frameCount, "%0.3f" % (self.length), self.fps)
      # log(self.startTime, self.modifiedTime, self.length)
    self.startPosition = 0
    return

  def open(self):
    if self.is_bag:
      self.cam = RSBag(self.camID)
    elif self.isRealSense:
      self.camID = self.realsense_id
      self.cam = RSCamera.cameraForID(self.camID)
    else:
      self.cam = cv2.VideoCapture()
      self.configureHWAccel()
    return

  def configureHWAccel(self):
    cvApiPref = cv2.CAP_ANY
    if 'GPU' in self.cv_subsystem:
      # Force FFMPEG and VAAPI
      cvHwAccel = cv2.VIDEO_ACCELERATION_VAAPI
      cvApiPref = cv2.CAP_FFMPEG
      cvDevice = 0
      if '.' in self.cv_subsystem:
        subsystemSplit = self.cv_subsystem.split(".")
        cvDevice = int(subsystemSplit[1])
      params = (cv2.CAP_PROP_HW_ACCELERATION, cvHwAccel, cv2.CAP_PROP_HW_DEVICE, int(cvDevice))
    elif self.cv_subsystem == 'CPU':
      params = None
    elif self.cv_subsystem == 'ANY':
      params = (cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY)
    else:
      log.warn("Invalid/Unknown subsystem {}".format(self.cv_subsystem))
      return None

    self.cam.open(self.camID, apiPreference=cvApiPref, params=params)
    if not self.cam.isOpened():
      raise ValueError("Unable to open {}".format(self.camID))
    hw_accel = self.cam.get(cv2.CAP_PROP_HW_ACCELERATION)
    if hw_accel > 0:
      log.info("HW Accel {} on device {}".format(hw_accel, self.cam.get(cv2.CAP_PROP_HW_DEVICE)))
    else:
      log.info("HW Accel unavailable")
    return

  def setStartPosition(self, pos):
    if self.is_bag:
      raise RuntimeError("BAG files do not support seeking")
    self.startPosition = pos * 1000
    if not self.is_bag:
      self.cam.set(cv2.CAP_PROP_POS_MSEC, self.startPosition)
    return

  def setEndPosition(self, pos):
    self.endPosition = pos * 1000
    return

  def capture(self):
    now = get_epoch_time()
    # BAG files don't support seeking, or grabbing frames until we catch up, they are all
    # captured with the same frame delta.
    if self.isFile and hasattr(self, 'endPosition') and self.realTime and not self.is_bag:
      frame_msec = (1 / self.fps) * 1000
      first_frame = int(self.startPosition / frame_msec)
      last_frame = int(self.endPosition / frame_msec)
      max_frames = last_frame - first_frame

      if not hasattr(self, 'startClock'):
        self.lastCapture = self.startClock = now * 1000
      next_fnum = int((now * 1000 - self.startClock) / frame_msec)
      cur_fnum = int((self.lastCapture - self.startClock) / frame_msec)
      #fnum = int(self.cam.get(cv2.CAP_PROP_POS_FRAMES)) - first_frame

      if next_fnum > last_frame and not self.loop:
        return None

      nframes = next_fnum - cur_fnum
      #print("FRAMES BEHIND", nframes, next_fnum, cur_fnum, max_frames)
      if nframes == 0:
        return None

      if nframes > 1:
        if nframes < 10:
          # Faster to grab frames and discard them than to use a seek
          for idx in range(nframes - 1):
            self.cam.grab()
        else:
          log.debug("SEEKING", nframes, next_fnum + first_frame)
          self.cam.set(cv2.CAP_PROP_POS_FRAMES, (next_fnum % max_frames) + first_frame)

    ret, frame = self.cam.read()

    while not ret and (not self.isFile or self.loop):
      del self.cam
      self.open()
      if self.isFile and not self.is_bag:
        # print("RESTARTING")
        self.cam.set(cv2.CAP_PROP_POS_MSEC, self.startPosition)
      ret, frame = self.cam.read()

    # FIXME - if there is no unwarp attribute, check of FoV is over a default threshold
    if frame is not None and hasattr(self, "unwarp") and self.unwarp:
      frame = self.intrinsics.unwarp(frame)

    self.lastCapture = now * 1000
    return frame

  def getResolution(self):
    if self.isRealSense or self.is_bag:
      width, height = self.cam.getResolution()
    else:
      if self.isFile:
        nframe = self.cam.get(cv2.CAP_PROP_POS_FRAMES)
      frame = self.capture()
      width = float(frame.shape[1])
      height = float(frame.shape[0])
      if self.isFile:
        self.cam.set(cv2.CAP_PROP_POS_FRAMES, nframe)
    if width == 0 or height == 0:
      raise Exception("Unable to get resolution")
    return (width, height)

  def setFramerate(self, rate):
    """! Configure framerate for camera object

    @param    self          VideoSource object
    @param    rate          Desired framerate to apply to stream.

    @return   BOOL          True if requested rate was applied successfuly. False otherwise.
    """
    if self.isRealSense or self.is_bag:
      return self.cam.setFramerate(rate)
    #elif self.is_bag:
    #  return False
    else:
      result = self.cam.set(cv2.CAP_PROP_FPS, rate)
      read_rate = self.cam.get(cv2.CAP_PROP_FPS)
      return result and read_rate == rate

  def setResolution(self, size):
    ret = False
    if self.isFile:
      log.warn("Resolution cannot be set for a file playback")
    elif self.isStream:
      log.warn("Resolution cannot be set for a network stream")
    elif self.isRealSense:
      ret = self.cam.enableColor( (int(size[0]), int(size[1])) )
      self._intrinsics = self.cam.matrix
      width, height = self.getResolution()
      if width != int(size[0]) or height != int(size[1]):
        ret = False
    else:
      if not self.cam.set(cv2.CAP_PROP_FRAME_WIDTH, float(size[0])) \
         or not self.cam.set(cv2.CAP_PROP_FRAME_HEIGHT, float(size[1])):
        log.warn("Set resolution failed")
      ret = True

    return ret

  @property
  def isRealSense(self):
    return self.realsense_id is not None

  @property
  def intrinsics(self):
    return self._intrinsics

  @intrinsics.setter
  def intrinsics(self, value):
    'setting'
    self._intrinsics = value

  def getNumberOfFrames(self):
    if self.is_bag:
      return self.cam.getNumberOfFrames()
    elif self.isFile:
      return self.cam.get(cv2.CAP_PROP_POS_FRAMES)
    else:
      raise RuntimeError("Streams do not support getting number of frames")

  def supportsPositionUpdate(self):
    return self.isFile and not self.is_bag
