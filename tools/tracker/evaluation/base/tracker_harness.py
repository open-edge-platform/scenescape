# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
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
  def set_callback_outputs_ready(
    self,
    callback: Callable[[Iterator[Dict[str, Any]]], None]
  ) -> 'TrackerHarness':
    """Set callback function to be called when tracker outputs are ready.

    Note: Only used by process_inputs_async(). Not needed for process_inputs().

    Args:
      callback: Function that receives an iterator of tracker outputs in canonical
        Tracker Output Format (see tools/tracker/evaluation/README.md#canonical-data-formats).

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

    Note: Only used by process_inputs_async(). Not needed for process_inputs().

    Args:
      callback: Function that receives (timestamp, error_message).

    Returns:
      Self for method chaining.
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
  def process_inputs_async(self, inputs: Iterator[Dict[str, Any]]) -> 'TrackerHarness':
    """Process input detections through the tracker asynchronously.

    This is the asynchronous (non-blocking) mode. Results are delivered via callbacks
    set with set_callback_outputs_ready(). Use this for streaming pipelines or
    when integrating with async frameworks.

    Callbacks must be set before calling this method:
    - set_callback_outputs_ready() - required
    - set_callback_on_failure() - optional

    Args:
      inputs: Iterator of detection dictionaries in canonical Input Detection Format
        (see tools/tracker/evaluation/README.md#canonical-data-formats).

    Returns:
      Self for method chaining.

    Raises:
      RuntimeError: If processing fails or callbacks not set.
      NotImplementedError: If async mode not supported by this harness.
    """
    pass

  @abstractmethod
  def reset(self) -> 'TrackerHarness':
    """Reset harness state to initial configuration.

    Returns:
      Self for method chaining.
    """
    pass
