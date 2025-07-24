#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2022 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import cv2
import imutils

from detector import Detector, Distributed, IAData
from scene_common import log

class MotionDetector(Detector):

  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    """! Initializes the MotionDetector object

    @param    asynchronous  Flag to enable asynchronous mode. Default is False.
    @param    distributed   Flag to enable distributed mode. Default is False.
    """
    super().__init__(asynchronous=asynchronous, distributed=distributed)
    self.fbgbMap = {}
    self.bgsAlg = 'mog2'
    self.contourSize = 12000
    self.detectShadows = 0
    return

  def detect(self, input, debugFlag=False):
    """! Detects and returns the detected object with bounding box based on
         motion

    @param    input       IAData object that contains an image
    @param    debugFlag   Flag to enable debug mode. Default is False.
    @return   A list of detected object and bounding box information
    """
    detections = []

    if (input is not None):
      if input.cameraID not in self.fbgbMap:
        if self.bgsAlg == 'knn':
          log.info("Running KNN bgs for {}".format(input.cameraID))
          self.fbgbMap[input.cameraID] = cv2.createBackgroundSubtractorKNN(self.model['history'], self.model['threshold'], self.detectShadows)
        elif self.bgsAlg == 'mog2':
          log.info("Running MOG2 bgs for {}".format(input.cameraID))
          self.fbgbMap[input.cameraID] = cv2.createBackgroundSubtractorMOG2(self.model['history'], self.model['threshold'], self.detectShadows)
        else:
          log.info("unknown bgs algorithm, running default MOG2 for {}".format(input.cameraID))
          self.fbgbMap[input.cameraID] = cv2.createBackgroundSubtractorMOG2(self.model['history'], self.model['threshold'], self.detectShadows)

      monoBlur = self.preprocess(input)

      for frame in monoBlur:

        currentCam = input.cameraID
        fgmask = self.fbgbMap[currentCam].apply(frame)

        thresh = cv2.dilate(fgmask, None, iterations=2)
        cnts = cv2.findContours(thresh.copy(),  cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = imutils.grab_contours(cnts)

        for c in cnts:
          if cv2.contourArea(c) < self.contourSize:
            continue

          (x, y, w, h) = cv2.boundingRect(c)

          detections.append((x, y, w, h))

      result = IAData(detections, input.id)
      self.taskLock.acquire()
      self.tasksComplete.append([result])
      self.taskLock.release()

    return super().detect(None, debugFlag=debugFlag)

  def preprocess(self, input):
    """! converts RGB image into grayscale

    @param    input       IAData object that contains an image
    @return   A grayscale image
    """
    monoBlur = []
    for frame in input.data:
      gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
      gray = cv2.GaussianBlur(gray, (21, 21), 0)
      monoBlur.append(gray)
    return monoBlur

  def postprocess(self, result):
    """! populates found object based on detection result

    @param    result      the list of detected objects
    @return   A list of detected object and bounding box information
    """

    found = []
    for detection in result.data:
      bounds = {'x': detection[0],
                'y': detection[1],
                'width': detection[2],
                'height': detection[3]
               }

      object = {'category': "motion",
                'bounding_box': bounds,
               }
      found.append(object)

    return found

  def setParameters(self, model, device, plugin, threshold, ov_cores):
    """! Sets model parameters to use for motion detection. The argument `model`
    needs to be a dict and must contains two attributes 'history' and 'threshold'.

    Good example of motion-mog2 model attributes: {'threshold': 16, 'history': 500}
    Good example of motion-knn model attributes: {'threshold': 400, 'history': 500}

    @param    model      The model parameters
    @param    device     Device name of a plugin to load the extensions to
    @param    plugin     Path to the extensions library file to load to a plugin
    @param    threshold  Threshold to filter keypoints
    @param    ovcores    Number of threads to request for OpenCV
    """
    if not isinstance(model, dict):
      raise TypeError(f"Argument type {type(model)} is inappropriate. Argument `model` must be a dict.")
    if 'history' not in model or 'threshold' not in model:
      raise KeyError("Missing key(s) 'history' and/or 'threshold' in dict `model`.")

    self.model = model
    return

class MotionMog2Detector(MotionDetector):

  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    """! Initializes the MotionMog2Detector object

    @param    asynchronous  Flag to enable asynchronous mode. Default is False.
    @param    distributed   Flag to enable distributed mode. Default is False.
    """
    super().__init__(asynchronous=asynchronous, distributed=distributed)
    self.fbgbMap = {}
    self.bgsAlg = 'mog2'

class MotionKnnDetector(MotionDetector):

  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    """! Initializes the MotionKnnDetector object

    @param    asynchronous  Flag to enable asynchronous mode. Default is False.
    @param    distributed   Flag to enable distributed mode. Default is False.
    """
    super().__init__(asynchronous=asynchronous, distributed=distributed)
    self.fbgbMap = {}
    self.bgsAlg = 'knn'
