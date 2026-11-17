# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared/deployment slice of the PTZ positioning configuration contract.

Only values the pose consumers (Controller, Tracker) hold themselves are
validated here. Positioning-only runtime settings are validated by the
Positioning service.
"""

import math
from dataclasses import dataclass
from typing import Any, Mapping

CONSUMER_CONFIG_KEYS = (
  "max_pose_age_s",
  "max_clock_offset_s",
  "max_detection_pipeline_latency_s",
  "max_detection_timestamp_uncertainty_s",
)


class PositioningConfigError(ValueError):
  """Raised when the shared positioning configuration is missing or invalid."""


@dataclass(frozen=True)
class ConsumerPositioningConfig:
  max_pose_age_s: float
  max_clock_offset_s: float
  max_detection_pipeline_latency_s: float
  max_detection_timestamp_uncertainty_s: float


def load_consumer_config(values: Mapping[str, Any]) -> ConsumerPositioningConfig:
  """Validate the deployment-owned values; all are required, none defaulted.

  Keys outside the shared slice are ignored.
  """
  missing = [key for key in CONSUMER_CONFIG_KEYS if values.get(key) is None]
  if missing:
    raise PositioningConfigError(f"Missing required positioning configuration: {missing}")
  parsed = {key: _finite(values[key], key) for key in CONSUMER_CONFIG_KEYS}
  for key in ("max_pose_age_s", "max_clock_offset_s", "max_detection_pipeline_latency_s"):
    if parsed[key] <= 0.0:
      raise PositioningConfigError(f"{key} must be > 0")
  if parsed["max_detection_timestamp_uncertainty_s"] < 0.0:
    raise PositioningConfigError("max_detection_timestamp_uncertainty_s must be >= 0")
  return ConsumerPositioningConfig(**parsed)


def _finite(value, key: str) -> float:
  if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
    raise PositioningConfigError(f"{key} must be a finite number")
  return float(value)
