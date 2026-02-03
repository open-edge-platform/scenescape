# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Base class for tracker harness implementations."""

from abc import ABC, abstractmethod
from typing import Iterator, Dict, Any, Callable, Optional


class TrackerHarness(ABC):
  """Base class for tracker harness implementations.

  A tracker harness executes a tracking system and produces tracker outputs.
  It consumes:
  - Scene and camera configuration in canonical format
  - Input detections or videos in canonical format
  - Tracker-specific configuration

  It produces:
  - Tracker outputs (tracks) in canonical format
  """

  @abstractmethod
  def set_scene_config(self, config: Dict[str, Any]) -> 'TrackerHarness':
    """Set scene and camera configuration.

    Args:
      config: Scene configuration conforming to tracker/schema/scene.schema.json.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If configuration is invalid.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def set_custom_config(self, config: Dict[str, Any]) -> 'TrackerHarness':
    """Set tracker-specific configuration.

    Args:
      config: Custom configuration dictionary (format depends on implementation).

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If configuration is invalid.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def set_callback_outputs_ready(
    self,
    callback: Callable[[Iterator[Dict[str, Any]]], None]
  ) -> 'TrackerHarness':
    """Set callback function to be called when tracker outputs are ready.

    Args:
      callback: Function that receives an iterator of tracker outputs.
        Each output conforms to tracker/schema/scene-data.schema.json.

    Returns:
      Self for method chaining.
    """
    pass

  @abstractmethod
  def set_callback_on_failure(
    self,
    callback: Callable[[str, str], None]
  ) -> 'TrackerHarness':
    """Set callback function to be called when failure occurs.

    Args:
      callback: Function that receives (timestamp, error_message).

    Returns:
      Self for method chaining.
    """
    pass

  @abstractmethod
  def process_inputs(self, inputs: Iterator[Dict[str, Any]]) -> 'TrackerHarness':
    """Process input detections through the tracker.

    Args:
      inputs: Iterator of detection dictionaries conforming to
        tracker/schema/camera-data.schema.json.

    Returns:
      Self for method chaining.

    Raises:
      RuntimeError: If processing fails.
    """
    pass

  @abstractmethod
  def reset(self) -> 'TrackerHarness':
    """Reset harness state to initial configuration.

    Returns:
      Self for method chaining.
    """
    pass
