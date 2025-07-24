# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import cv2
import dt_apriltags

from detector import Detector, Distributed, IAData
from scene_common.geometry import Point, Rectangle

class ATagDetector(Detector):
  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    super().__init__(asynchronous=asynchronous, distributed=distributed)
    self.at_detector = dt_apriltags.Detector()
    return

  def detect(self, input, debugFlag=False):
    if input is not None:
      result = []
      mono = self.preprocess(input)
      for frame in mono:
        tags = self.at_detector.detect(frame)
        #print("APRILTAG DETECTED", len(tags), tags)
        result.append(IAData(tags, input.id))
      self.taskLock.acquire()
      self.tasksComplete.append(result)
      self.taskLock.release()
    return super().detect(None, debugFlag=debugFlag)

  def preprocess(self, input):
    monochrome = []
    for frame in input.data:
      gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
      monochrome.append(gray)
    return monochrome

  def postprocess(self, result):
    found = []
    for tag in result.data:
      bounds = [None] * 4
      for corner in tag.corners:
        if bounds[0] is None or corner[0] < bounds[0]:
          bounds[0] = corner[0]
        if bounds[2] is None or corner[0] > bounds[2]:
          bounds[2] = corner[0]
        if bounds[1] is None or corner[1] < bounds[1]:
          bounds[1] = corner[1]
        if bounds[3] is None or corner[1] > bounds[3]:
          bounds[3] = corner[1]

      bounds = Rectangle(origin=Point(bounds[0], bounds[1]),
                         opposite=Point(bounds[2], bounds[3]))
      object = {
        'category': "apriltag",
        'bounding_box': bounds.asDict,
        'tag_id': tag.tag_id,
        'tag_family': tag.tag_family.decode("utf-8"),
        'corners': tag.corners.tolist(),
        'homography': tag.homography.tolist(),
        'center': tag.center.tolist(),
        'hamming': tag.hamming,
        'decision_margin': tag.decision_margin,
      }
      found.append(object)
    return found
