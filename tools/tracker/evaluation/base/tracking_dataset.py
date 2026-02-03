# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Base class for tracking dataset implementations."""

from abc import ABC, abstractmethod
from typing import Iterator, List, Dict, Any, Optional


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
  def get_scene_config(self) -> Dict[str, Any]:
    """Get scene and camera configuration in canonical format.

    Returns:
      Dictionary conforming to tracker/schema/scene.schema.json.

    Raises:
      RuntimeError: If configuration cannot be loaded or converted.
    """
    pass

  @abstractmethod
  def get_inputs(self, camera: Optional[str] = None) -> Iterator[Dict[str, Any]]:
    """Get input detections in canonical format.

    Args:
      camera: Camera identifier (optional). If None, returns inputs from all cameras.

    Yields:
      Detection dictionaries conforming to tracker/schema/camera-data.schema.json.

    Raises:
      ValueError: If camera identifier is invalid.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def get_ground_truth(self) -> Iterator[Dict[str, Any]]:
    """Get ground-truth tracks in evaluator input format.

    Returns:
      Iterator of ground-truth tracks in MOTChallenge CSV-compatible format.

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
