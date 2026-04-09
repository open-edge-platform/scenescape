# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for DiagnosticEvaluator implementation.

Tests track matching, scalar metric computation, and CSV output.
Does not test plot generation.
"""

import math
import pytest
import sys
from pathlib import Path
import tempfile
import shutil

import pandas as pd

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from evaluators.diagnostic_evaluator import DiagnosticEvaluator, MIN_OVERLAP_FRAMES


def _make_timestamp(index, interval_ms=100):
  """Generate ISO 8601 timestamp for a given frame index (0-based)."""
  total_ms = index * interval_ms
  seconds = total_ms // 1000
  millis = total_ms % 1000
  return f"2024-01-01T00:00:{seconds:02d}.{millis:03d}Z"


def _make_tracker_outputs(
  num_frames, tracks, interval_ms=100
):
  """Generate canonical tracker output dicts.

  Args:
    num_frames: Number of frames to generate.
    tracks: Dict mapping UUID string to a callable(frame_index) -> (x, y, z)
            or to a dict {frame_index: (x, y, z)} for sparse tracks.
    interval_ms: Milliseconds between frames.

  Returns:
    List of canonical tracker output dicts.
  """
  outputs = []
  for i in range(num_frames):
    objects = []
    for uuid, pos_source in tracks.items():
      if callable(pos_source):
        pos = pos_source(i)
      else:
        if i not in pos_source:
          continue
        pos = pos_source[i]
      objects.append({
        "id": uuid,
        "translation": list(pos),
        "category": "person"
      })
    outputs.append({
      "timestamp": _make_timestamp(i, interval_ms),
      "id": "scene-1",
      "name": "TestScene",
      "objects": objects
    })
  return outputs


def _make_gt_file(tmp_path, num_frames, tracks):
  """Generate ground truth CSV file.

  Args:
    tmp_path: Directory to write the file.
    num_frames: Number of frames.
    tracks: Dict mapping integer GT ID to a callable(frame_1indexed) -> (x, y)
            or to a dict {frame_1indexed: (x, y)} for sparse tracks.

  Returns:
    Path to GT CSV file.
  """
  gt_file = tmp_path / "gt.txt"
  lines = []
  for frame in range(1, num_frames + 1):
    for gid, pos_source in tracks.items():
      if callable(pos_source):
        x, y = pos_source(frame)
      else:
        if frame not in pos_source:
          continue
        x, y = pos_source[frame]
      # frame,id,x,y,z,conf,class,visibility
      lines.append(f"{frame},{gid},{x},{y},0.0,1.0,1,1")
  gt_file.write_text("\n".join(lines))
  return str(gt_file)


# --- Fixtures ---

@pytest.fixture
def evaluator():
  """Create DiagnosticEvaluator instance."""
  return DiagnosticEvaluator()


@pytest.fixture
def temp_output_folder():
  """Create temporary folder for results."""
  temp_dir = Path(tempfile.mkdtemp(prefix="diagnostic_eval_test_"))
  yield temp_dir
  if temp_dir.exists():
    shutil.rmtree(temp_dir)


@pytest.fixture
def perfect_data(tmp_path):
  """Two tracks, 15 frames, output matches GT exactly."""
  num_frames = 15

  def track1_pos(i):
    # i is 0-based for tracker outputs
    return (1.0 + 0.1 * i, 2.0 + 0.1 * i, 0.0)

  def track2_pos(i):
    return (6.0 + 0.1 * i, 7.0 + 0.1 * i, 0.0)

  tracker_outputs = _make_tracker_outputs(
    num_frames,
    {"uuid-1": track1_pos, "uuid-2": track2_pos}
  )

  def gt1_pos(frame):
    # frame is 1-indexed → convert to 0-based
    return (1.0 + 0.1 * (frame - 1), 2.0 + 0.1 * (frame - 1))

  def gt2_pos(frame):
    return (6.0 + 0.1 * (frame - 1), 7.0 + 0.1 * (frame - 1))

  gt_file = _make_gt_file(tmp_path, num_frames, {1: gt1_pos, 2: gt2_pos})
  return tracker_outputs, gt_file


@pytest.fixture
def known_error_data(tmp_path):
  """Two tracks, 15 frames, output offset by (0.3, 0.4) from GT.

  Expected per-frame distance = sqrt(0.3^2 + 0.4^2) = 0.5
  Expected LOC_T_X_mae = 0.3, LOC_T_Y_mae = 0.4
  """
  num_frames = 15
  x_offset = 0.3
  y_offset = 0.4

  def track1_pos(i):
    return (1.0 + 0.1 * i + x_offset, 2.0 + 0.1 * i + y_offset, 0.0)

  def track2_pos(i):
    return (6.0 + 0.1 * i + x_offset, 7.0 + 0.1 * i + y_offset, 0.0)

  tracker_outputs = _make_tracker_outputs(
    num_frames,
    {"uuid-1": track1_pos, "uuid-2": track2_pos}
  )

  def gt1_pos(frame):
    return (1.0 + 0.1 * (frame - 1), 2.0 + 0.1 * (frame - 1))

  def gt2_pos(frame):
    return (6.0 + 0.1 * (frame - 1), 7.0 + 0.1 * (frame - 1))

  gt_file = _make_gt_file(tmp_path, num_frames, {1: gt1_pos, 2: gt2_pos})
  return tracker_outputs, gt_file


# --- Test Classes ---

class TestConfiguration:
  """Test configuration methods."""

  def test_configure_valid_metrics(self, evaluator):
    """Test configuring valid metrics."""
    result = evaluator.configure_metrics(['LOC_T_X', 'DIST_T'])
    assert result is evaluator
    assert evaluator._metrics == ['LOC_T_X', 'DIST_T']

  def test_configure_all_metrics(self, evaluator):
    """Test configuring all supported metrics."""
    result = evaluator.configure_metrics(['LOC_T_X', 'LOC_T_Y', 'DIST_T'])
    assert result is evaluator
    assert len(evaluator._metrics) == 3

  def test_configure_invalid_metric(self, evaluator):
    """Test configuring invalid metric raises ValueError."""
    with pytest.raises(ValueError, match="not supported"):
      evaluator.configure_metrics(['INVALID_METRIC'])

  def test_configure_empty_metrics(self, evaluator):
    """Test configuring empty metrics list."""
    result = evaluator.configure_metrics([])
    assert result is evaluator
    assert evaluator._metrics == []

  def test_set_output_folder(self, evaluator, temp_output_folder):
    """Test setting output folder."""
    result = evaluator.set_output_folder(temp_output_folder)
    assert result is evaluator
    assert evaluator._output_folder == temp_output_folder

  def test_set_output_folder_string(self, evaluator, temp_output_folder):
    """Test setting output folder with string path."""
    result = evaluator.set_output_folder(str(temp_output_folder))
    assert result is evaluator
    assert evaluator._output_folder == temp_output_folder

  def test_set_output_folder_creates_directory(self, evaluator, temp_output_folder):
    """Test that set_output_folder creates directory if needed."""
    new_folder = temp_output_folder / "new_subfolder"
    assert not new_folder.exists()
    evaluator.set_output_folder(new_folder)
    assert new_folder.exists()


class TestTrackMatching:
  """Test bipartite track matching."""

  def test_perfect_matching(self, evaluator, perfect_data, temp_output_folder):
    """Two output tracks perfectly match two GT tracks."""
    tracker_outputs, gt_file = perfect_data
    evaluator.configure_metrics(['DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)

    results = evaluator.evaluate_metrics()
    assert results['num_matches'] == 2.0

  def test_below_minimum_overlap_no_matches(self, evaluator, tmp_path, temp_output_folder):
    """Tracks with fewer than MIN_OVERLAP_FRAMES overlapping frames produce no matches."""
    num_frames = MIN_OVERLAP_FRAMES - 1

    tracker_outputs = _make_tracker_outputs(
      num_frames,
      {"uuid-1": lambda i: (1.0, 2.0, 0.0)}
    )
    gt_file = _make_gt_file(
      tmp_path, num_frames,
      {1: lambda f: (1.0, 2.0)}
    )

    evaluator.configure_metrics(['DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)
    results = evaluator.evaluate_metrics()

    assert results['num_matches'] == 0.0
    assert results['DIST_T_mean'] == 0.0

  def test_exact_minimum_overlap_matches(self, evaluator, tmp_path, temp_output_folder):
    """Tracks with exactly MIN_OVERLAP_FRAMES overlapping frames produce a match."""
    num_frames = MIN_OVERLAP_FRAMES

    tracker_outputs = _make_tracker_outputs(
      num_frames,
      {"uuid-1": lambda i: (1.0, 2.0, 0.0)}
    )
    gt_file = _make_gt_file(
      tmp_path, num_frames,
      {1: lambda f: (1.0, 2.0)}
    )

    evaluator.configure_metrics(['DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)
    results = evaluator.evaluate_metrics()

    assert results['num_matches'] == 1.0

  def test_matching_selects_closest_pair(self, evaluator, tmp_path, temp_output_folder):
    """Assignment picks the lowest mean-distance pairing."""
    num_frames = 12

    # Track A at (1.0, 1.0), Track B at (5.0, 5.0)
    tracker_outputs = _make_tracker_outputs(
      num_frames,
      {
        "uuid-A": lambda i: (1.0, 1.0, 0.0),
        "uuid-B": lambda i: (5.0, 5.0, 0.0),
      }
    )
    # GT 1 at (1.1, 1.1) — close to Track A
    # GT 2 at (5.1, 5.1) — close to Track B
    gt_file = _make_gt_file(
      tmp_path, num_frames,
      {1: lambda f: (1.1, 1.1), 2: lambda f: (5.1, 5.1)}
    )

    evaluator.configure_metrics(['DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)
    results = evaluator.evaluate_metrics()

    assert results['num_matches'] == 2.0
    # Expected distance per pair = sqrt(0.1^2 + 0.1^2) ≈ 0.1414
    expected_dist = math.sqrt(0.1 ** 2 + 0.1 ** 2)
    assert abs(results['DIST_T_mean'] - expected_dist) < 1e-6

  def test_no_output_tracks(self, evaluator, tmp_path, temp_output_folder):
    """No tracker outputs results in error."""
    gt_file = _make_gt_file(tmp_path, 10, {1: lambda f: (1.0, 2.0)})

    evaluator.configure_metrics(['DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    with pytest.raises(RuntimeError, match="No tracker outputs provided"):
      evaluator.process_tracker_outputs(iter([]), gt_file)


class TestScalarMetrics:
  """Test scalar metric computation."""

  def test_perfect_tracking_zero_distance(self, evaluator, perfect_data, temp_output_folder):
    """Perfect tracking yields zero distance error."""
    tracker_outputs, gt_file = perfect_data
    evaluator.configure_metrics(['LOC_T_X', 'LOC_T_Y', 'DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)

    results = evaluator.evaluate_metrics()

    assert results['DIST_T_mean'] == pytest.approx(0.0, abs=1e-9)
    assert results['LOC_T_X_mae'] == pytest.approx(0.0, abs=1e-9)
    assert results['LOC_T_Y_mae'] == pytest.approx(0.0, abs=1e-9)

  def test_known_error_metrics(self, evaluator, known_error_data, temp_output_folder):
    """Constant offset produces predictable metric values."""
    tracker_outputs, gt_file = known_error_data
    evaluator.configure_metrics(['LOC_T_X', 'LOC_T_Y', 'DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)

    results = evaluator.evaluate_metrics()

    assert results['DIST_T_mean'] == pytest.approx(0.5, abs=1e-9)
    assert results['LOC_T_X_mae'] == pytest.approx(0.3, abs=1e-9)
    assert results['LOC_T_Y_mae'] == pytest.approx(0.4, abs=1e-9)

  def test_evaluate_without_processing_raises(self, evaluator):
    """Evaluation fails without prior processing."""
    evaluator.configure_metrics(['DIST_T'])
    with pytest.raises(RuntimeError, match="No data has been processed"):
      evaluator.evaluate_metrics()

  def test_evaluate_without_metrics_raises(self, evaluator, perfect_data):
    """Evaluation fails without configured metrics."""
    tracker_outputs, gt_file = perfect_data
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)

    with pytest.raises(RuntimeError, match="No metrics configured"):
      evaluator.evaluate_metrics()

  def test_only_requested_metrics_returned(self, evaluator, perfect_data, temp_output_folder):
    """Only configured metrics appear in results."""
    tracker_outputs, gt_file = perfect_data
    evaluator.configure_metrics(['DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)

    results = evaluator.evaluate_metrics()

    assert 'DIST_T_mean' in results
    assert 'num_matches' in results
    assert 'LOC_T_X_mae' not in results
    assert 'LOC_T_Y_mae' not in results


class TestCsvOutput:
  """Test CSV file output."""

  def test_csv_files_created(self, evaluator, perfect_data, temp_output_folder):
    """CSV files are created for each configured metric."""
    tracker_outputs, gt_file = perfect_data
    evaluator.configure_metrics(['LOC_T_X', 'LOC_T_Y', 'DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)
    evaluator.evaluate_metrics()

    assert (temp_output_folder / 'LOC_T_X.csv').exists()
    assert (temp_output_folder / 'LOC_T_Y.csv').exists()
    assert (temp_output_folder / 'DIST_T.csv').exists()

  def test_only_configured_csvs_created(self, evaluator, perfect_data, temp_output_folder):
    """Only CSVs for configured metrics are created."""
    tracker_outputs, gt_file = perfect_data
    evaluator.configure_metrics(['DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)
    evaluator.evaluate_metrics()

    assert (temp_output_folder / 'DIST_T.csv').exists()
    assert not (temp_output_folder / 'LOC_T_X.csv').exists()
    assert not (temp_output_folder / 'LOC_T_Y.csv').exists()

  def test_loc_csv_columns(self, evaluator, perfect_data, temp_output_folder):
    """LOC_T_X CSV has expected columns."""
    tracker_outputs, gt_file = perfect_data
    evaluator.configure_metrics(['LOC_T_X'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)
    evaluator.evaluate_metrics()

    df = pd.read_csv(temp_output_folder / 'LOC_T_X.csv')
    assert list(df.columns) == ['frame_id', 'track_id', 'gt_id', 'value_track', 'value_gt']

  def test_dist_csv_columns(self, evaluator, perfect_data, temp_output_folder):
    """DIST_T CSV has expected columns."""
    tracker_outputs, gt_file = perfect_data
    evaluator.configure_metrics(['DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)
    evaluator.evaluate_metrics()

    df = pd.read_csv(temp_output_folder / 'DIST_T.csv')
    assert list(df.columns) == ['frame_id', 'track_id', 'gt_id', 'distance']

  def test_csv_nan_for_missing_frames(self, evaluator, tmp_path, temp_output_folder):
    """Frames where only one side has data produce NaN in CSV."""
    # Output track: frames 0-14 (1-indexed: 1-15)
    # GT track: frames 1-12 only (1-indexed: 1-12)
    # Frames 13-15 should have NaN for GT values
    num_tracker_frames = 15
    num_gt_frames = 12

    tracker_outputs = _make_tracker_outputs(
      num_tracker_frames,
      {"uuid-1": lambda i: (1.0 + 0.1 * i, 2.0 + 0.1 * i, 0.0)}
    )
    gt_file = _make_gt_file(
      tmp_path, num_gt_frames,
      {1: lambda f: (1.0 + 0.1 * (f - 1), 2.0 + 0.1 * (f - 1))}
    )

    evaluator.configure_metrics(['LOC_T_X', 'DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)
    evaluator.evaluate_metrics()

    df_loc = pd.read_csv(temp_output_folder / 'LOC_T_X.csv')
    df_dist = pd.read_csv(temp_output_folder / 'DIST_T.csv')

    # Frames beyond GT range should have NaN for GT values
    trailing = df_loc[df_loc['frame_id'] > num_gt_frames]
    assert trailing['value_gt'].isna().all()
    assert trailing['value_track'].notna().all()

    trailing_dist = df_dist[df_dist['frame_id'] > num_gt_frames]
    assert trailing_dist['distance'].isna().all()

  def test_csv_row_count(self, evaluator, perfect_data, temp_output_folder):
    """CSV has one row per frame per matched pair."""
    tracker_outputs, gt_file = perfect_data
    evaluator.configure_metrics(['DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)
    evaluator.evaluate_metrics()

    df = pd.read_csv(temp_output_folder / 'DIST_T.csv')
    # 15 frames × 2 matched pairs = 30 rows
    assert len(df) == 30


class TestReset:
  """Test reset functionality."""

  def test_reset(self, evaluator, perfect_data, temp_output_folder):
    """Reset clears all state."""
    tracker_outputs, gt_file = perfect_data
    evaluator.configure_metrics(['DIST_T'])
    evaluator.set_output_folder(temp_output_folder)
    evaluator.process_tracker_outputs(iter(tracker_outputs), gt_file)

    result = evaluator.reset()

    assert result is evaluator
    assert evaluator._metrics == []
    assert evaluator._output_folder is None
    assert evaluator._processed is False
    assert evaluator._output_tracks == {}
    assert evaluator._gt_tracks == {}
    assert evaluator._uuid_to_id_map == {}


class TestMethodChaining:
  """Test method chaining support."""

  def test_full_chain(self, evaluator, perfect_data, temp_output_folder):
    """All configuration methods support chaining."""
    tracker_outputs, gt_file = perfect_data
    result = (evaluator
              .configure_metrics(['DIST_T'])
              .set_output_folder(temp_output_folder)
              .process_tracker_outputs(iter(tracker_outputs), gt_file))
    assert result is evaluator
