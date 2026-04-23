# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""CameraAccuracyEvaluator: per-camera, per-object projection accuracy metrics.

This evaluator is designed to consume the output of ``CameraProjectionHarness``
and report two categories of information:

**Position accuracy**
  For every (camera, object) pair the evaluator computes the frame-by-frame
  Euclidean distance in the XY-plane between the projected world position and
  the ground-truth world position.  The average of these distances gives the
  mean projection error introduced by that camera's calibration for that object.

**Visibility**
  For every (camera, object) pair the evaluator counts in how many frames the
  object was detected by that camera.  This tells us the coverage each camera
  provides for each object.

Object ID encoding
------------------
``CameraProjectionHarness`` encodes object IDs as ``"{camera_id}:{object_id}"``.
This evaluator splits on ``":"`` to recover ``camera_id`` and ``object_id``.

Ground-truth format
-------------------
Ground truth is expected as a file path (str) to a MOTChallenge 3-D CSV file
with 8 columns:
  frame, id, x, y, z, conf, class, visibility

This is the same format produced by ``MetricTestDataset.get_ground_truth()``.

Metrics returned by ``evaluate_metrics()``
------------------------------------------
The method returns a flat ``Dict[str, float]`` of summary scalars:

  - ``n_cameras`` (int):      number of unique cameras seen in tracker outputs.
  - ``n_objects`` (int):      number of GT objects matched.
  - ``dist_mean_all``:        overall mean distance error across all (cam, obj) pairs.
  - ``dist_mean_{cam_key}``:  mean error per camera (cam_key has ``/`` and ``:``
                               replaced with ``_`` to stay a valid key).
  - ``dist_mean_{cam_key}_{obj_id}``: mean distance error per (camera, object).
  - ``visibility_{cam_key}_{obj_id}`` (int): frame count per (camera, object).
  - ``visibility_pct_{cam_key}_{obj_id}``: visibility as % of total GT frames
                                            (float, 0–100).

Outputs written to the configured folder
-----------------------------------------
  - ``distance_errors.csv``:      frame-level rows: cam_id, object_id, frame,
                                  proj_x, proj_y, gt_x, gt_y, distance.
  - ``visibility_summary.csv``:   rows: cam_id, object_id, frame_count,
                                  total_gt_frames, visibility_pct.
  - ``accuracy_summary.csv``:     rows: cam_id, object_id, mean_distance_error.
  - ``summary_table.csv``:        wide per-object table with human-readable
                                  columns, e.g.
                                  "Cam_x1_0 - Visibility (frames)",
                                  "Cam_x1_0 - Visibility (%)",
                                  "Cam_x1_0 - Mean Error (m)".
  - ``distance_errors_{cam_key}.png``: distance error over time per camera.
  - ``trajectories_{cam_key}.png``:    XY trajectories (projected solid,
                                       GT dashed) with tight zoom per camera.
  - ``visibility_bar_chart.png``:      bar chart comparing per-object visibility
                                       across cameras.
"""

import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from base.tracker_evaluator import TrackerEvaluator

SUPPORTED_METRICS = ['DIST_T', 'VISIBILITY']


class CameraAccuracyEvaluator(TrackerEvaluator):
  """Per-camera projection accuracy and visibility evaluator.

  See module docstring for full details.
  """

  def __init__(self):
    self._metrics: List[str] = []
    self._output_folder: Optional[Path] = None
    self._processed: bool = False

    # Structures filled by process_tracker_outputs()
    # {(cam_id, obj_id): {frame_num: (x, y)}}
    self._projected_tracks: Dict[Tuple[str, str], Dict[int, Tuple[float, float]]] = {}
    # {obj_id: {frame_num: (x, y)}}
    self._gt_tracks: Dict[str, Dict[int, Tuple[float, float]]] = {}
    # {obj_id: category string} populated from projected outputs
    self._obj_categories: Dict[str, str] = {}
    # {cam_id: (x, y)} camera world position derived from harness output
    self._cam_positions: Dict[str, Tuple[float, float]] = {}
    # {cam_id: (dx, dy)} normalized 2-D world-space view direction
    self._cam_view_dirs: Dict[str, Tuple[float, float]] = {}
    # Total number of GT frames (max frame index across all GT tracks)
    self._total_gt_frames: int = 0
    # Stored after evaluate_metrics() to enable format_summary()
    self._last_camera_ids: List[str] = []
    self._last_gt_obj_ids: List[str] = []
    self._last_results: Dict[str, Any] = {}

  # ------------------------------------------------------------------
  # TrackerEvaluator interface
  # ------------------------------------------------------------------

  def configure_metrics(self, metrics: List[str]) -> 'CameraAccuracyEvaluator':
    """Configure which metrics to compute.

    Args:
      metrics: Subset of ``['DIST_T', 'VISIBILITY']``.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If an unsupported metric name is given.
    """
    for m in metrics:
      if m not in SUPPORTED_METRICS:
        raise ValueError(
          f"Metric '{m}' is not supported. Supported: {SUPPORTED_METRICS}"
        )
    self._metrics = list(metrics)
    return self

  def set_output_folder(self, path: Path) -> 'CameraAccuracyEvaluator':
    """Set folder for CSV files and plots.

    Args:
      path: Output directory; created if it does not exist.

    Returns:
      Self for method chaining.
    """
    if not isinstance(path, Path):
      path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    self._output_folder = path
    return self

  def set_scene_config(self, config: Dict[str, Any]) -> 'CameraAccuracyEvaluator':
    """Pre-compute camera world positions from the scene calibration config.

    Solves the PnP problem from ``camera points`` / ``map points``
    correspondences (same math as ``PointCorrespondenceTransform``) using
    ``cv2.solvePnP`` locally — no Docker or ``scene_common`` required.

    Positions computed here take priority over the ``camera_position`` field
    that ``CameraProjectionHarness`` embeds in its output frames.

    Args:
      config: Raw scene config dict with a ``"sensors"`` sub-dict.  Each
              sensor entry must contain:
              - ``camera points``  (list of 2-D pixel points)
              - ``map points``     (list of 3-D world points)
              - ``intrinsics``     ([fx, fy, cx, cy])

    Returns:
      Self for method chaining.
    """
    sensors = config.get("sensors", {})
    for cam_id, sensor in sensors.items():
      pos = self._solve_camera_position(cam_id, sensor)
      if pos is not None:
        self._cam_positions[cam_id] = pos
      view_dir = self._solve_camera_view_dir(cam_id, sensor)
      if view_dir is not None:
        self._cam_view_dirs[cam_id] = view_dir
    return self

  @staticmethod
  def _solve_camera_position(
    cam_id: str,
    sensor: Dict[str, Any],
  ) -> Optional[Tuple[float, float]]:
    """Compute (x, y) world position of a camera via solvePnP.

    Replicates the pose-matrix inversion done by
    ``PointCorrespondenceTransform._calculatePoseMat()``.

    Args:
      cam_id: Camera identifier (used only for warning messages).
      sensor: Single sensor entry from the scene config ``sensors`` dict.

    Returns:
      ``(x, y)`` world position, or ``None`` if solvePnP fails.
    """
    try:
      fx, fy, cx, cy = sensor["intrinsics"]
      K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
      cam_pts = np.array(sensor["camera points"], dtype=np.float32)
      map_pts_raw = np.array(sensor["map points"], dtype=np.float32)
      # Ensure 3-D: pad with z=0 if only 2-D world points provided
      if map_pts_raw.ndim == 2 and map_pts_raw.shape[1] == 2:
        map_pts = np.hstack([map_pts_raw, np.zeros((len(map_pts_raw), 1), dtype=np.float32)])
      else:
        map_pts = map_pts_raw

      ok, rvec, tvec = cv2.solvePnP(map_pts, cam_pts, K, None)
      if not ok:
        return None

      # Invert [R|t] to get camera position in world coords:  C = -R^T @ t
      R, _ = cv2.Rodrigues(rvec)
      cam_world = (-R.T @ tvec).flatten()
      return (float(cam_world[0]), float(cam_world[1]))

    except Exception as exc:
      print(f"[CameraAccuracyEvaluator] WARNING: solvePnP failed for '{cam_id}': {exc}",
            file=sys.stderr)
      return None

  @staticmethod
  def _solve_camera_view_dir(
    cam_id: str,
    sensor: Dict[str, Any],
  ) -> Optional[Tuple[float, float]]:
    """Compute normalized 2-D world-space viewing direction of a camera.

    The camera optical axis is +Z in camera space; transformed to world
    space via ``R^T @ [0, 0, 1]``.  Only the XY components are returned
    (top-down 2-D projection).

    Args:
      cam_id: Camera identifier (used only for warning messages).
      sensor: Single sensor entry from the scene config ``sensors`` dict.

    Returns:
      Normalized ``(dx, dy)`` direction vector, or ``None`` on failure.
    """
    try:
      fx, fy, cx, cy = sensor["intrinsics"]
      K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
      cam_pts = np.array(sensor["camera points"], dtype=np.float32)
      map_pts_raw = np.array(sensor["map points"], dtype=np.float32)
      if map_pts_raw.ndim == 2 and map_pts_raw.shape[1] == 2:
        map_pts = np.hstack([map_pts_raw, np.zeros((len(map_pts_raw), 1), dtype=np.float32)])
      else:
        map_pts = map_pts_raw

      ok, rvec, _ = cv2.solvePnP(map_pts, cam_pts, K, None)
      if not ok:
        return None

      R, _ = cv2.Rodrigues(rvec)
      # Camera optical axis in world coordinates
      world_axis = (R.T @ np.array([[0.0], [0.0], [1.0]])).flatten()
      dx, dy = float(world_axis[0]), float(world_axis[1])
      norm = (dx ** 2 + dy ** 2) ** 0.5
      if norm < 1e-9:
        return None
      return (dx / norm, dy / norm)

    except Exception as exc:
      print(f"[CameraAccuracyEvaluator] WARNING: view dir failed for '{cam_id}': {exc}",
            file=sys.stderr)
      return None

  def process_tracker_outputs(
    self,
    tracker_outputs: Iterator[Dict[str, Any]],
    ground_truth: Union[str, Iterator[str]],
  ) -> 'CameraAccuracyEvaluator':
    """Parse projected outputs and ground truth for evaluation.

    Args:
      tracker_outputs: Iterator of Tracker Output Format dicts from
                       ``CameraProjectionHarness``.  Object IDs must be
                       encoded as ``"{camera_id}:{object_id}"``.
      ground_truth: Path to a MOTChallenge 3-D CSV ground-truth file, either
                    as a plain ``str`` (as returned by
                    ``MetricTestDataset.get_ground_truth()``) or as a
                    length-1 ``Iterator[str]`` (for pipeline-engine
                    compatibility with other evaluators).

    Returns:
      Self for method chaining.

    Raises:
      RuntimeError: If parsing fails.
    """
    try:
      self._parse_projected_outputs(tracker_outputs)
      self._parse_ground_truth(ground_truth)
      self._processed = True
      return self
    except Exception as exc:
      raise RuntimeError(f"Failed to process outputs: {exc}") from exc

  def evaluate_metrics(self) -> Dict[str, float]:
    """Compute configured metrics and write detailed CSV / plot outputs.

    Returns:
      Flat dictionary of summary scalars (see module docstring).

    Raises:
      RuntimeError: If ``process_tracker_outputs()`` was not called first.
    """
    if not self._processed:
      raise RuntimeError(
        "No data processed. Call process_tracker_outputs() first."
      )
    if not self._metrics:
      raise RuntimeError(
        "No metrics configured. Call configure_metrics() first."
      )

    results: Dict[str, float] = {}

    # Unique camera IDs
    camera_ids = sorted({cam for cam, _ in self._projected_tracks})
    gt_obj_ids = sorted(self._gt_tracks.keys())

    results["n_cameras"] = len(camera_ids)
    results["n_objects"] = len(gt_obj_ids)

    distance_rows: List[Dict] = []
    visibility_rows: List[Dict] = []
    accuracy_rows: List[Dict] = []

    all_distances: List[float] = []

    for cam_id in camera_ids:
      cam_distances: List[float] = []
      cam_key = cam_id.replace("/", "_").replace(":", "_")

      for obj_id in gt_obj_ids:
        key = (cam_id, obj_id)
        proj_track = self._projected_tracks.get(key, {})
        gt_track = self._gt_tracks.get(obj_id, {})

        # Visibility: frames where this camera detected this object
        frame_count = len(proj_track)
        visibility_rows.append({
          "cam_id": cam_id,
          "object_id": obj_id,
          "frame_count": frame_count,
        })
        if "VISIBILITY" in self._metrics:
          results[f"visibility_{cam_key}_{obj_id}"] = frame_count
          if self._total_gt_frames > 0:
            results[f"visibility_pct_{cam_key}_{obj_id}"] = round(
              100.0 * frame_count / self._total_gt_frames, 1
            )

        # Distance error over frames where both projected and GT are available
        obj_distances: List[float] = []
        overlap_frames = sorted(set(proj_track) & set(gt_track))
        for frame in overlap_frames:
          px, py = proj_track[frame]
          gx, gy = gt_track[frame]
          dist = math.sqrt((px - gx) ** 2 + (py - gy) ** 2)
          obj_distances.append(dist)
          distance_rows.append({
            "cam_id": cam_id,
            "object_id": obj_id,
            "frame": frame,
            "proj_x": px,
            "proj_y": py,
            "gt_x": gx,
            "gt_y": gy,
            "distance": dist,
          })

        mean_dist = float(np.mean(obj_distances)) if obj_distances else float("nan")
        accuracy_rows.append({
          "cam_id": cam_id,
          "object_id": obj_id,
          "overlap_frames": len(overlap_frames),
          "mean_distance_error": mean_dist,
        })

        if "DIST_T" in self._metrics and not math.isnan(mean_dist):
          results[f"dist_mean_{cam_key}_{obj_id}"] = mean_dist
          cam_distances.append(mean_dist)
          all_distances.append(mean_dist)

      if "DIST_T" in self._metrics and cam_distances:
        results[f"dist_mean_{cam_key}"] = float(np.mean(cam_distances))

    if "DIST_T" in self._metrics:
      results["dist_mean_all"] = (
        float(np.mean(all_distances)) if all_distances else float("nan")
      )

    # Store before _write_outputs so _write_summary_table_csv can read them
    self._last_camera_ids = camera_ids
    self._last_gt_obj_ids = gt_obj_ids
    self._last_results = results

    if self._output_folder:
      self._write_outputs(distance_rows, visibility_rows, accuracy_rows, camera_ids)

    return results

  def format_summary(self) -> str:
    """Return a human-readable table of per-object, per-camera accuracy.

    Columns: Object ID | Category | [per camera: Visibility | Dist Error (m)]
    Bottom row: camera mean distance error.

    Must be called after ``evaluate_metrics()``.
    """
    camera_ids = self._last_camera_ids
    gt_obj_ids = self._last_gt_obj_ids
    results = self._last_results
    if not camera_ids or not gt_obj_ids:
      return "  (no results)"

    show_pct = self._total_gt_frames > 0 and "VISIBILITY" in self._metrics
    show_vis = "VISIBILITY" in self._metrics
    show_dist = "DIST_T" in self._metrics

    # Short per-camera metric column labels (camera name shown once as group header)
    FIXED_COLS  = ["Object ID", "Category"]
    METRIC_LABELS = []
    if show_vis:
      METRIC_LABELS.append("Vis (frames)")
    if show_pct:
      METRIC_LABELS.append("Vis (%)")
    if show_dist:
      METRIC_LABELS.append("Mean Err (m)")
    metrics_per_cam = len(METRIC_LABELS)

    # --- Build data cells ---
    def cam_cells(cam_id, obj_id=None):
      """Return metric cells for one camera; obj_id=None for mean row."""
      cam_key = cam_id.replace("/", "_").replace(":", "_")
      cells = []
      if show_vis:
        if obj_id is not None:
          v = results.get(f"visibility_{cam_key}_{obj_id}")
          cells.append(str(v) if v is not None else "-")
        else:
          cells.append("")
      if show_pct:
        if obj_id is not None:
          p = results.get(f"visibility_pct_{cam_key}_{obj_id}")
          cells.append(f"{p:.1f}%" if p is not None else "-")
        else:
          cells.append("")
      if show_dist:
        key = f"dist_mean_{cam_key}" if obj_id is None else f"dist_mean_{cam_key}_{obj_id}"
        d = results.get(key)
        cells.append(f"{d:.4f}" if d is not None else "-")
      return cells

    data_rows = []
    for obj_id in gt_obj_ids:
      row = [obj_id, self._obj_categories.get(obj_id, "?")]
      for cam_id in camera_ids:
        row += cam_cells(cam_id, obj_id)
      data_rows.append(row)

    mean_cells = ["Mean", ""]
    for cam_id in camera_ids:
      mean_cells += cam_cells(cam_id, obj_id=None)

    # --- Compute column widths ---
    # Index 0,1 = fixed; then metrics_per_cam columns per camera
    total_cols = len(FIXED_COLS) + metrics_per_cam * len(camera_ids)
    metric_header = FIXED_COLS + METRIC_LABELS * len(camera_ids)
    col_widths = [len(h) for h in metric_header]
    for row in data_rows + [mean_cells]:
      for i, cell in enumerate(row):
        col_widths[i] = max(col_widths[i], len(cell))

    GAP = "  "
    SEP = " | "  # visual separator between camera groups

    def fmt(cell, i):
      return cell.ljust(col_widths[i]) if i < 2 else cell.rjust(col_widths[i])

    def render_row(cells):
      # Fixed columns joined with GAP; each camera group separated by SEP
      fixed = GAP + GAP.join(fmt(cells[i], i) for i in range(2))
      cam_groups = []
      for ci in range(len(camera_ids)):
        start = 2 + ci * metrics_per_cam
        end = start + metrics_per_cam
        cam_groups.append(GAP.join(fmt(cells[i], i) for i in range(start, end)))
      return fixed + SEP + SEP.join(cam_groups)

    # --- Separator and total width ---
    sample = render_row(data_rows[0] if data_rows else mean_cells)
    sep = "  " + "-" * (len(sample) - 2)

    # --- Camera group header row ---
    fixed_prefix_width = sample.index(SEP) - len("  ")
    cam_group_parts = [" " * fixed_prefix_width]
    for ci, cam_id in enumerate(camera_ids):
      start = 2 + ci * metrics_per_cam
      end = start + metrics_per_cam
      cam_col_width = (
        sum(col_widths[start:end]) + len(GAP) * (metrics_per_cam - 1)
      )
      cam_group_parts.append(cam_id.center(cam_col_width))
    cam_group_line = "  " + SEP.join(cam_group_parts)

    # --- Metric column header row (short names, no camera prefix) ---
    metric_row = FIXED_COLS + METRIC_LABELS * len(camera_ids)
    metric_header_line = render_row(metric_row)

    lines = [cam_group_line, metric_header_line, sep]

    for row in data_rows:
      lines.append(render_row(row))

    lines.append(sep)
    lines.append(render_row(mean_cells))

    overall = results.get("dist_mean_all")
    if overall is not None:
      lines.append(f"\n  Overall mean error: {overall:.4f} m")

    return "\n".join(lines)

  def reset(self) -> 'CameraAccuracyEvaluator':
    """Reset evaluator state.

    Returns:
      Self for method chaining.
    """
    self._metrics = []
    self._output_folder = None
    self._processed = False
    self._projected_tracks = {}
    self._gt_tracks = {}
    self._obj_categories = {}
    self._total_gt_frames = 0
    self._last_camera_ids = []
    self._last_gt_obj_ids = []
    self._last_results = {}
    return self

  # ------------------------------------------------------------------
  # Private helpers
  # ------------------------------------------------------------------

  def _parse_projected_outputs(self, tracker_outputs: Iterator[Dict[str, Any]]) -> None:
    """Fill ``self._projected_tracks`` from harness output frames.

    Frame numbers are computed from timestamps using the same centred-rounding
    approach as DiagnosticEvaluator so that frame indices line up with the GT
    CSV produced by MetricTestDataset.

    Args:
      tracker_outputs: Iterator returned by CameraProjectionHarness.
    """
    frames_list = (
      tracker_outputs
      if isinstance(tracker_outputs, list)
      else list(tracker_outputs)
    )
    if not frames_list:
      raise RuntimeError("No tracker outputs provided")

    # Derive FPS from timestamps
    timestamps = [
      datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
      for d in frames_list
    ]

    # Use unique timestamps to compute FPS (each camera may emit its own stream)
    unique_ts = sorted(set(timestamps))
    if len(unique_ts) > 1:
      span = (unique_ts[-1] - unique_ts[0]).total_seconds()
      fps = (len(unique_ts) - 1) / span if span > 0 else 30.0
    else:
      fps = 30.0

    first_ts = unique_ts[0]
    frame_duration = 1.0 / fps

    for frame_data in frames_list:
      ts = datetime.fromisoformat(frame_data["timestamp"].replace("Z", "+00:00"))
      time_delta = (ts - first_ts).total_seconds()
      frame_num = int(round(time_delta / frame_duration)) + 1

      # Extract camera world position if present — fallback when no scene
      # config was supplied via set_scene_config() (first seen per camera wins)
      cam_pos = frame_data.get("camera_position")
      if cam_pos:
        frame_cam_id = frame_data.get("cam_id", "")
        if frame_cam_id and frame_cam_id not in self._cam_positions:
          self._cam_positions[frame_cam_id] = (float(cam_pos[0]), float(cam_pos[1]))

      for obj in frame_data.get("objects", []):
        encoded_id = obj["id"]
        # ID format: "{camera_id}:{object_id}"
        if ":" not in encoded_id:
          continue
        cam_id, obj_id = encoded_id.split(":", 1)
        translation = obj["translation"]
        key = (cam_id, obj_id)
        if key not in self._projected_tracks:
          self._projected_tracks[key] = {}
        self._projected_tracks[key][frame_num] = (
          float(translation[0]),
          float(translation[1]),
        )
        # Record category (first seen wins; should be consistent across cameras)
        if obj_id not in self._obj_categories:
          self._obj_categories[obj_id] = obj.get("category", "unknown")

  def _parse_ground_truth(self, ground_truth) -> None:
    """Fill ``self._gt_tracks`` from MOTChallenge 3-D CSV.

    Args:
      ground_truth: str path or length-1 iterator containing the path.
    """
    if isinstance(ground_truth, str):
      gt_path = ground_truth
    else:
      gt_data = list(ground_truth)
      if gt_data and isinstance(gt_data[0], str):
        gt_path = gt_data[0]
      else:
        raise RuntimeError(
          "Ground truth must be a file path string. "
          "Ensure dataset.get_ground_truth() returns a CSV path."
        )

    sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))
    from format_converters import read_csv_to_dataframe

    df = read_csv_to_dataframe(
      gt_path,
      column_names=["frame", "id", "x", "y", "z", "conf", "class", "visibility"],
    )

    for _, row in df.iterrows():
      obj_id = str(int(row["id"]))
      frame = int(row["frame"])
      if obj_id not in self._gt_tracks:
        self._gt_tracks[obj_id] = {}
      self._gt_tracks[obj_id][frame] = (float(row["x"]), float(row["y"]))

    if self._gt_tracks:
      self._total_gt_frames = max(
        max(frames.keys()) for frames in self._gt_tracks.values()
      )

  def _write_outputs(
    self,
    distance_rows: List[Dict],
    visibility_rows: List[Dict],
    accuracy_rows: List[Dict],
    camera_ids: List[str],
  ) -> None:
    """Write CSV files and distance-over-time plots."""
    folder = self._output_folder

    # Distance errors CSV
    if distance_rows:
      pd.DataFrame(distance_rows).to_csv(
        folder / "distance_errors.csv", index=False
      )

    # Visibility summary CSV
    pd.DataFrame(visibility_rows).to_csv(
      folder / "visibility_summary.csv", index=False
    )

    # Accuracy summary CSV
    pd.DataFrame(accuracy_rows).to_csv(
      folder / "accuracy_summary.csv", index=False
    )

    # Combined per-object per-camera summary table CSV
    self._write_summary_table_csv(folder)

    # Per-camera distance-over-time plots
    if distance_rows and "DIST_T" in self._metrics:
      dist_df = pd.DataFrame(distance_rows)
      for cam_id in camera_ids:
        cam_df = dist_df[dist_df["cam_id"] == cam_id]
        if cam_df.empty:
          continue
        cam_pos = self._cam_positions.get(cam_id)
        cam_view_dir = self._cam_view_dirs.get(cam_id)
        self._plot_camera_distances(cam_df, cam_id, folder, cam_pos, cam_view_dir)

    # Visibility bar chart
    if visibility_rows and "VISIBILITY" in self._metrics:
      self._plot_visibility(pd.DataFrame(visibility_rows), camera_ids, folder)

  def _write_summary_table_csv(self, folder: Path) -> None:
    """Write the per-object per-camera summary table to summary_table.csv."""
    camera_ids = self._last_camera_ids
    gt_obj_ids = self._last_gt_obj_ids
    results = self._last_results
    show_pct = self._total_gt_frames > 0 and "VISIBILITY" in self._metrics

    # Build human-readable column name helpers
    def col_vis(cam):   return f"{cam} - Visibility (frames)"
    def col_pct(cam):   return f"{cam} - Visibility (%)"
    def col_dist(cam):  return f"{cam} - Mean Error (m)"

    rows = []
    for obj_id in gt_obj_ids:
      row: Dict[str, Any] = {
        "Object ID": obj_id,
        "Category": self._obj_categories.get(obj_id, "unknown"),
      }
      for cam_id in camera_ids:
        cam_key = cam_id.replace("/", "_").replace(":", "_")
        if "VISIBILITY" in self._metrics:
          row[col_vis(cam_id)] = results.get(f"visibility_{cam_key}_{obj_id}", "")
          if show_pct:
            pct = results.get(f"visibility_pct_{cam_key}_{obj_id}")
            row[col_pct(cam_id)] = f"{pct:.1f}" if pct is not None else ""
        if "DIST_T" in self._metrics:
          dist = results.get(f"dist_mean_{cam_key}_{obj_id}")
          row[col_dist(cam_id)] = f"{dist:.4f}" if dist is not None else ""
      rows.append(row)

    # Append a camera mean row
    mean_row: Dict[str, Any] = {"Object ID": "MEAN", "Category": ""}
    for cam_id in camera_ids:
      cam_key = cam_id.replace("/", "_").replace(":", "_")
      if "VISIBILITY" in self._metrics:
        mean_row[col_vis(cam_id)] = ""
        if show_pct:
          mean_row[col_pct(cam_id)] = ""
      if "DIST_T" in self._metrics:
        dist = results.get(f"dist_mean_{cam_key}")
        mean_row[col_dist(cam_id)] = f"{dist:.4f}" if dist is not None else ""
    rows.append(mean_row)

    pd.DataFrame(rows).to_csv(folder / "summary_table.csv", index=False)

  def _plot_camera_distances(
    self,
    cam_df: pd.DataFrame,
    cam_id: str,
    folder: Path,
    cam_pos: Optional[Tuple[float, float]] = None,
    cam_view_dir: Optional[Tuple[float, float]] = None,
  ) -> None:
    """Three separate plots per camera:

    - distance_errors_<cam>.png:        projection error over time per object.
    - trajectories_<cam>.png:           XY trajectory — projected (solid) vs
                                        ground-truth (dashed) with camera marker
                                        and view-direction arrow.
    - error_vs_cam_distance_<cam>.png:  projection error vs. distance from camera
                                        to GT position (only when cam_pos is known).
    """
    obj_ids = sorted(cam_df["object_id"].unique())
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    safe_name = cam_id.replace("/", "_").replace(":", "_")

    # --- Plot 1: distance error over time ---
    fig_err, ax_err = plt.subplots(figsize=(12, 5))
    for idx, obj_id in enumerate(obj_ids):
      grp = cam_df[cam_df["object_id"] == obj_id].sort_values("frame")
      cat = self._obj_categories.get(obj_id, "?")
      color = colors[idx % len(colors)]
      mean_err = grp["distance"].mean()
      ax_err.plot(
        grp["frame"], grp["distance"],
        color=color, linewidth=1,
        label=f"obj {obj_id} ({cat})  mean={mean_err:.3f} m",
      )
    ax_err.set_xlabel("Frame")
    ax_err.set_ylabel("Distance error (m)")
    ax_err.set_title(f"Camera '{cam_id}': projection distance error per object")
    ax_err.legend(fontsize="small")
    ax_err.grid(True, alpha=0.3)
    fig_err.tight_layout()
    fig_err.savefig(folder / f"distance_errors_{safe_name}.png", dpi=150)
    plt.close(fig_err)

    # --- Plot 2: XY trajectories projected vs GT ---
    fig_xy, ax_xy = plt.subplots(figsize=(14, 12))
    for idx, obj_id in enumerate(obj_ids):
      grp = cam_df[cam_df["object_id"] == obj_id].sort_values("frame")
      cat = self._obj_categories.get(obj_id, "?")
      color = colors[idx % len(colors)]

      ax_xy.plot(grp["proj_x"], grp["proj_y"], color=color, linewidth=1.2, linestyle="-",
                 label=f"obj {obj_id} ({cat}) projected")
      ax_xy.plot(grp["gt_x"], grp["gt_y"], color=color, linewidth=1.2, linestyle="--",
                 label=f"obj {obj_id} ({cat}) GT")
      ax_xy.scatter(grp["proj_x"].iloc[0], grp["proj_y"].iloc[0],
                    color=color, marker="o", s=30, zorder=5)
      ax_xy.scatter(grp["gt_x"].iloc[0], grp["gt_y"].iloc[0],
                    color=color, marker="x", s=50, zorder=5)

    ax_xy.set_xlabel("X (m)")
    ax_xy.set_ylabel("Y (m)")
    ax_xy.set_title(f"Camera '{cam_id}': projected (—) vs ground-truth (- -) trajectories")
    traj_handles, _ = ax_xy.get_legend_handles_labels()
    proxy_circle = Line2D([0], [0], marker="o", color="gray", linestyle="None",
                          markersize=6, label="trajectory start (projected)")
    proxy_cross = Line2D([0], [0], marker="x", color="gray", linestyle="None",
                         markersize=8, markeredgewidth=1.5, label="trajectory start (GT)")
    extra_handles = [proxy_circle, proxy_cross]

    # Build axis limits from all trajectory data
    all_x = pd.concat([cam_df["proj_x"], cam_df["gt_x"]])
    all_y = pd.concat([cam_df["proj_y"], cam_df["gt_y"]])
    traj_x_span = float(all_x.max() - all_x.min()) or 1.0
    traj_y_span = float(all_y.max() - all_y.min()) or 1.0
    arrow_len = min(traj_x_span, traj_y_span) * 0.15

    # Camera position marker + view-direction arrow
    if cam_pos is not None:
      cam_x, cam_y = cam_pos
      ax_xy.scatter(cam_x, cam_y, marker="*", color="black", s=250, zorder=10)
      proxy_cam = Line2D([0], [0], marker="*", color="black", linestyle="None",
                         markersize=10, label="camera position")
      extra_handles.append(proxy_cam)
      all_x = pd.concat([all_x, pd.Series([cam_x])])
      all_y = pd.concat([all_y, pd.Series([cam_y])])
      if cam_view_dir is not None:
        vdx, vdy = cam_view_dir
        ax_xy.annotate(
          "",
          xy=(cam_x + vdx * arrow_len, cam_y + vdy * arrow_len),
          xytext=(cam_x, cam_y),
          xycoords="data",
          textcoords="data",
          arrowprops=dict(
            arrowstyle="->",
            color="black",
            lw=1.8,
            mutation_scale=18,
          ),
          zorder=11,
        )
        proxy_dir = Line2D([0], [0], color="black", linewidth=1.8,
                           label="camera view direction")
        extra_handles.append(proxy_dir)

    ax_xy.legend(handles=traj_handles + extra_handles, fontsize="small", ncol=2,
                 loc="upper left", bbox_to_anchor=(0.0, -0.08),
                 borderaxespad=0, framealpha=0.9)
    x_span = float(all_x.max() - all_x.min()) or 1.0
    y_span = float(all_y.max() - all_y.min()) or 1.0
    margin_x = x_span * 0.05
    margin_y = y_span * 0.05
    # Orient axes so camera always appears at the visual bottom with correct chirality.
    # When the camera is above the scene (cam_y > scene_cy) we rotate the view 180°:
    # flip BOTH Y and X.  Flipping Y alone would mirror left/right from the camera's
    # perspective; flipping both together is equivalent to a 180° rotation and preserves
    # the camera-relative left/right direction.
    scene_cy = float(cam_df["gt_y"].mean())
    if cam_pos is not None and cam_y > scene_cy:
      # Camera above scene: 180° rotation — both axes inverted
      ax_xy.set_xlim(all_x.max() + margin_x, all_x.min() - margin_x)
      ax_xy.set_ylim(all_y.max() + margin_y, all_y.min() - margin_y)
    else:
      # Camera below (or at) scene: natural orientation
      ax_xy.set_xlim(all_x.min() - margin_x, all_x.max() + margin_x)
      ax_xy.set_ylim(all_y.min() - margin_y, all_y.max() + margin_y)

    ax_xy.set_aspect("equal", adjustable="box")
    ax_xy.grid(True, alpha=0.3)
    fig_xy.tight_layout(rect=[0, 0.12, 1, 1])
    fig_xy.savefig(folder / f"trajectories_{safe_name}.png", dpi=150, bbox_inches="tight")
    plt.close(fig_xy)

    # --- Plot 3: projection error vs. distance from camera (requires cam_pos) ---
    if cam_pos is not None:
      cam_x, cam_y = cam_pos
      fig_ev, ax_ev = plt.subplots(figsize=(12, 6))

      for idx, obj_id in enumerate(obj_ids):
        grp = cam_df[cam_df["object_id"] == obj_id].copy()
        cat = self._obj_categories.get(obj_id, "?")
        color = colors[idx % len(colors)]

        grp["cam_distance"] = np.sqrt(
          (grp["gt_x"] - cam_x) ** 2 + (grp["gt_y"] - cam_y) ** 2
        )

        # Bin by camera distance; skip objects with too few unique distances
        n_bins = min(10, grp["cam_distance"].nunique())
        if n_bins < 2:
          continue
        grp["bin"] = pd.cut(grp["cam_distance"], bins=n_bins)
        agg = grp.groupby("bin", observed=True)["distance"].agg(["mean", "std"]).dropna()
        bin_centers = agg.index.map(lambda iv: iv.mid)

        ax_ev.plot(bin_centers, agg["mean"], color=color, linewidth=1.5,
                   marker="o", markersize=4,
                   label=f"obj {obj_id} ({cat})  mean={grp['distance'].mean():.3f} m")
        ax_ev.fill_between(bin_centers,
                           agg["mean"] - agg["std"].fillna(0),
                           agg["mean"] + agg["std"].fillna(0),
                           color=color, alpha=0.15)

      ax_ev.set_xlabel("Distance from camera to GT position (m)")
      ax_ev.set_ylabel("Projection error (m)")
      ax_ev.set_title(
        f"Camera '{cam_id}': mean projection error vs. distance from camera\n"
        "(binned; shaded band = ±1 std)"
      )
      if ax_ev.get_legend_handles_labels()[0]:
        ax_ev.legend(fontsize="small")
      ax_ev.grid(True, alpha=0.3)
      fig_ev.tight_layout()
      fig_ev.savefig(folder / f"error_vs_cam_distance_{safe_name}.png", dpi=150)
      plt.close(fig_ev)

  def _plot_visibility(
    self,
    vis_df: pd.DataFrame,
    camera_ids: List[str],
    folder: Path,
  ) -> None:
    """Bar chart: frame count per object per camera."""
    obj_ids = sorted(vis_df["object_id"].unique())
    x = np.arange(len(obj_ids))
    width = 0.8 / max(len(camera_ids), 1)

    fig, ax = plt.subplots(figsize=(max(8, len(obj_ids) * 2), 5))
    for i, cam_id in enumerate(camera_ids):
      cam_counts = [
        vis_df[(vis_df["cam_id"] == cam_id) & (vis_df["object_id"] == oid)][
          "frame_count"
        ].values[0]
        if not vis_df[
          (vis_df["cam_id"] == cam_id) & (vis_df["object_id"] == oid)
        ].empty
        else 0
        for oid in obj_ids
      ]
      ax.bar(x + i * width, cam_counts, width, label=cam_id)

    ax.set_xticks(x + width * (len(camera_ids) - 1) / 2)
    ax.set_xticklabels([f"obj {oid}" for oid in obj_ids])
    ax.set_ylabel("Frames detected")
    ax.set_title("Object visibility per camera")
    ax.legend(fontsize="small")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(folder / "visibility_bar_chart.png", dpi=150)
    plt.close(fig)
