# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import cv2
import torch
import yaml
try:
  from ultralytics.yolo.utils import ops
except ImportError:
  raise ImportError("Failed to import 'ops' module. Please ensure ultralytics is installed correctly.")

from scene_common.geometry import Point, Rectangle

from detector import Detector, Distributed, IAData

class YoloV8Detector(Detector):
  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    super().__init__(asynchronous=asynchronous, distributed=distributed)
    self.ie = None
    self.threshold = 0.5
    self.detector = None
    self.asynchronous = asynchronous
    self.saveDict = True
    self.normalize_input = True
    # Parameters from demo. Keeping snake_case for them.
    self.max_detections = 300
    self.nms_iou_threshold = 0.7
    # Model size
    self.h = 640
    self.w = 640
    # Model ordering
    self.idxCategory = 5
    self.idxConfidence = 4
    self.idxOriginX = 0
    self.idxOriginY = 1
    self.idxOppositeX = 2
    self.idxOppositeY = 3
    # Default colorspace is RGB.
    self.colorSpaceCode = cv2.COLOR_BGR2RGB
    self.normalized_output = False
    return

  def loadLabels(self, metadatafile):
    with open(metadatafile,'r') as file:
      model_info = yaml.safe_load(file)
      self.categories = []
      for cat in model_info['names']:
        self.categories.append(model_info['names'][cat])
    return

  def setParameters(self, model, device, plugin, threshold, ov_cores):
    # Some yolov8 export options generate a completly dynamic model
    # with a -1, 3, -1, -1 shape. Force-request a (self.w x self.h) version of it.
    model['input_shape'] = [1, 3, self.h, self.w]
    super().setParameters(model, device, plugin, threshold, ov_cores)
    if 'categories' in model:
      if isinstance(model['categories'],str):
        self.loadLabels(model['categories'])
      else:
        self.categories = model['categories']
    if 'threshold' in model:
      self.threshold = model['threshold']
    return

  def postprocess(self, result):
    objects = []
    predictions = ops.non_max_suppression( torch.from_numpy(result.data['output0']),
        self.threshold,          #'min_conf_threshold' min confidence for detections
        self.nms_iou_threshold,  #threshold for overlap.
        nc=len(self.categories), #Number of classes.
        agnostic=False,
        max_det=self.max_detections)[0] # One frame at a time, so index 0

    if not len(predictions):
      return objects

    # Note 'predictions' already contains only the subset of boxes with confidence
    # above the requested threshold.
    for det in predictions:

      cidx = int(det[self.idxCategory])
      if cidx < len(self.categories):
        category = self.categories[cidx]
      else:
        category = "unknown:%i" % (cidx)

      if det[self.idxConfidence] < self.threshold:
        continue

      bounds = self.recalculateBoundingBox(det[self.idxOriginX:self.idxOppositeY+1],
                                           result.save[0],
                                           result.save[1])
      comw = bounds.width / 3
      comh = bounds.height / 4
      center_of_mass = Rectangle(origin=Point(bounds.x + comw, bounds.y + comh),
                                 size=(comw, comh))
      odict = {'id': len(objects) + 1,
             'category': category,
             'confidence': float(det[self.idxConfidence]),
             'bounding_box': bounds.asDict,
             'center_of_mass': center_of_mass.asDict}
      objects.append(odict)
    return objects
