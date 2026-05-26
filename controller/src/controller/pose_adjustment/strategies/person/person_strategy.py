# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log

from controller.pose_adjustment.strategies.person.bbox_adjuster import PersonPoseAdjuster


class PersonPoseAdjustmentStrategy:
  """Pose adjustment strategy for person detections."""

  def __init__(self, max_entry_age_seconds: float):
    self._adjuster = PersonPoseAdjuster(max_entry_age_seconds=max_entry_age_seconds)

  def detection_type(self) -> str:
    return 'person'

  def set_max_entry_age_seconds(self, max_entry_age_seconds: float) -> None:
    self._adjuster.set_max_entry_age_seconds(max_entry_age_seconds)

  def adjust_detections(self, detections: list, scene_name: str, camera, when: float) -> int:
    if not detections:
      return 0

    resolution = getattr(getattr(camera, 'pose', None), 'resolution', None)
    if resolution is None and hasattr(camera.pose, 'intrinsics'):
      resolution = camera.pose.intrinsics.getResolutionFromIntrinsics()
    if resolution is not None:
      resolution = tuple(resolution)

    adjusted_count = 0
    for detection in detections:
      if not isinstance(detection, dict):
        continue
      if self._adjuster.adjust_detection(
        detection,
        scene_name,
        camera.cameraID,
        when,
        resolution,
      ):
        adjusted_count += 1

    log.debug(
      f"Pose adjustment batch for scene {scene_name}, camera {camera.cameraID}: "
      f"detections={len(detections)}, adjusted={adjusted_count}, resolution={resolution}"
    )
    return adjusted_count
