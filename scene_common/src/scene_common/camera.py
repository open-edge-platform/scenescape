# SPDX-FileCopyrightText: (C) 2021 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common.geometry import Point
from scene_common.options import (
  provenance_from_camera_info,
  sync_legacy_pose_source,
)
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


def _pose_locked_from_info(info):
  if 'pose_locked' not in info:
    return False
  value = info['pose_locked']
  if not isinstance(value, bool) and value not in (0, 1):
    raise ValueError('pose_locked must be a boolean')
  return bool(value)


def _camera_pose_from_info(info, cam_intrins):
  pose_formats = [
    ('translation', 'rotation', 'scale'),
    ('camera points', 'map points')
  ]
  if any(keysNotEmpty(info, pose_format) for pose_format in pose_formats):
    return CameraPose(info, cam_intrins)
  return CameraPose(DEFAULT_TRANSFORM, cam_intrins)


class Camera:
  def __init__(self, anID, info, resolution=None):
    self.cameraID = anID
    self.pose_locked = _pose_locked_from_info(info)
    # Untagged payloads stay unknown; Manager stamps origin on authored config.
    self.pose_provenance = provenance_from_camera_info(info)
    sync_legacy_pose_source(self)
    # PTZ cameras carry a Manager-owned calibration block; its presence marks the camera as PTZ
    ptz_calibration = info.get('ptz_calibration')
    self.ptz_calibration = ptz_calibration if isinstance(ptz_calibration, dict) else None

    if resolution is None and 'width' in info and 'height' in info:
      resolution = (info['width'], info['height'])

    intrinsics = info.get('intrinsics', info.get('fov', None))
    if intrinsics is not None:
      cam_intrins = CameraIntrinsics(intrinsics,
                                     info.get('distortion', None),
                                     resolution)
      info['resolution'] = resolution
      self.pose = _camera_pose_from_info(info, cam_intrins)
    return

  def groundOrigin(self, z=None):
    pt = self.pose.translation
    return Point(pt.x, pt.y, z if z is not None else pt.z)

  def serialize(self):
    data = {
      'uid': self.cameraID,
      'name': self.cameraID,
      'pose_locked': self.pose_locked,
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
