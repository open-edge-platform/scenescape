# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Base class for tracker evaluator implementations."""

from abc import ABC, abstractmethod
from typing import Iterator, List, Dict, Any
from pathlib import Path


class TrackerEvaluator(ABC):
  """Base class for tracker evaluator implementations.

  A tracker evaluator computes tracking quality metrics by comparing
  tracker outputs against ground-truth data.

  It consumes:
  - Tracker outputs in canonical format
  - Ground-truth tracks in evaluator-specific format

  It produces:
  - Metrics dictionary
  - Optional plots and detailed results
  """

  @abstractmethod
  def configure_metrics(self, metrics: List[str]) -> 'TrackerEvaluator':
    """Configure which metrics to evaluate.

    Args:
      metrics: List of metric names to compute (e.g., ['HOTA', 'MOTA', 'IDF1']).

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If any metric name is not supported.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def set_output_folder(self, path: Path) -> 'TrackerEvaluator':
    """Set folder where evaluation outputs should be stored.

    Args:
      path: Path to results folder. Will be created if it doesn't exist.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If path is invalid.
      RuntimeError: On other errors.
    """
    pass

  @abstractmethod
  def process_tracker_outputs(
    self,
    tracker_outputs: Iterator[Dict[str, Any]],
    ground_truth: Iterator[Dict[str, Any]]
  ) -> 'TrackerEvaluator':
    """Process tracker outputs and ground-truth for evaluation.

    Args:
      tracker_outputs: Iterator of tracker output dictionaries in canonical Tracker Output Format
        (see tools/tracker/evaluation/README.md#canonical-data-formats).
      ground_truth: Iterator of ground-truth tracks in evaluator-specific format.

    Returns:
      Self for method chaining.

    Raises:
      RuntimeError: If processing fails.
    """
    pass

  @abstractmethod
  def evaluate_metrics(self) -> Dict[str, float]:
    """Evaluate configured metrics.

    Returns:
      Dictionary mapping metric names to computed values.

    Raises:
      RuntimeError: If evaluation fails or no data has been processed.
    """
    pass

  @abstractmethod
  def reset(self) -> 'TrackerEvaluator':
    """Reset evaluator state to initial configuration.

    Returns:
      Self for method chaining.
    """
    pass
