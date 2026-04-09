# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Diagnostic evaluator for per-frame location comparison and error analysis.

Computes per-frame location metrics (LOC_T_X, LOC_T_Y, DIST_T) between
matched output tracks and ground-truth tracks using bipartite assignment
that minimizes mean Euclidean distance over overlapping frames.
"""

from typing import Iterator, List, Dict, Any
from pathlib import Path
from datetime import datetime
import sys
import math

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.optimize import linear_sum_assignment

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from base.tracker_evaluator import TrackerEvaluator

# Minimum number of overlapping frames required for a valid track match.
# Pairs with fewer overlapping frames receive infinite cost and are excluded.
MIN_OVERLAP_FRAMES = 10


class DiagnosticEvaluator(TrackerEvaluator):
  """Per-frame location comparison and error analysis evaluator.

  Matches output tracks to ground-truth tracks via bipartite assignment
  (minimizing mean Euclidean distance over overlapping frames), then
  produces per-frame CSV files and plots for each configured metric.

  Supported Metrics:
    - LOC_T_X: Per-frame X position of each matched (output, GT) track pair
    - LOC_T_Y: Per-frame Y position of each matched (output, GT) track pair
    - DIST_T: Per-frame Euclidean distance error between each matched pair

  evaluate_metrics() returns summary scalars only. Detailed per-frame data
  is written to CSV files in the output folder.
  """

  SUPPORTED_METRICS = ['LOC_T_X', 'LOC_T_Y', 'DIST_T']

  def __init__(self):
    """Initialize DiagnosticEvaluator."""
    self._metrics: List[str] = []
    self._output_folder: Path = None
    self._processed: bool = False

    # Per-track data: {int_id: {frame_num: (x, y)}}
    self._output_tracks: Dict[int, Dict[int, tuple]] = {}
    self._gt_tracks: Dict[int, Dict[int, tuple]] = {}
    self._uuid_to_id_map: Dict[str, int] = {}

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

  def process_tracker_outputs(
    self,
    tracker_outputs: Iterator[Dict[str, Any]],
    ground_truth: Iterator[Dict[str, Any]]
  ) -> 'DiagnosticEvaluator':
    """Process tracker outputs and ground-truth for evaluation.

    Parses both inputs into per-track dictionaries keyed by integer track ID,
    mapping frame numbers to (x, y) positions.

    Args:
      tracker_outputs: Iterator of tracker output dictionaries in canonical
        Tracker Output Format.
      ground_truth: File path string to ground-truth CSV in MOTChallenge 3D
        format (passed as iterator due to base class signature).

    Returns:
      Self for method chaining.

    Raises:
      RuntimeError: If processing fails.
    """
    try:
      self._parse_tracker_outputs(tracker_outputs)
      self._parse_ground_truth(ground_truth)
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

    matches = self._match_tracks()

    loc_x_rows = []
    loc_y_rows = []
    dist_rows = []
    all_distances = []
    all_x_errors = []
    all_y_errors = []

    for output_id, gt_id in matches:
      out_track = self._output_tracks[output_id]
      gt_track = self._gt_tracks[gt_id]
      union_frames = sorted(set(out_track) | set(gt_track))

      for frame in union_frames:
        out_pos = out_track.get(frame)
        gt_pos = gt_track.get(frame)

        out_x = out_pos[0] if out_pos else float('nan')
        out_y = out_pos[1] if out_pos else float('nan')
        gt_x = gt_pos[0] if gt_pos else float('nan')
        gt_y = gt_pos[1] if gt_pos else float('nan')

        if out_pos and gt_pos:
          dist = math.sqrt((out_x - gt_x) ** 2 + (out_y - gt_y) ** 2)
          all_distances.append(dist)
          all_x_errors.append(abs(out_x - gt_x))
          all_y_errors.append(abs(out_y - gt_y))
        else:
          dist = float('nan')

        loc_x_rows.append({
          'frame_id': frame, 'track_id': output_id, 'gt_id': gt_id,
          'value_track': out_x, 'value_gt': gt_x
        })
        loc_y_rows.append({
          'frame_id': frame, 'track_id': output_id, 'gt_id': gt_id,
          'value_track': out_y, 'value_gt': gt_y
        })
        dist_rows.append({
          'frame_id': frame, 'track_id': output_id, 'gt_id': gt_id,
          'distance': dist
        })

    if self._output_folder:
      self._write_outputs(loc_x_rows, loc_y_rows, dist_rows)

    results = {'num_matches': float(len(matches))}
    if 'DIST_T' in self._metrics:
      results['DIST_T_mean'] = (
        float(np.mean(all_distances)) if all_distances else 0.0
      )
    if 'LOC_T_X' in self._metrics:
      results['LOC_T_X_mae'] = (
        float(np.mean(all_x_errors)) if all_x_errors else 0.0
      )
    if 'LOC_T_Y' in self._metrics:
      results['LOC_T_Y_mae'] = (
        float(np.mean(all_y_errors)) if all_y_errors else 0.0
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
    self._uuid_to_id_map = {}
    return self

  # --- Private helpers ---

  def _parse_tracker_outputs(self, tracker_outputs):
    """Parse canonical tracker outputs into per-track frame dictionaries."""
    tracker_output_list = list(tracker_outputs)
    if not tracker_output_list:
      raise RuntimeError("No tracker outputs provided")

    # Deduplicate timestamps
    seen_timestamps = set()
    filtered = []
    for data in tracker_output_list:
      ts = data.get("timestamp")
      if ts not in seen_timestamps:
        seen_timestamps.add(ts)
        filtered.append(data)
    tracker_output_list = filtered

    # Calculate FPS from timestamps
    timestamps = [
      datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
      for d in tracker_output_list
    ]
    num_frames = len(timestamps)
    if num_frames > 1:
      time_span = (timestamps[-1] - timestamps[0]).total_seconds()
      camera_fps = (num_frames - 1) / time_span if time_span > 0 else 30.0
    else:
      camera_fps = 30.0

    first_ts = timestamps[0]
    frame_duration = 1.0 / camera_fps
    next_id = 1

    for scene_data in tracker_output_list:
      ts = datetime.fromisoformat(
        scene_data["timestamp"].replace("Z", "+00:00")
      )
      time_delta = (ts - first_ts).total_seconds()
      frame = int(round(time_delta / frame_duration)) + 1

      for obj in scene_data.get("objects", []):
        uuid = obj["id"]
        if uuid not in self._uuid_to_id_map:
          self._uuid_to_id_map[uuid] = next_id
          next_id += 1
        tid = self._uuid_to_id_map[uuid]

        translation = obj["translation"]
        if tid not in self._output_tracks:
          self._output_tracks[tid] = {}
        self._output_tracks[tid][frame] = (translation[0], translation[1])

  def _parse_ground_truth(self, ground_truth):
    """Parse ground-truth CSV into per-track frame dictionaries."""
    if isinstance(ground_truth, str):
      gt_file_path = ground_truth
    else:
      gt_data = list(ground_truth)
      if gt_data and isinstance(gt_data[0], str):
        gt_file_path = gt_data[0]
      else:
        raise RuntimeError(
          "Ground truth must be a file path string. "
          "Ensure dataset.get_ground_truth() returns a CSV file path."
        )

    sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))
    from format_converters import read_csv_to_dataframe

    gt_df = read_csv_to_dataframe(
      gt_file_path,
      column_names=['frame', 'id', 'x', 'y', 'z', 'conf', 'class', 'visibility']
    )

    for _, row in gt_df.iterrows():
      gid = int(row['id'])
      frame = int(row['frame'])
      if gid not in self._gt_tracks:
        self._gt_tracks[gid] = {}
      self._gt_tracks[gid][frame] = (float(row['x']), float(row['y']))

  def _match_tracks(self):
    """Bipartite assignment minimizing mean Euclidean distance.

    Returns:
      List of (output_track_id, gt_track_id) tuples.
    """
    output_ids = list(self._output_tracks.keys())
    gt_ids = list(self._gt_tracks.keys())
    n = len(output_ids)
    m = len(gt_ids)

    if n == 0 or m == 0:
      return []

    cost = np.full((n, m), np.inf)
    for i, oid in enumerate(output_ids):
      out_frames = set(self._output_tracks[oid])
      for j, gid in enumerate(gt_ids):
        overlap = out_frames & set(self._gt_tracks[gid])
        if len(overlap) >= MIN_OVERLAP_FRAMES:
          dists = []
          for f in overlap:
            ox, oy = self._output_tracks[oid][f]
            gx, gy = self._gt_tracks[gid][f]
            dists.append(math.sqrt((ox - gx) ** 2 + (oy - gy) ** 2))
          cost[i, j] = np.mean(dists)

    if not np.any(np.isfinite(cost)):
      return []

    row_ind, col_ind = linear_sum_assignment(cost)
    matches = []
    for r, c in zip(row_ind, col_ind):
      if np.isfinite(cost[r, c]):
        matches.append((output_ids[r], gt_ids[c]))
    return matches

  def _write_outputs(self, loc_x_rows, loc_y_rows, dist_rows):
    """Write CSV files and plots for configured metrics."""
    if 'LOC_T_X' in self._metrics:
      df = pd.DataFrame(loc_x_rows,
                         columns=['frame_id', 'track_id', 'gt_id',
                                  'value_track', 'value_gt'])
      df.to_csv(self._output_folder / 'LOC_T_X.csv', index=False)
      if not df.empty:
        self._plot_location_metric(df, 'LOC_T_X', 'X Position')

    if 'LOC_T_Y' in self._metrics:
      df = pd.DataFrame(loc_y_rows,
                         columns=['frame_id', 'track_id', 'gt_id',
                                  'value_track', 'value_gt'])
      df.to_csv(self._output_folder / 'LOC_T_Y.csv', index=False)
      if not df.empty:
        self._plot_location_metric(df, 'LOC_T_Y', 'Y Position')

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
