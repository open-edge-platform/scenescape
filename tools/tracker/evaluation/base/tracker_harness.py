# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Base class for tracker harness implementations."""

from abc import ABC, abstractmethod
from typing import Iterator, Dict, Any
from pathlib import Path


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
      config: Scene configuration in canonical Scene Configuration Format
        (see tools/tracker/evaluation/README.md#canonical-data-formats).

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
  def set_output_folder(self, path: Path) -> 'TrackerHarness':
    """Set folder where harness-specific outputs should be stored.

    Args:
      path: Path to output folder. Will be created if it doesn't exist.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If path is invalid.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def process_inputs(self, inputs: Iterator[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    """Process input detections through the tracker synchronously.

    This is the default (synchronous) mode. Processes all inputs and returns outputs.
    Use this for batch processing, testing, and simple evaluation pipelines.

    Args:
      inputs: Iterator of detection dictionaries in canonical Input Detection Format
        (see tools/tracker/evaluation/README.md#canonical-data-formats).

    Returns:
      Iterator of tracker outputs in canonical Tracker Output Format.

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
