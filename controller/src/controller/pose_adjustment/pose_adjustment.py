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


def _normalize_detection_type(detection_type: str) -> str:
  return detection_type.strip().lower()


def _normalize_route_labels(strategy_type: str, parsed: object) -> list[str]:
  normalized_strategy_type = _normalize_detection_type(strategy_type)
  if not normalized_strategy_type:
    return []

  if parsed is None:
    return [normalized_strategy_type]
  if not isinstance(parsed, list):
    log.warning(
      f"Ignoring pose adjustment route for {strategy_type!r}: expected a list of labels"
    )
    return [normalized_strategy_type]

  labels = [normalized_strategy_type]
  seen = {normalized_strategy_type}
  for label in parsed:
    if not isinstance(label, str):
      log.warning(
        f"Ignoring non-string pose adjustment route entry for {strategy_type!r}: {label!r}"
      )
      continue
    normalized_label = _normalize_detection_type(label)
    if not normalized_label or normalized_label in seen:
      continue
    labels.append(normalized_label)
    seen.add(normalized_label)
  return labels


def _extract_routing_config(
  pose_adjustment_config_data: Optional[dict],
) -> dict[str, list[str]]:
  if pose_adjustment_config_data is None:
    return {}
  if not isinstance(pose_adjustment_config_data, dict):
    log.warning("Ignoring pose adjustment config: expected a JSON object")
    return {}

  routes = {}
  for strategy_type, labels in pose_adjustment_config_data.items():
    if not isinstance(strategy_type, str):
      log.warning(f"Ignoring non-string pose adjustment route key: {strategy_type!r}")
      continue
    normalized_strategy_type = _normalize_detection_type(strategy_type)
    if not normalized_strategy_type:
      continue
    routes[normalized_strategy_type] = _normalize_route_labels(strategy_type, labels)
  return routes

class PoseAdjustment:
  """Coordinates pose adjustment strategies by detection type."""

  def __init__(
    self,
    enabled: bool,
    max_entry_age_seconds: float,
    strategies: Optional[Iterable[PoseAdjustmentStrategy]] = None,
    detection_type_routes: Optional[dict[str, list[str]]] = None,
  ):
    self.enabled = enabled
    self._strategies: dict[str, PoseAdjustmentStrategy] = {}
    self._resolved_detection_types: dict[str, str] = {}
    self._detection_type_routes = detection_type_routes or {}
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
    pose_adjustment_config_data: Optional[dict] = None,
    detection_type_routes: Optional[dict[str, list[str]]] = None,
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

    routes = _extract_routing_config(pose_adjustment_config_data)
    if detection_type_routes is not None:
      routes.update({
        _normalize_detection_type(strategy_type): _normalize_route_labels(strategy_type, labels)
        for strategy_type, labels in detection_type_routes.items()
        if isinstance(strategy_type, str)
      })

    return cls(
      enabled=enabled,
      max_entry_age_seconds=max_entry_age_seconds,
      strategies=strategies,
      detection_type_routes=routes,
    )

  def register_strategy(self, strategy: PoseAdjustmentStrategy) -> None:
    detection_type = _normalize_detection_type(strategy.detection_type())
    self._strategies[detection_type] = strategy
    self._rebuild_detection_type_routes()

  def supported_detection_types(self) -> list[str]:
    return sorted(self._strategies.keys())

  def set_max_entry_age_seconds(self, max_entry_age_seconds: float) -> None:
    for strategy in self._strategies.values():
      strategy.set_max_entry_age_seconds(max_entry_age_seconds)

  def adjust_detections(self, detection_type: str, detections: list, scene_name: str, camera, when: float) -> int:
    if not self.enabled:
      return 0

    normalized_detection_type = _normalize_detection_type(detection_type)
    strategy_type = self._resolved_detection_types.get(normalized_detection_type)
    if strategy_type is None:
      return 0

    strategy = self._strategies.get(strategy_type)
    if strategy is None:
      return 0

    return strategy.adjust_detections(detections, scene_name, camera, when)

  def _rebuild_detection_type_routes(self) -> None:
    resolved_detection_types = {}
    for strategy_type, labels in self._detection_type_routes.items():
      if strategy_type not in self._strategies:
        continue
      for label in labels:
        resolved_detection_types[_normalize_detection_type(label)] = strategy_type

    for strategy_type in self._strategies.keys():
      resolved_detection_types[strategy_type] = strategy_type

    self._resolved_detection_types = resolved_detection_types
