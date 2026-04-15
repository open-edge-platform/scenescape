# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for CameraAccuracyEvaluator."""

import math
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from evaluators.camera_accuracy_evaluator import CameraAccuracyEvaluator


def _make_timestamp(index, interval_ms=100):
  """ISO 8601 timestamp for frame *index* (0-based)."""
  total_ms = index * interval_ms
  s = total_ms // 1000
  ms = total_ms % 1000
  return f"2024-01-01T00:00:{s:02d}.{ms:03d}Z"


def _make_projected_outputs(frames_per_cam, tracks_per_cam):
  """Generate projected output frames as CameraProjectionHarness would.

  Args:
    frames_per_cam: Number of frames each camera emits.
    tracks_per_cam: Dict mapping cam_id → {obj_id: callable(frame_idx) -> (x, y)}.

  Returns:
    List of canonical Tracker Output Format dicts with encoded object IDs.
  """
  outputs = []
  for i in range(frames_per_cam):
    ts = _make_timestamp(i)
    for cam_id, obj_tracks in tracks_per_cam.items():
      objects = []
      for obj_id, pos_fn in obj_tracks.items():
        x, y = pos_fn(i)
        objects.append({
          "id": f"{cam_id}:{obj_id}",
          "translation": [x, y, 0.0],
          "category": "person",
        })
      outputs.append({
        "cam_id": cam_id,
        "frame": i,
        "timestamp": ts,
        "camera_position": [1.0, 2.0, 3.0],
        "objects": objects,
      })
  return outputs


def _make_gt_csv(tmp_path, frames, gt_tracks):
  """Write a MOTChallenge 3-D CSV ground-truth file.

  Args:
    tmp_path: Directory for the file.
    frames: Number of frames (1-indexed in CSV).
    gt_tracks: Dict mapping integer obj_id → callable(1-indexed frame) -> (x, y).

  Returns:
    Path to the written CSV file.
  """
  gt_file = tmp_path / "gt.csv"
  rows = []
  for frame_1 in range(1, frames + 1):
    for obj_id, pos_fn in gt_tracks.items():
      x, y = pos_fn(frame_1)
      rows.append(f"{frame_1},{obj_id},{x},{y},0.0,1.0,1,1")
  gt_file.write_text("\n".join(rows))
  return str(gt_file)


@pytest.fixture
def tmp_output(tmp_path):
  return tmp_path / "evaluator_out"


class TestInitialization:
  def test_initial_state(self):
    ev = CameraAccuracyEvaluator()
    assert ev._metrics == []
    assert ev._output_folder is None
    assert not ev._processed

  def test_configure_metrics_valid(self):
    ev = CameraAccuracyEvaluator()
    result = ev.configure_metrics(["DIST_T", "VISIBILITY"])
    assert result is ev
    assert ev._metrics == ["DIST_T", "VISIBILITY"]

  def test_configure_metrics_invalid(self):
    ev = CameraAccuracyEvaluator()
    with pytest.raises(ValueError, match="not supported"):
      ev.configure_metrics(["BAD_METRIC"])

  def test_set_output_folder(self, tmp_path):
    ev = CameraAccuracyEvaluator()
    folder = tmp_path / "out"
    ev.set_output_folder(folder)
    assert folder.exists()
    assert ev._output_folder == folder


class TestProcessTrackerOutputs:
  def test_raises_without_process(self):
    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    with pytest.raises(RuntimeError, match="No data processed"):
      ev.evaluate_metrics()

  def test_raises_without_metrics(self, tmp_path):
    ev = CameraAccuracyEvaluator()
    gt_file = _make_gt_csv(tmp_path, 5, {0: lambda f: (1.0, 2.0)})
    outputs = _make_projected_outputs(5, {"cam1": {"0": lambda i: (1.0, 2.0)}})
    ev.process_tracker_outputs(iter(outputs), gt_file)
    with pytest.raises(RuntimeError, match="No metrics configured"):
      ev.evaluate_metrics()


class TestDistanceMetric:
  def test_perfect_projection(self, tmp_path, tmp_output):
    """Zero error when projected == GT."""
    n_frames = 20
    pos = lambda i: (5.0 + i * 0.01, 10.0)

    outputs = _make_projected_outputs(
      n_frames, {"Cam_x1_0": {"0": lambda i: pos(i)}}
    )
    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: pos(f - 1)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    results = ev.evaluate_metrics()

    assert results["dist_mean_all"] == pytest.approx(0.0, abs=1e-6)
    assert results["dist_mean_Cam_x1_0_0"] == pytest.approx(0.0, abs=1e-6)

  def test_constant_offset(self, tmp_path, tmp_output):
    """Constant 1 m offset → mean error = 1."""
    n_frames = 20
    outputs = _make_projected_outputs(
      n_frames, {"cam1": {"0": lambda i: (6.0, 10.0)}}
    )
    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: (5.0, 10.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    results = ev.evaluate_metrics()

    assert results["dist_mean_cam1_0"] == pytest.approx(1.0, abs=1e-6)
    assert results["dist_mean_all"] == pytest.approx(1.0, abs=1e-6)

  def test_two_cameras_different_errors(self, tmp_path, tmp_output):
    """Each camera can have a different mean error."""
    n_frames = 20
    tracks = {
      "cam_x1": {"0": lambda i: (5.5, 11.0)},   # 0.5 m error
      "cam_x2": {"0": lambda i: (6.0, 11.0)},   # 1.0 m error
    }
    outputs = _make_projected_outputs(n_frames, tracks)
    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: (5.0, 11.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    results = ev.evaluate_metrics()

    assert results["dist_mean_cam_x1_0"] == pytest.approx(0.5, abs=1e-6)
    assert results["dist_mean_cam_x2_0"] == pytest.approx(1.0, abs=1e-6)
    assert results["dist_mean_all"] == pytest.approx(0.75, abs=1e-6)

  def test_summary_keys_present(self, tmp_path, tmp_output):
    n_frames = 20
    outputs = _make_projected_outputs(
      n_frames, {"camA": {"1": lambda i: (1.0, 2.0)}}
    )
    gt_file = _make_gt_csv(tmp_path, n_frames, {1: lambda f: (1.0, 2.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    results = ev.evaluate_metrics()

    assert "n_cameras" in results
    assert "n_objects" in results
    assert "dist_mean_all" in results
    assert results["n_cameras"] == 1
    assert results["n_objects"] == 1


class TestVisibilityMetric:
  def test_full_visibility(self, tmp_path, tmp_output):
    """Object seen in all frames → visibility == n_frames."""
    n_frames = 15
    outputs = _make_projected_outputs(
      n_frames, {"cam1": {"0": lambda i: (5.0, 10.0)}}
    )
    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: (5.0, 10.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["VISIBILITY"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    results = ev.evaluate_metrics()

    assert results["visibility_cam1_0"] == float(n_frames)

  def test_partial_visibility(self, tmp_path, tmp_output):
    """Camera only sees object in the first half of the frames."""
    n_frames = 20
    # Build sparse outputs: cam1 detects obj 0 only in frames 0..9
    outputs = []
    for i in range(n_frames):
      ts = _make_timestamp(i)
      objs = []
      if i < 10:
        objs.append({"id": "cam1:0", "translation": [5.0, 10.0, 0.0], "category": "person"})
      outputs.append({"cam_id": "cam1", "frame": i, "timestamp": ts, "objects": objs})

    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: (5.0, 10.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["VISIBILITY"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    results = ev.evaluate_metrics()

    assert results["visibility_cam1_0"] == 10.0


class TestCsvOutputs:
  def test_csv_files_created(self, tmp_path, tmp_output):
    n_frames = 20
    outputs = _make_projected_outputs(
      n_frames, {"camA": {"0": lambda i: (5.0 + i * 0.01, 10.0)}}
    )
    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: (5.0, 10.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T", "VISIBILITY"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    ev.evaluate_metrics()

    assert (tmp_output / "distance_errors.csv").exists()
    assert (tmp_output / "visibility_summary.csv").exists()
    assert (tmp_output / "accuracy_summary.csv").exists()
    assert (tmp_output / "summary_table.csv").exists()


class TestReset:
  def test_reset_clears_state(self, tmp_path):
    n_frames = 10
    outputs = _make_projected_outputs(
      n_frames, {"cam1": {"0": lambda i: (5.0, 10.0)}}
    )
    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: (5.0, 10.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_path / "out")
    ev.process_tracker_outputs(iter(outputs), gt_file)
    ev.reset()

    assert ev._metrics == []
    assert ev._output_folder is None
    assert not ev._processed
    assert not ev._projected_tracks
    assert not ev._gt_tracks


class TestSetOutputFolderString:
  def test_accepts_string_path(self, tmp_path):
    """set_output_folder converts a string to Path (branch coverage)."""
    ev = CameraAccuracyEvaluator()
    folder = str(tmp_path / "str_out")
    ev.set_output_folder(folder)
    assert Path(folder).exists()
    assert ev._output_folder == Path(folder)


class TestProcessTrackerOutputsException:
  def test_empty_iterator_wrapped_in_runtime_error(self):
    """Empty outputs → inner RuntimeError re-wrapped (except branch)."""
    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    with pytest.raises(RuntimeError, match="Failed to process outputs"):
      ev.process_tracker_outputs(iter([]), "ignored_path")

  def test_invalid_gt_iterator_raises(self, tmp_path):
    """Iterator containing a dict (not a path string) raises RuntimeError."""
    outputs = _make_projected_outputs(5, {"cam1": {"0": lambda i: (5.0, 10.0)}})
    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    with pytest.raises(RuntimeError, match="Failed to process outputs|Ground truth"):
      ev.process_tracker_outputs(iter(outputs), iter([{"not": "a path"}]))


class TestParseEdgeCases:
  def test_single_frame_fps_fallback(self, tmp_path, tmp_output):
    """Single-frame input → fps defaults to 30 (single-timestamp branch)."""
    outputs = _make_projected_outputs(1, {"cam1": {"0": lambda i: (5.0, 10.0)}})
    gt_file = _make_gt_csv(tmp_path, 1, {0: lambda f: (5.0, 10.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    results = ev.evaluate_metrics()

    assert results["dist_mean_all"] == pytest.approx(0.0, abs=1e-6)

  def test_id_without_colon_skipped(self, tmp_path, tmp_output):
    """Object IDs without ':' are silently skipped."""
    outputs = [
      {
        "cam_id": "cam1",
        "frame": 0,
        "timestamp": _make_timestamp(0),
        "objects": [
          {"id": "no_colon_id",  "translation": [9.0, 9.0, 0.0], "category": "x"},
          {"id": "cam1:0",       "translation": [5.0, 10.0, 0.0], "category": "person"},
        ],
      }
    ]
    gt_file = _make_gt_csv(tmp_path, 1, {0: lambda f: (5.0, 10.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    results = ev.evaluate_metrics()

    assert results["n_objects"] == 1
    assert "dist_mean_cam1_0" in results

  def test_ground_truth_as_iterator_path(self, tmp_path, tmp_output):
    """_parse_ground_truth accepts iter([path_string]) form."""
    n_frames = 10
    outputs = _make_projected_outputs(n_frames, {"cam1": {"0": lambda i: (5.0, 10.0)}})
    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: (5.0, 10.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), iter([gt_file]))
    results = ev.evaluate_metrics()

    assert results["dist_mean_all"] == pytest.approx(0.0, abs=1e-6)

  def test_empty_camera_distance_df_skipped(self, tmp_path, tmp_output):
    """Camera whose projected objects have no GT match is skipped in plots."""
    n_frames = 10
    outputs = _make_projected_outputs(
      n_frames,
      {
        "cam1": {"0": lambda i: (5.0, 10.0)},
        "cam2": {"99": lambda i: (1.0, 2.0)},  # obj 99 absent from GT
      },
    )
    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: (5.0, 10.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    ev.evaluate_metrics()  # must not raise

    assert (tmp_output / "accuracy_summary.csv").exists()


class TestFormatSummary:
  def test_format_summary_no_results(self):
    """format_summary before evaluate_metrics returns a no-results string."""
    ev = CameraAccuracyEvaluator()
    assert "(no results)" in ev.format_summary()

  def test_format_summary_dist_only(self, tmp_path, tmp_output):
    """format_summary produces a table with distance metric column."""
    n_frames = 10
    outputs = _make_projected_outputs(
      n_frames, {"CamA": {"0": lambda i: (5.0, 10.0)}}
    )
    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: (5.0, 10.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    ev.evaluate_metrics()
    summary = ev.format_summary()

    assert "CamA" in summary
    assert "Mean Err (m)" in summary
    assert "Overall mean error" in summary

  def test_format_summary_both_metrics(self, tmp_path, tmp_output):
    """format_summary includes visibility columns when both metrics active."""
    n_frames = 10
    outputs = _make_projected_outputs(
      n_frames, {"CamB": {"1": lambda i: (3.0, 7.0)}}
    )
    gt_file = _make_gt_csv(tmp_path, n_frames, {1: lambda f: (3.0, 7.0)})

    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T", "VISIBILITY"])
    ev.set_output_folder(tmp_output)
    ev.process_tracker_outputs(iter(outputs), gt_file)
    ev.evaluate_metrics()
    summary = ev.format_summary()

    assert "Vis (frames)" in summary
    assert "Vis (%)" in summary
    assert "Mean Err (m)" in summary


class TestSetSceneConfig:
  """Tests for set_scene_config() / _solve_camera_position()."""

  # Minimal sensor dict matching the real config.json format
  _SENSOR = {
    "camera points": [[201, 119], [592, 118], [781, 579], [2, 579]],
    "map points": [[3, 15, 0], [10, 15, 0], [10, 5, 0], [3, 5, 0]],
    "intrinsics": [964.2426913831672, 964.6302329684294, 400.0, 300.0],
    "width": 800.0,
    "height": 600.0,
  }

  def test_set_scene_config_populates_cam_positions(self):
    """set_scene_config resolves at least one camera position."""
    config = {"sensors": {"Cam_x1_0": self._SENSOR}}
    ev = CameraAccuracyEvaluator()
    ev.set_scene_config(config)
    assert "Cam_x1_0" in ev._cam_positions
    x, y = ev._cam_positions["Cam_x1_0"]
    assert isinstance(x, float)
    assert isinstance(y, float)

  def test_set_scene_config_returns_self(self):
    """set_scene_config() returns self for chaining."""
    ev = CameraAccuracyEvaluator()
    result = ev.set_scene_config({"sensors": {}})
    assert result is ev

  def test_scene_config_takes_priority_over_harness_output(self, tmp_path, tmp_output):
    """Config-derived positions are not overwritten by camera_position in frames."""
    config = {"sensors": {"CamA": self._SENSOR}}
    ev = CameraAccuracyEvaluator()
    ev.configure_metrics(["DIST_T"])
    ev.set_output_folder(tmp_output)
    ev.set_scene_config(config)

    config_pos = ev._cam_positions.get("CamA")
    assert config_pos is not None

    # Build outputs with a different camera_position value
    n_frames = 5
    outputs = []
    for i in range(n_frames):
      ts = _make_timestamp(i)
      outputs.append({
        "cam_id": "CamA",
        "frame": i,
        "timestamp": ts,
        "camera_position": [999.0, 999.0, 5.0],  # should be ignored
        "objects": [{"id": "CamA:0", "translation": [5.0, 10.0, 0.0], "category": "person"}],
      })

    gt_file = _make_gt_csv(tmp_path, n_frames, {0: lambda f: (5.0, 10.0)})
    ev.process_tracker_outputs(iter(outputs), gt_file)

    # Position must still be the solvePnP result, not 999/999
    assert ev._cam_positions["CamA"] == config_pos

  def test_solve_camera_position_bad_sensor(self):
    """_solve_camera_position returns None gracefully on bad input."""
    result = CameraAccuracyEvaluator._solve_camera_position("bad", {})
    assert result is None

  def test_empty_sensors_dict(self):
    """set_scene_config with no sensors leaves _cam_positions unchanged."""
    ev = CameraAccuracyEvaluator()
    ev.set_scene_config({"sensors": {}})
    assert ev._cam_positions == {}

  def test_set_scene_config_populates_cam_view_dirs(self):
    """set_scene_config resolves at least one camera view direction."""
    config = {"sensors": {"Cam_x1_0": self._SENSOR}}
    ev = CameraAccuracyEvaluator()
    ev.set_scene_config(config)
    assert "Cam_x1_0" in ev._cam_view_dirs
    dx, dy = ev._cam_view_dirs["Cam_x1_0"]
    assert isinstance(dx, float)
    assert isinstance(dy, float)

  def test_set_scene_config_view_dir_normalized(self):
    """View direction vector has unit magnitude."""
    config = {"sensors": {"Cam_x1_0": self._SENSOR}}
    ev = CameraAccuracyEvaluator()
    ev.set_scene_config(config)
    dx, dy = ev._cam_view_dirs["Cam_x1_0"]
    magnitude = math.sqrt(dx ** 2 + dy ** 2)
    assert abs(magnitude - 1.0) < 1e-6

  def test_solve_camera_view_dir_bad_sensor(self):
    """_solve_camera_view_dir returns None gracefully on bad input."""
    result = CameraAccuracyEvaluator._solve_camera_view_dir("bad", {})
    assert result is None

  def test_empty_sensors_dict_no_view_dirs(self):
    """set_scene_config with no sensors leaves _cam_view_dirs unchanged."""
    ev = CameraAccuracyEvaluator()
    ev.set_scene_config({"sensors": {}})
    assert ev._cam_view_dirs == {}


class TestPlotCameraDistances:
  """Smoke tests for _plot_camera_distances axis orientation and view-direction arrow."""

  _SENSOR = {
    "camera points": [[201, 119], [592, 118], [781, 579], [2, 579]],
    "map points": [[3, 15, 0], [10, 15, 0], [10, 5, 0], [3, 5, 0]],
    "intrinsics": [964.2426913831672, 964.6302329684294, 400.0, 300.0],
    "width": 800.0,
    "height": 600.0,
  }

  def _make_cam_df(self):
    import pandas as pd
    return pd.DataFrame({
      "object_id": [0, 0, 0],
      "frame": [1, 2, 3],
      "proj_x": [1.0, 2.0, 3.0],
      "proj_y": [4.0, 5.0, 6.0],
      "gt_x": [1.1, 2.1, 3.1],
      "gt_y": [4.1, 5.1, 6.1],
      "distance": [0.1, 0.1, 0.1],
    })

  def test_camera_above_scene_does_not_raise(self, tmp_path):
    """No exception when camera is above scene (both axes inverted)."""
    ev = CameraAccuracyEvaluator()
    ev._obj_categories = {0: "person"}
    cam_df = self._make_cam_df()
    # cam_y=20 > scene mean gt_y≈5 → triggers 180° rotation
    ev._plot_camera_distances(cam_df, "TestCam", tmp_path, cam_pos=(5.0, 20.0))
    assert (tmp_path / "trajectories_TestCam.png").exists()

  def test_camera_below_scene_does_not_raise(self, tmp_path):
    """No exception when camera is below scene (natural orientation)."""
    ev = CameraAccuracyEvaluator()
    ev._obj_categories = {0: "person"}
    cam_df = self._make_cam_df()
    # cam_y=-5 < scene mean gt_y≈5 → natural orientation
    ev._plot_camera_distances(cam_df, "TestCam", tmp_path, cam_pos=(5.0, -5.0))
    assert (tmp_path / "trajectories_TestCam.png").exists()

  def test_view_direction_arrow_does_not_raise(self, tmp_path):
    """No exception when both cam_pos and cam_view_dir are provided."""
    ev = CameraAccuracyEvaluator()
    ev._obj_categories = {0: "person"}
    cam_df = self._make_cam_df()
    ev._plot_camera_distances(
      cam_df, "TestCam", tmp_path,
      cam_pos=(5.0, -5.0),
      cam_view_dir=(0.0, 1.0),
    )
    assert (tmp_path / "trajectories_TestCam.png").exists()

  def test_no_cam_pos_does_not_raise(self, tmp_path):
    """No exception when cam_pos is None (no camera marker)."""
    ev = CameraAccuracyEvaluator()
    ev._obj_categories = {0: "person"}
    cam_df = self._make_cam_df()
    ev._plot_camera_distances(cam_df, "TestCam", tmp_path, cam_pos=None)
    assert (tmp_path / "trajectories_TestCam.png").exists()
