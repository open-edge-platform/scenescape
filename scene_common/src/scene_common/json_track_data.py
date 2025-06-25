# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import os
import json
import glob
import cv2
import numpy as np

from scene_common.timestamp import get_iso_time, get_epoch_time
from scene_common import log

AVG_FRAMES = 15

class CamManager:
  def __init__(self, inputs, scene):
    self.jfiles = []
    self.frameres = [0, 0]
    self.camStart = None
    self.loopCount = 0
    self.frameBuf = [None] * len(inputs)

    for path in inputs:
      jfile = Simcam(path)
      # Throw away first frame
      camDetect = jfile.read()

      if scene:
        sensor = scene.cameraWithID(camDetect['id'])
        if not sensor:
          log.error("NO SUCH SENSOR", camDetect['id'])
          exit(1)

        frame = jfile.getImage(camDetect, scene)
        sensor.pose.setResolution((frame.shape[1], frame.shape[0]))
        if frame.shape[1] / 2 > self.frameres[0]:
          self.frameres[0] = int(frame.shape[1] / 2)
        if frame.shape[0] / 2 > self.frameres[1]:
          self.frameres[1] = int(frame.shape[0] / 2)

      # jfile.initWriter((int(frame.shape[1] / 2), int(frame.shape[0] / 2)))
      self.jfiles.append(jfile)
    return

  def nextFrame(self, scene, loop, readFrame=True):
    for idx in range(len(self.jfiles)):
      if not self.frameBuf[idx]:
        self.frameBuf[idx] = self.jfiles[idx].read(loop=False)

    if self.frameBuf.count(None) == len(self.frameBuf):
      if not loop:
        return 0, False, None
      self.loopCount += 1
      for idx in range(len(self.jfiles)):
        self.jfiles[idx].reset()
        self.frameBuf[idx] = self.jfiles[idx].read(loop=False)

    t = [x['epochtime'] if x else np.nan for x in self.frameBuf]
    idx = np.nanargmin(t)
    camDetect = self.frameBuf[idx]
    self.frameBuf[idx] = None
    # print("USING FRAME", camDetect['id'], camDetect['frame'], camDetect['epochtime'])
    if scene and readFrame:
      frame = self.jfiles[idx].getImage(camDetect, scene)
    else:
      frame = None

    # Correct timestamp
    if self.loopCount:
      t = [x.frameFirst for x in self.jfiles]
      frameFirst = np.min(t)
      t = [x.frameLast for x in self.jfiles]
      idx = np.argmax(t)
      last = self.jfiles[idx]
      frameLast = last.frameLast

      when = camDetect['epochtime']
      when += ((frameLast + 1 / last.frameAvg) - frameFirst) * self.loopCount
      camDetect['epochtime'] = when

      camDetect['timestamp'] = get_iso_time(when)

    return idx, camDetect, frame

class Simcam:
  def __init__(self, path):
    self.path = path
    base, ext = os.path.splitext(self.path)
    self.jfile = open(base + ".json", "r")
    self.video = None
    self.frameAvg = 0
    self.frameFirst = self.frameLast = None
    self.lastFrame = -1
    return

  def reset(self):
    self.jfile.seek(0, 0)
    return

  def read(self, loop=True, after=None):
    camData = self.jfile.readline()
    if not camData:
      if not loop:
        return None
      self.reset()
      camData = self.jfile.readline()
    camDetect = json.loads(camData)

    when = get_epoch_time(camDetect['timestamp'])
    camDetect['epochtime'] = when

    if not self.frameFirst:
      self.frameFirst = when

    if not self.frameLast or when > self.frameLast:
      if not self.frameLast:
        self.frameLast = when
      self.frameAvg *= AVG_FRAMES
      self.frameAvg += when - self.frameLast
      self.frameAvg /= AVG_FRAMES + 1
      self.frameLast = when

    return camDetect

  def getImage(self, info, scene):
    if 'image' in info:
      frame = info['image']
      frame = np.fromstring(base64.b64decode(frame), np.uint8)
      frame = cv2.imdecode(frame, 1)
    elif 'frame' in info:
      num = info['frame']
      if not self.video:
        base, ext = os.path.splitext(self.path)
        base += ".*"
        possible = glob.glob(base)
        for p in possible:
          base, ext = os.path.splitext(p)
          if ext.startswith(".json"):
            continue
          break
        self.video = cv2.VideoCapture(p)
      if self.lastFrame + 1 != num:
        log.info("FRAME", num)
        ret = self.video.set(cv2.CAP_PROP_POS_FRAMES, num)
      ret, frame = self.video.read()
      self.lastFrame = num
    else:
      frame = 255 * np.ones((480, 640, 3), np.uint8)

    # # Unwarp
    # if info['id'] in scene.sensors:
    #   sensor = scene.sensors[info['id']]
    #   frame = sensor.pose.intrinsics.unwarp(frame)

    return frame

  def initWriter(self, res):
    base, ext = os.path.splitext(self.path)
    self.wrpath = base + "-demo.mp4"
    four_cc = cv2.VideoWriter_fourcc(*"MP4V")
    self.writer = cv2.VideoWriter(self.wrpath, four_cc, 15, res)
    return

  def writeFrame(self, frame):
    self.writer.write(frame)
    return

