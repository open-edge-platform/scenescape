# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

from scene_common.geometry import Point
from scene_common.transform import CameraIntrinsics, CameraPose
import numpy as np

DEFAULT_TRANSFORM = {
  'translation': [0, 0, 0],
  'rotation':  [0, 0, 0],
  'scale': [1, 1, 1]
}

def keysNotEmpty(info, keys):
  for k in keys:
    if k not in info:
      return False
    value = info[k]
    if isinstance(value, list) and not value:
      return False
    if isinstance(value, np.ndarray) and value.size == 0:
      return False
  return True

class Camera:
  def __init__(self, anID, info, resolution=None):
    self.cameraID = anID

    if resolution is None and 'width' in info and 'height' in info:
      resolution = (info['width'], info['height'])

    intrinsics = info.get('intrinsics', info.get('fov', None))
    if intrinsics is not None:
      cam_intrins = CameraIntrinsics(intrinsics,
                                     info.get('distortion', None),
                                     resolution)

      info['resolution'] = resolution
      pose_formats = [
        ('translation', 'rotation', 'scale'),
        ('camera points', 'map points')
      ]
      if any(keysNotEmpty(info, pose_format) for pose_format in pose_formats):
        self.pose = CameraPose(info, cam_intrins)
      else:
        self.pose = CameraPose(DEFAULT_TRANSFORM, cam_intrins)
    return

  def groundOrigin(self, z=None):
    pt = self.pose.translation
    return Point(pt.x, pt.y, z if z is not None else pt.z)

  def serialize(self):
    data = {
      'uid': self.cameraID,
      'name': self.cameraID,
    }

    # resolution
    # aspect_ratio - does this serve any purpose if resolution is available?
    # rate - of what?

    data['intrinsics'] = self.pose.intrinsics.intrinsics
    data['distortion'] = self.pose.intrinsics.distortion
    data['translation'] = self.pose.translation.asNumpyCartesian.tolist()
    if hasattr(self.pose, 'rotation'):
      data['rotation'] = self.pose.rotation
    data['scale'] = self.pose.scale

    return data
