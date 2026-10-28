# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Process-wide access to the active PTZ pose registry.

Scenes are rebuilt whenever Manager data refreshes, so they cannot hold the
registry themselves without a window in which a rebuilt scene would silently fall
back to the static home pose. They ask this holder instead.
"""

from typing import Any, Optional

from controller.ptz.registry import PTZPoseRegistry

_active: Optional[PTZPoseRegistry] = None


def set_active_registry(registry: Optional[PTZPoseRegistry]) -> None:
  global _active
  _active = registry


def active_registry() -> Optional[PTZPoseRegistry]:
  return _active


def visibility_camera(camera: Any) -> Optional[Any]:
  """Camera to evaluate visibility with; None when a PTZ camera currently sees nothing."""
  registry = _active
  if registry is None:
    return camera
  return registry.visibility_camera(camera)
