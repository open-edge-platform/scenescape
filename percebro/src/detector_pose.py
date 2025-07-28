# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np

from scene_common.geometry import Point, Rectangle

from detector import Detector, Distributed
from open_pose import OpenPoseDecoder

class PoseEstimator(Detector):
  POSE_PAIRS = ((15, 13), (13, 11), (16, 14), (14, 12), (11, 12), (5, 11),
                (6, 12), (5, 6), (5, 7), (6, 8), (7, 9), (8, 10), (1, 2),
                (0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (4, 6))

  bodyPartKP = ['Nose', 'Left-Eye', 'Right-Eye', 'Left-Ear', 'Right-Ear',
                'Left-Shoulder', 'Right-Shoulder', 'Left-Elbow', 'Right-Elbow',
                'Left-Wrist', 'Right-Wrist', 'Left-Hip', 'Right-Hip',
                'Left-Knee', 'Right-Knee', 'Left-Ankle', 'Right-Ankle']

  colors = [  (255,0,0),  (255,85,0), (255,170,0), (255,255,0), (170,255,0),  (85,255,0),
              (0,255,0),  (0,255,85), (0,255,170), (0,255,255), (0,170,255),  (0,85,255),
              (0,0,255),  (85,0,255), (170,0,255), (255,0,255), (255,0,170)]

  def __init__(self, asynchronous=False, distributed=Distributed.NONE):
    super().__init__(asynchronous=asynchronous, distributed=distributed)
    self.decoder = OpenPoseDecoder()
    self.saveDict = True

    return

  def setParameters(self, model, device, plugin, threshold, ov_cores):
    super().setParameters(model, device, plugin, threshold, ov_cores)

    if self.distributed == Distributed.OVMS:
      self.output_keys = list(self.model_metadata["outputs"].keys())
      self.n, self.c, self.h, self.w = self.model_metadata["inputs"]["data"]["shape"]
    else:
      self.output_keys = [out.get_any_name() for out in self.model.outputs]
      self.n, self.c, self.h, self.w = self.model.inputs[0].shape

    return

  def postprocess(self, result):
    people = []
    poses = self.processResults(result)

    for pose in poses:
      points = pose[:, :2]
      points_scores = pose[:, 2]

      hpe_bounds = [None] * 4
      published_pose = []
      for point, score in zip(points, points_scores):
        if len(point) == 0 or score == 0:
          published_pose.append(())
          continue

        point_x, point_y = point[0], point[1]
        published_pose.append((point_x, point_y))

        if hpe_bounds[0] is None or point_x < hpe_bounds[0]:
          hpe_bounds[0] = point_x
        if hpe_bounds[2] is None or point_x > hpe_bounds[2]:
          hpe_bounds[2] = point_x
        if hpe_bounds[1] is None or point_y < hpe_bounds[1]:
          hpe_bounds[1] = point_y
        if hpe_bounds[3] is None or point_y > hpe_bounds[3]:
          hpe_bounds[3] = point_y

      if hpe_bounds[0] == None:
        continue

      if self.hasKeypoints(published_pose,
                          ('Right-Hip', 'Right-Knee', 'Right-Ankle',
                          'Left-Hip', 'Left-Knee', 'Left-Ankle')) \
          or self.hasKeypoints(published_pose,
                              ('Right-Shoulder', 'Right-Elbow', 'Right-Wrist',
                              'Left-Shoulder', 'Left-Elbow', 'Left-Wrist')):

        bounds = Rectangle(origin=Point(hpe_bounds[0], hpe_bounds[1]),
                           opposite=Point(hpe_bounds[2], hpe_bounds[3]))
        if bounds.width == 0 or bounds.height == 0:
          continue

        comw = bounds.width / 3
        comh = bounds.height / 4
        center_of_mass = Rectangle(origin=Point(bounds.x + comw, bounds.y + comh),
                                   size=(comw, comh))
        person = {'id': len(people) + 1,
                  'category': 'person',
                  'bounding_box': bounds.asDict,
                  'center_of_mass': center_of_mass.asDict,
                  'pose': published_pose}
        people.append(person)

    return people

  def hasKeypoints(self, pose, points):
    for point in points:
      idx = self.bodyPartKP.index(point)
      if idx >= len(pose) or not len(pose[idx]):
        return False
    return True

  def processResults(self, results):

    pafs = results.data[self.output_keys[0]]
    heatmaps = results.data[self.output_keys[1]]

    pooled_heatmaps = np.array(
        [[self.maxpool(h, kernel_size=3, stride=1, padding=1) for h in heatmaps[0]]])
    nms_heatmaps = self.nonMaxSuppression(heatmaps, pooled_heatmaps)

    image_shape = results.save
    poses, _ = self.decoder(heatmaps, nms_heatmaps, pafs)

    if self.distributed == Distributed.OVMS:
      output_shape = self.model_metadata["outputs"][self.output_keys[0]]['shape']
    else:
      output_shape = self.model.get_output_shape(0)

    image_width, image_height = image_shape
    _, _, output_height, output_width = output_shape
    x_scale, y_scale = image_width / output_width, image_height / output_height

    if self.keep_aspect:
      height_ratio = self.h / image_height
      width_ratio = self.w / image_width
      if height_ratio <= width_ratio:
        x_scale = x_scale / (height_ratio / width_ratio)
      else:
        y_scale = y_scale / (width_ratio / height_ratio)

    poses[:, :, :2] *= (x_scale, y_scale)
    return poses

  def maxpool(self, matrix, kernel_size, stride, padding):
    matrix = np.pad(matrix, padding, mode="constant")
    output_shape = ((matrix.shape[0] - kernel_size) // stride + 1,
                    (matrix.shape[1] - kernel_size) // stride + 1,)

    kernel_size = (kernel_size, kernel_size)

    matrix_view = np.lib.stride_tricks.as_strided(matrix,
        shape=output_shape + kernel_size,
        strides=(stride * matrix.strides[0], stride * matrix.strides[1]) + matrix.strides)
    matrix_view = matrix_view.reshape(-1, *kernel_size)

    return matrix_view.max(axis=(1, 2)).reshape(output_shape)

  def nonMaxSuppression(self, result, pooled_result):
    return result * (result == pooled_result)
