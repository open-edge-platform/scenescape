# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Diagnostic evaluator for per-frame location comparison and error analysis.

Computes per-frame location metrics (LOC_T_X, LOC_T_Y, LOC_T_Z, DIST_T) between
matched output tracks and ground-truth tracks using bipartite assignment
that minimizes mean Euclidean distance over overlapping frames. Matching and
DIST_T use x, y and z by default; set_space() restricts them to the ground plane
or the height.
"""

from typing import Iterator, List, Dict, Any, Optional
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from base.tracker_evaluator import TrackerEvaluator
from utils.tracks import match_tracks, position_distance, space_axes


class DiagnosticEvaluator(TrackerEvaluator):
  """Per-frame location comparison and error analysis evaluator.

  Matches output tracks to ground-truth tracks via bipartite assignment
  (minimizing mean Euclidean distance over overlapping frames), then
  produces per-frame CSV files and plots for each configured metric.

  Supported Metrics:
    - LOC_T_X: Per-frame X position of each matched (output, GT) track pair
    - LOC_T_Y: Per-frame Y position of each matched (output, GT) track pair
    - LOC_T_Z: Per-frame Z position of each matched (output, GT) track pair
    - DIST_T: Per-frame Euclidean distance error between each matched pair

  The space ("xyz" by default, "xy" or "z", see set_space()) selects the axes
  of the matching and of DIST_T; LOC_T_X/Y/Z are per axis. Positions without a
  z are measured in the plane.

  evaluate_metrics() returns summary scalars only. Detailed per-frame data
  is written to CSV files in the output folder.
  """

  SUPPORTED_METRICS = ['LOC_T_X', 'LOC_T_Y', 'LOC_T_Z', 'DIST_T']

  def __init__(self):
    """Initialize DiagnosticEvaluator."""
    self._metrics: List[str] = []
    self._output_folder: Path = None
    self._processed: bool = False

    # Per-track data: {track_id: {frame_num: (x, y, z)}}
    self._output_tracks: Dict[str, Dict[int, tuple]] = {}
    self._gt_tracks: Dict[str, Dict[int, tuple]] = {}
    self._base_fps: Optional[float] = None
    self._space: str = 'xyz'

  def set_space(self, space: str) -> 'DiagnosticEvaluator':
    """Set the axes of the track matching and of DIST_T.

    Args:
      space: "xyz" (default), "xy" for the ground plane or "z" for the height.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If space is not supported.
    """
    space_axes(space)
    self._space = space
    return self

  def configure_metrics(self, metrics: List[str]) -> 'DiagnosticEvaluator':
    """Configure which metrics to evaluate.

    Args:
      metrics: List of metric names to compute (e.g., ['LOC_T_X', 'DIST_T']).

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
    self._metrics = metrics
    return self

  def set_output_folder(self, path: Path) -> 'DiagnosticEvaluator':
    """Set folder where evaluation outputs should be stored.

    Args:
      path: Path to results folder. Will be created if it doesn't exist.

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

  def set_base_fps(self, fps=None) -> 'DiagnosticEvaluator':
    """Set base frame rate for timestamp-to-frame-number conversion.

    Args:
      fps: Frames per second (> 0). Required before processing; it is never
        inferred from timestamps. None leaves it unset and processing raises.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If fps is not None and <= 0.
    """
    if fps is not None and fps <= 0:
      raise ValueError("fps must be > 0")
    self._base_fps = fps
    return self

  def process_tracker_outputs(
    self,
    tracker_outputs: Iterator[Dict[str, Any]],
    ground_truth: Iterator[Dict[str, Any]]
  ) -> 'DiagnosticEvaluator':
    """Process tracker outputs and ground-truth for evaluation.

    Parses both inputs into per-track dictionaries keyed by string track ID,
    mapping frame numbers to (x, y, z) positions.

    Args:
      tracker_outputs: Iterator of tracker output dictionaries in canonical
        Tracker Output Format.
      ground_truth: File path string to ground-truth JSONL in canonical
        Tracker Output Format (passed as iterator due to base class signature).

    Returns:
      Self for method chaining.

    Raises:
      RuntimeError: If processing fails.
    """
    try:
      self._parse_inputs(tracker_outputs, ground_truth)
      self._processed = True
      return self
    except Exception as e:
      raise RuntimeError(f"Failed to process tracker outputs: {e}") from e

  def evaluate_metrics(self) -> Dict[str, float]:
    """Evaluate configured metrics.

    Performs bipartite track matching, computes per-frame metrics, writes
    CSV files and plots to the output folder, and returns summary scalars.

    Returns:
      Dictionary mapping metric names to computed summary values:
        - num_matches: Number of matched track pairs
        - DIST_T_mean: Overall mean Euclidean distance (if DIST_T configured)
        - LOC_T_X_mae: Overall mean absolute X error (if LOC_T_X configured)
        - LOC_T_Y_mae: Overall mean absolute Y error (if LOC_T_Y configured)
        - LOC_T_Z_mae: Overall mean absolute Z error (if LOC_T_Z configured);
          NaN when no matched pair has a z

    Raises:
      RuntimeError: If evaluation fails or no data has been processed.
    """
    if not self._processed:
      raise RuntimeError(
        "No data has been processed. Call process_tracker_outputs() first."
      )
    if not self._metrics:
      raise RuntimeError(
        "No metrics configured. Call configure_metrics() first."
      )

    matches = match_tracks(self._output_tracks, self._gt_tracks, self._space)

    location_rows = {axis: [] for axis in range(3)}
    dist_rows = []
    all_distances = []
    axis_errors = {axis: [] for axis in range(3)}

    for output_id, gt_id in matches:
      out_track = self._output_tracks[output_id]
      gt_track = self._gt_tracks[gt_id]
      union_frames = sorted(set(out_track) | set(gt_track))

      for frame in union_frames:
        out_pos = out_track.get(frame)
        gt_pos = gt_track.get(frame)

        # NaN where a position or its z is missing.
        out_values = [self._axis_value(out_pos, axis) for axis in range(3)]
        gt_values = [self._axis_value(gt_pos, axis) for axis in range(3)]

        if out_pos and gt_pos:
          dist = position_distance(out_pos, gt_pos, self._space)
          all_distances.append(dist)
          for axis in range(3):
            if not np.isnan(out_values[axis] + gt_values[axis]):
              axis_errors[axis].append(abs(out_values[axis] - gt_values[axis]))
        else:
          dist = float('nan')

        for axis in range(3):
          location_rows[axis].append({
            'frame_id': frame, 'track_id': output_id, 'gt_id': gt_id,
            'value_track': out_values[axis], 'value_gt': gt_values[axis]
          })
        dist_rows.append({
          'frame_id': frame, 'track_id': output_id, 'gt_id': gt_id,
          'distance': dist
        })

    if self._output_folder:
      self._write_outputs(*location_rows.values(), dist_rows)

    results = {'num_matches': float(len(matches))}
    if 'DIST_T' in self._metrics:
      results['DIST_T_mean'] = (
        float(np.mean(all_distances)) if all_distances else 0.0
      )
    for axis, name in enumerate('XYZ'):
      if f'LOC_T_{name}' in self._metrics:
        # Z has no samples for planar data: NaN, not a perfect 0.0.
        empty = float('nan') if name == 'Z' else 0.0
        results[f'LOC_T_{name}_mae'] = (
          float(np.mean(axis_errors[axis])) if axis_errors[axis] else empty
        )
    return results

  def reset(self) -> 'DiagnosticEvaluator':
    """Reset evaluator state to initial configuration.

    Returns:
      Self for method chaining.
    """
    self._metrics = []
    self._output_folder = None
    self._processed = False
    self._output_tracks = {}
    self._gt_tracks = {}
    self._base_fps = None
    self._space = 'xyz'
    return self

  # --- Private helpers ---

  @staticmethod
  def _axis_value(position, axis):
    """Coordinate `axis` (x=0, y=1, z=2) of a position; NaN if it lacks it."""
    return position[axis] if position and len(position) > axis else float('nan')

  def _parse_inputs(self, tracker_outputs, ground_truth):
    """Parse tracker outputs and ground truth onto a shared time grid.

    Both tracker output and ground truth carry absolute ISO timestamps. They
    are quantized onto a common frame grid using a shared reference epoch so
    that track-vs-ground-truth matching is timestamp-based.
    """
    from utils.format_converters import stream_jsonl
    from utils.timeline import (
      deduplicate_frames_by_timestamp,
      ingest_frames,
      reference_timestamp,
      require_fps,
      resolve_ground_truth_path,
    )

    tracker_output_list = list(tracker_outputs)
    if not tracker_output_list:
      raise RuntimeError("No tracker outputs provided")
    tracker_output_list = deduplicate_frames_by_timestamp(tracker_output_list)

    gt_frames = list(stream_jsonl(resolve_ground_truth_path(ground_truth)))

    # Shared reference epoch and frame rate for both inputs.
    reference = reference_timestamp(tracker_output_list, gt_frames)
    camera_fps = require_fps(self._base_fps)

    ingest_frames(tracker_output_list, self._output_tracks, reference, camera_fps)
    ingest_frames(gt_frames, self._gt_tracks, reference, camera_fps)

  def _write_outputs(self, loc_x_rows, loc_y_rows, loc_z_rows, dist_rows):
    """Write CSV files and plots for configured metrics."""
    for name, rows in (('X', loc_x_rows), ('Y', loc_y_rows), ('Z', loc_z_rows)):
      metric = f'LOC_T_{name}'
      if metric in self._metrics:
        df = pd.DataFrame(rows,
                           columns=['frame_id', 'track_id', 'gt_id',
                                    'value_track', 'value_gt'])
        df.to_csv(self._output_folder / f'{metric}.csv', index=False)
        if not df.empty:
          self._plot_location_metric(df, metric, f'{name} Position')

    if 'DIST_T' in self._metrics:
      df = pd.DataFrame(dist_rows,
                         columns=['frame_id', 'track_id', 'gt_id',
                                  'distance'])
      df.to_csv(self._output_folder / 'DIST_T.csv', index=False)
      if not df.empty:
        self._plot_distance_metric(df, 'DIST_T')

  def _plot_location_metric(self, df, metric_name, ylabel):
    """Plot location metric for all matched pairs."""
    fig, ax = plt.subplots(figsize=(12, 6))
    for (oid, gid), group in df.groupby(['track_id', 'gt_id']):
      ax.plot(group['frame_id'], group['value_track'],
              label=f'Track {oid}', linestyle='-')
      ax.plot(group['frame_id'], group['value_gt'],
              label=f'GT {gid}', linestyle='--')
    ax.set_xlabel('Frame')
    ax.set_ylabel(ylabel)
    ax.set_title(f'{metric_name}: Track vs Ground Truth')
    ax.legend(fontsize='small')
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(self._output_folder / f'{metric_name}.png', dpi=150)
    plt.close(fig)

  def _plot_distance_metric(self, df, metric_name):
    """Plot distance metric for all matched pairs."""
    fig, ax = plt.subplots(figsize=(12, 6))
    for (oid, gid), group in df.groupby(['track_id', 'gt_id']):
      ax.plot(group['frame_id'], group['distance'],
              label=f'Track {oid} vs GT {gid}')
    ax.set_xlabel('Frame')
    ax.set_ylabel('Euclidean Distance (m)')
    ax.set_title(f'{metric_name}: Per-Frame Distance Error')
    ax.legend(fontsize='small')
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(self._output_folder / f'{metric_name}.png', dpi=150)
    plt.close(fig)
