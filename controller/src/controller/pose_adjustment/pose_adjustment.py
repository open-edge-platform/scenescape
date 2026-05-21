# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Iterable, Optional

from scene_common import log

from controller.pose_adjustment.strategy import PoseAdjustmentStrategy
from controller.pose_adjustment.strategies.person import PersonPoseAdjustmentStrategy


POSE_ADJUSTMENT_ENV_VAR = 'CONTROLLER_ENABLE_POSE_ADJUSTMENT'


def _env_bool(name: str, default: bool) -> bool:
  value = os.getenv(name)
  if value is None:
    return default
  return value.strip().lower() in ('1', 'true', 'yes', 'on')

class PoseAdjustment:
  """Coordinates pose adjustment strategies by detection type."""

  def __init__(
    self,
    enabled: bool,
    max_entry_age_seconds: float,
    strategies: Optional[Iterable[PoseAdjustmentStrategy]] = None,
  ):
    self.enabled = enabled
    self._strategies: dict[str, PoseAdjustmentStrategy] = {}
    if strategies is None:
      strategies = [
        PersonPoseAdjustmentStrategy(max_entry_age_seconds=max_entry_age_seconds),
      ]
    for strategy in strategies:
      self.register_strategy(strategy)

  @classmethod
  def from_env(
    cls,
    max_entry_age_seconds: float,
    default_enabled: bool = True,
    strategies: Optional[Iterable[PoseAdjustmentStrategy]] = None,
  ):
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

    return cls(
      enabled=enabled,
      max_entry_age_seconds=max_entry_age_seconds,
      strategies=strategies,
    )

  def register_strategy(self, strategy: PoseAdjustmentStrategy) -> None:
    self._strategies[strategy.detection_type()] = strategy

  def supported_detection_types(self) -> list[str]:
    return sorted(self._strategies.keys())

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
