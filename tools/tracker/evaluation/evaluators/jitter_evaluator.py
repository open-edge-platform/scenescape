# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Jitter evaluator implementation for tracking smoothness metrics.

Evaluates tracker output quality by measuring positional jitter —
the degree of unwanted high-frequency variation in tracked object trajectories.
"""

from typing import Iterator, List, Dict, Any
from pathlib import Path
from datetime import datetime
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from base.tracker_evaluator import TrackerEvaluator


class JitterEvaluator(TrackerEvaluator):
  """Evaluator for tracker smoothness metrics based on positional jitter.

  Jitter metrics quantify high-frequency noise in tracked object trajectories
  by analysing frame-to-frame position changes for each track.

  Supported Metrics:
    - rms_jerk:              Root mean square jerk across all tracks.
    - acceleration_variance: Variance of acceleration magnitudes across all tracks.

  Usage::

    from pathlib import Path
    from evaluators.jitter_evaluator import JitterEvaluator

    evaluator = JitterEvaluator()
    evaluator.configure_metrics(['jitter_mean', 'jitter_max'])
    evaluator.set_output_folder(Path('/path/to/results'))
    evaluator.process_tracker_outputs(tracker_outputs, ground_truth)
    metrics = evaluator.evaluate_metrics()
    print(metrics)
  """

  SUPPORTED_METRICS: List[str] = ['rms_jerk', 'acceleration_variance']

  def __init__(self):
    """Initialize JitterEvaluator."""
    self._metrics: List[str] = []
    self._output_folder: Path = None
    self._processed: bool = False

    # Per-track position history: {track_uuid: [(timestamp, [x, y, z]), ...]}
    self._track_histories: Dict[str, List[tuple]] = {}

  # ------------------------------------------------------------------
  # TrackerEvaluator interface
  # ------------------------------------------------------------------

  def configure_metrics(self, metrics: List[str]) -> 'JitterEvaluator':
    """Configure which jitter metrics to evaluate.

    Args:
      metrics: List of metric names to compute.
                Supported: 'rms_jerk', 'acceleration_variance'.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If any metric name is not supported.
    """
    for metric in metrics:
      if metric not in self.SUPPORTED_METRICS:
        raise ValueError(
          f"Metric '{metric}' not supported. "
          f"Supported metrics: {self.SUPPORTED_METRICS}"
        )
    self._metrics = list(metrics)
    return self

  def set_output_folder(self, path: Path) -> 'JitterEvaluator':
    """Set folder where evaluation outputs should be stored.

    Args:
      path: Path to results folder. Created if it does not exist.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If path is invalid.
    """
    if not isinstance(path, Path):
      path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    self._output_folder = path
    return self

  def process_tracker_outputs(
    self,
    tracker_outputs: Iterator[Dict[str, Any]],
    ground_truth: Iterator[Dict[str, Any]]
  ) -> 'JitterEvaluator':
    """Process tracker outputs and build per-track position histories.

    Reads tracker outputs in canonical format and organises 3-D positions
    by track UUID, sorted by timestamp, ready for jitter calculation.

    Args:
      tracker_outputs: Iterator of tracker output dicts in canonical
        Tracker Output Format (see tools/tracker/evaluation/README.md).
      ground_truth: Ground-truth data (not used by jitter metrics but
        required by the base-class signature).

    Returns:
      Self for method chaining.

    Raises:
      RuntimeError: If no tracker outputs are provided or processing fails.
    """
    try:
      outputs = list(tracker_outputs)
      if not outputs:
        raise RuntimeError("No tracker outputs provided")

      # Deduplicate by timestamp
      seen_timestamps: set = set()
      deduplicated = []
      for frame in outputs:
        ts = frame.get("timestamp")
        if ts in seen_timestamps:
          continue
        seen_timestamps.add(ts)
        deduplicated.append(frame)

      # Build per-track histories
      track_histories: Dict[str, List[tuple]] = {}
      for frame in deduplicated:
        ts_str = frame.get("timestamp", "")
        try:
          ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as exc:
          raise RuntimeError(
            f"Cannot parse timestamp '{ts_str}': {exc}"
          ) from exc

        for obj in frame.get("objects", []):
          track_id = obj.get("id")
          position = obj.get("translation")
          if track_id is None or position is None:
            continue
          if track_id not in track_histories:
            track_histories[track_id] = []
          track_histories[track_id].append((ts, list(position)))

      # Sort each track's positions by timestamp
      for track_id in track_histories:
        track_histories[track_id].sort(key=lambda entry: entry[0])

      self._track_histories = track_histories
      self._processed = True
      return self

    except RuntimeError:
      raise
    except Exception as exc:
      raise RuntimeError(f"Failed to process tracker outputs: {exc}") from exc

  def evaluate_metrics(self) -> Dict[str, float]:
    """Evaluate configured jitter metrics.

    Returns:
      Dictionary mapping metric names to computed float values.

    Raises:
      RuntimeError: If no data has been processed or no metrics configured.
      NotImplementedError: Jitter calculation is not yet implemented.
    """
    if not self._processed:
      raise RuntimeError(
        "No data has been processed. Call process_tracker_outputs() first."
      )
    if not self._metrics:
      raise RuntimeError(
        "No metrics configured. Call configure_metrics() first."
      )

    jitter_per_track = self._compute_jitter_per_track()

    results = {}
    for metric in self._metrics:
      if metric == 'rms_jerk':
        results[metric] = self._compute_rms_jerk(jitter_per_track)
      elif metric == 'acceleration_variance':
        results[metric] = self._compute_acceleration_variance(jitter_per_track)

    if self._output_folder is not None:
      self._save_results(results)

    return results

  def reset(self) -> 'JitterEvaluator':
    """Reset evaluator state to initial configuration.

    Returns:
      Self for method chaining.
    """
    self._metrics = []
    self._output_folder = None
    self._processed = False
    self._track_histories = {}
    return self

  # ------------------------------------------------------------------
  # Internal helpers — metric calculation stubs
  # ------------------------------------------------------------------

  def _compute_jitter_per_track(self) -> Dict[str, Any]:
    """Compute per-track kinematic data from position histories.

    Applies sequential forward finite differences on positions to derive
    velocity, acceleration, and jerk vectors for each track, accounting
    for variable time steps between consecutive frames.

    Minimum track lengths required:
      - 2 points: velocity
      - 3 points: acceleration
      - 4 points: jerk

    Tracks with fewer than 4 points are skipped (no jerk can be calculated).

    Returns:
      Dict mapping track UUID to a dict with keys:
        'jerk_magnitudes':         np.ndarray of scalar jerk magnitudes (m/s³).
                                   Empty array if fewer than 4 points.
        'acceleration_magnitudes': np.ndarray of scalar acceleration magnitudes (m/s²).
                                   Empty array if fewer than 3 points.
    """
    result: Dict[str, Any] = {}

    for track_id, history in self._track_histories.items():
      if len(history) < 3:
        continue

      times = np.array([
        ts.timestamp() for ts, _ in history
      ], dtype=float)  # seconds since epoch

      positions = np.array(
        [pos for _, pos in history], dtype=float
      )  # shape (n, 3)

      # --- velocity: forward difference on positions ---
      # v[i] = (p[i+1] - p[i]) / dt[i],  shape (n-1, 3)
      dt_pos = np.diff(times)              # shape (n-1,)
      velocity = np.diff(positions, axis=0) / dt_pos[:, np.newaxis]

      # midpoint times for velocity samples
      times_v = (times[:-1] + times[1:]) / 2  # shape (n-1,)

      # --- acceleration: forward difference on velocity ---
      # a[i] = (v[i+1] - v[i]) / dt_v[i],  shape (n-2, 3)
      dt_vel = np.diff(times_v)            # shape (n-2,)
      acceleration = np.diff(velocity, axis=0) / dt_vel[:, np.newaxis]
      accel_magnitudes = np.linalg.norm(acceleration, axis=1)  # shape (n-2,)

      # midpoint times for acceleration samples
      times_a = (times_v[:-1] + times_v[1:]) / 2  # shape (n-2,)

      # --- jerk: forward difference on acceleration ---
      # j[i] = (a[i+1] - a[i]) / dt_a[i],  shape (n-3, 3)
      jerk_magnitudes: np.ndarray
      if len(acceleration) >= 2:
        dt_acc = np.diff(times_a)          # shape (n-3,)
        jerk = np.diff(acceleration, axis=0) / dt_acc[:, np.newaxis]
        jerk_magnitudes = np.linalg.norm(jerk, axis=1)  # shape (n-3,)
      else:
        jerk_magnitudes = np.empty(0)

      result[track_id] = {
        'jerk_magnitudes': jerk_magnitudes,
        'acceleration_magnitudes': accel_magnitudes,
      }

    return result

  def _compute_rms_jerk(self, jitter_per_track: Dict[str, Any]) -> float:
    """Compute root mean square jerk across all tracks.

    Collects every jerk magnitude sample from all tracks and returns
    sqrt(mean(jerk²)).

    Args:
      jitter_per_track: Output of _compute_jitter_per_track().

    Returns:
      RMS jerk in m/s³, or 0.0 if no jerk samples are available.
    """
    non_empty = [
      data['jerk_magnitudes']
      for data in jitter_per_track.values()
      if len(data['jerk_magnitudes']) > 0
    ]
    all_jerks = np.concatenate(non_empty) if non_empty else np.empty(0)

    if all_jerks.size == 0:
      return 0.0

    return float(np.sqrt(np.mean(all_jerks ** 2)))

  def _compute_acceleration_variance(self, jitter_per_track: Dict[str, Any]) -> float:
    """Compute variance of acceleration magnitudes across all tracks.

    Collects every acceleration magnitude sample from all tracks and
    returns their variance.

    Args:
      jitter_per_track: Output of _compute_jitter_per_track().

    Returns:
      Acceleration magnitude variance in (m/s²)², or 0.0 if no samples.
    """
    non_empty = [
      data['acceleration_magnitudes']
      for data in jitter_per_track.values()
      if len(data['acceleration_magnitudes']) > 0
    ]
    all_accels = np.concatenate(non_empty) if non_empty else np.empty(0)

    if all_accels.size == 0:
      return 0.0

    return float(np.var(all_accels))

  def _save_results(self, results: Dict[str, float]) -> None:
    """Save metric results to the output folder.

    Writes a plain-text summary file ``jitter_results.txt`` under
    ``self._output_folder``.

    Args:
      results: Metric name → value mapping to persist.
    """
    results_file = self._output_folder / "jitter_results.txt"
    with open(results_file, 'w') as f:
      f.write("Jitter Evaluation Results\n")
      f.write("=" * 40 + "\n")
      for metric, value in results.items():
        f.write(f"{metric}: {value:.6f}\n")
