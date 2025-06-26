#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import cv2
import numpy as np

from detector import Detector
from scene_common.geometry import Point, Rectangle

class Detector3D(Detector):
  """ Detector3D is a mock 3D object detector that uses the 2D retail model
  and create a 3D bounding boxes (where x=z). This class will be rewritten
  once we start supporting 3D object detection models in scenescape.
  """
  def postprocess(self, result):
    objects = []
    intrinsics = np.array([[905, 0.0, 640], [0.0, 905, 360], [0.0, 0.0, 1.0]])
    distortion = np.zeros(4)

    detections = result.data if isinstance(result.data, np.ndarray) else result.data.buffer
    detections = detections[0][0]

    for _, label, confidence, x_min, y_min, x_max, y_max in detections:
      # detections seem to be sorted by threshold descending, bail out
      # when threshold is too low or detection width or height is zero
      if confidence <= self.threshold or x_min == x_max or y_min == y_max:
        break

      category = self.categories[int(label)] if label < len(self.categories) else f"unknown:{label}"

      width, height = result.save[:2]
      x_min, y_min = int(x_min*width), int(y_min*height)
      x_max, y_max = int(x_max*width), int(y_max*height)

      # convert from pixel to meter. This step is needed to align the output
      # with the original output format.
      x_min, y_min = cv2.undistortPoints(np.float64((x_min, y_min)), intrinsics, distortion)[0][0]
      x_max, y_max = cv2.undistortPoints(np.float64((x_max, y_max)), intrinsics, distortion)[0][0]

      bounding_box = Rectangle(origin=Point(x_min, y_min, x_min),
                               opposite=Point(x_max, y_max, x_max))
      box_as_dict = bounding_box.asDict

      com_w, com_h = bounding_box.width / 3, bounding_box.height / 4
      com_x, com_y = bounding_box.x + com_w, bounding_box.y + com_h
      center_of_mass = Rectangle(origin=Point(com_x, com_y, com_x),
                                 size=(com_w, com_h, com_w))

      object = {
        'id': len(objects) + 1,
        'category': category,
        'confidence': float(confidence),
        'translation': [
          box_as_dict['x'] + (box_as_dict['width'] / 2),
          box_as_dict['y'] + (box_as_dict['height'] / 2),
          box_as_dict['z'] + (box_as_dict['depth'] / 2)
        ],
        'rotation': [0.5, 0.1, 0.0, 0.0],
        'size': [bounding_box.width, bounding_box.height, bounding_box.depth],
        'center_of_mass': center_of_mass.asDict
      }
      objects.append(object)

    return objects
