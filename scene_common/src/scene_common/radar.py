# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pose-only radar sensor used by the Controller for 3-D detection transforms."""

from scene_common.camera import DEFAULT_TRANSFORM, keysNotEmpty
from scene_common.transform import CameraPose


class Radar:
  """First-class radar sensor with scene extrinsics and no imaging intrinsics."""

  def __init__(self, an_id, info):
    self.cameraID = an_id  # MovingObject expects cameraID on the sensor
    self.radarID = an_id
    self.sensorID = an_id

    pose_formats = [
      ('translation', 'rotation', 'scale'),
      ('translation', 'rotation'),
    ]
    if any(keysNotEmpty(info, pose_format) for pose_format in pose_formats):
      pose_info = {
        'translation': info.get('translation', DEFAULT_TRANSFORM['translation']),
        'rotation': info.get('rotation', DEFAULT_TRANSFORM['rotation']),
        'scale': info.get('scale', DEFAULT_TRANSFORM['scale']),
      }
      self.pose = CameraPose(pose_info, None)
    elif keysNotEmpty(info, ('transforms',)) or info.get('transform_type'):
      # Fall back to flat transforms array via CameraPose.arrayToDictionary
      from scene_common.transform import CameraPose as CP
      mapped = CP.arrayToDictionary(
        info.get('transforms', []),
        info.get('transform_type', 'euler'),
      )
      if mapped:
        self.pose = CameraPose(mapped, None)
    return

  def serialize(self):
    data = {
      'uid': self.radarID,
      'name': self.radarID,
    }
    if hasattr(self, 'pose'):
      data['translation'] = self.pose.translation.asNumpyCartesian.tolist()
      if hasattr(self.pose, 'rotation'):
        data['rotation'] = self.pose.rotation
      data['scale'] = self.pose.scale
    return data
