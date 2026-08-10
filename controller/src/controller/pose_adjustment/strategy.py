# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import Protocol


class PoseAdjustmentStrategy(Protocol):
  def detection_type(self) -> str:
    ...

  def adjust_detections(self, detections: list, scene_name: str, camera, when: float) -> int:
    ...

  def set_max_entry_age_seconds(self, max_entry_age_seconds: float) -> None:
    ...
