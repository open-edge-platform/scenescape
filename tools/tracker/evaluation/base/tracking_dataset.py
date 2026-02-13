# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Base class for tracking dataset implementations."""

from abc import ABC, abstractmethod
from typing import Iterator, List, Dict, Any, Optional
from pathlib import Path


class TrackingDataset(ABC):
  """Base class for tracking dataset implementations.

  A tracking dataset provides:
  - Scene and camera configuration in canonical format
  - Input data (videos or object detections) from multiple cameras
  - Ground-truth object locations for evaluation

  Implementations must convert dataset-specific formats to SceneScape canonical formats.
  """

  @abstractmethod
  def set_scene(self, scene: Optional[str] = None) -> 'TrackingDataset':
    """Set the scene to use from the dataset.

    Args:
      scene: Scene identifier (optional). If None, uses default/first scene.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If scene identifier is invalid.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def set_cameras(self, cameras: Optional[List[str]] = None) -> 'TrackingDataset':
    """Set the cameras to use from the scene.

    Args:
      cameras: List of camera identifiers (optional). If None, uses all available cameras.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If camera identifiers are invalid.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def set_time_range(
    self,
    start: Optional[str] = None,
    end: Optional[str] = None
  ) -> 'TrackingDataset':
    """Set the time range for input sequences.

    Args:
      start: Start timestamp (optional). Format depends on implementation.
      end: End timestamp (optional). Format depends on implementation.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If timestamps are invalid or start > end.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def set_camera_fps(self, camera_fps: float) -> 'TrackingDataset':
    """Set the camera frame rate for input sequences.

    Args:
      camera_fps: Camera frames per second.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If camera_fps is invalid or not supported.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def set_custom_config(self, config: Dict[str, Any]) -> 'TrackingDataset':
    """Set custom dataset-specific configuration.

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
  def set_output_folder(self, path: Path) -> 'TrackingDataset':
    """Set folder where dataset-specific outputs should be stored.

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
  def get_scene_config(self) -> Dict[str, Any]:
    """Get scene and camera configuration in dataset-specific format.

    TODO: This currently returns dataset-specific format. In the future, when
    scene configuration schemas are fully stabilized, this should return the
    canonical Scene Configuration Format.

    Returns:
      Dictionary with scene configuration (format depends on implementation).

    Raises:
      RuntimeError: If configuration cannot be loaded.
    """
    pass

  @abstractmethod
  def get_inputs(self, camera: Optional[str] = None) -> Iterator[Dict[str, Any]]:
    """Get input detections in canonical format, sorted by timestamp.

    Args:
      camera: Camera identifier (optional). If None, returns inputs from all cameras.

    Yields:
      Detection dictionaries conforming to Input Detection Format
      (see tools/tracker/evaluation/README.md#canonical-data-formats).
      Frames are yielded in chronological order (sorted by timestamp) across all cameras.

    Raises:
      ValueError: If camera identifier is invalid.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def get_ground_truth(self) -> str:
    """Get ground-truth data in evaluator input format.

    Returns:
      Path to ground-truth file in Ground Truth Format (MOTChallenge 3D CSV)
      (see tools/tracker/evaluation/README.md#canonical-data-formats).

    Raises:
      RuntimeError: If ground-truth cannot be loaded or converted.
    """
    pass

  @abstractmethod
  def reset(self) -> 'TrackingDataset':
    """Reset dataset state to initial configuration.

    Returns:
      Self for method chaining.
    """
    pass
