# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Protocol

from scene_common import log

from controller.pose_adjustment.bbox_adjuster import PersonPoseAdjuster


POSE_ADJUSTMENT_ENV_VAR = 'CONTROLLER_ENABLE_POSE_ADJUSTMENT'


def _env_bool(name: str, default: bool) -> bool:
  value = os.getenv(name)
  if value is None:
    return default
  return value.strip().lower() in ('1', 'true', 'yes', 'on')


class PoseAdjustmentStrategy(Protocol):
  def detection_type(self) -> str:
    ...

  def supports_detection(self, detection_type: str) -> bool:
    ...

  def adjust_detections(self, detections: list, scene_name: str, camera, when: float) -> int:
    ...

  def set_max_entry_age_seconds(self, max_entry_age_seconds: float) -> None:
    ...


class PersonPoseAdjustmentStrategy:
  """Pose adjustment strategy for person detections."""

  def __init__(self, max_entry_age_seconds: float):
    self._adjuster = PersonPoseAdjuster(max_entry_age_seconds=max_entry_age_seconds)

  def detection_type(self) -> str:
    return 'person'

  def supports_detection(self, detection_type: str) -> bool:
    return detection_type == 'person'

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


class PoseAdjustment:
  """Coordinates pose adjustment strategies by detection type."""

  def __init__(self, enabled: bool, max_entry_age_seconds: float):
    self.enabled = enabled
    self._strategies = {
      strategy.detection_type(): strategy
      for strategy in [
        PersonPoseAdjustmentStrategy(max_entry_age_seconds=max_entry_age_seconds),
      ]
    }

  @classmethod
  def from_env(cls, max_entry_age_seconds: float, default_enabled: bool = True):
    enabled = default_enabled
    if os.getenv(POSE_ADJUSTMENT_ENV_VAR) is not None:
      enabled = _env_bool(POSE_ADJUSTMENT_ENV_VAR, default_enabled)
      source = POSE_ADJUSTMENT_ENV_VAR
    else:
      source = None

    if not enabled:
      if source is not None:
        log.info(f"Pose adjustment DISABLED via {source}")
      else:
        log.info("Pose adjustment DISABLED")

    return cls(enabled=enabled, max_entry_age_seconds=max_entry_age_seconds)

  def set_max_entry_age_seconds(self, max_entry_age_seconds: float) -> None:
    for strategy in self._strategies.values():
      strategy.set_max_entry_age_seconds(max_entry_age_seconds)

  def adjust_detections(self, detection_type: str, detections: list, scene_name: str, camera, when: float) -> int:
    if not self.enabled:
      return 0

    strategy = self._strategies.get(detection_type)
    if strategy is None:
      return 0

    return strategy.adjust_detections(detections, scene_name, camera, when)
