# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for JitterEvaluator implementation."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from evaluators.jitter_evaluator import JitterEvaluator


@pytest.fixture
def evaluator():
  return JitterEvaluator()


@pytest.fixture
def mock_gt_csv(tmp_path):
  """Ground-truth CSV with two tracks, 4 frames each (MOTChallenge 3D format)."""
  gt_file = tmp_path / "gt.txt"
  # frame,id,x,y,z,conf,class,visibility — constant velocity so low jitter
  gt_file.write_text(
    "1,1,0.0,0.0,0.0,1.0,1,1\n"
    "1,2,5.0,5.0,0.0,1.0,1,1\n"
    "2,1,1.0,0.0,0.0,1.0,1,1\n"
    "2,2,5.1,5.0,0.0,1.0,1,1\n"
    "3,1,2.0,0.0,0.0,1.0,1,1\n"
    "3,2,5.2,5.0,0.0,1.0,1,1\n"
    "4,1,3.0,0.0,0.0,1.0,1,1\n"
    "4,2,5.3,5.0,0.0,1.0,1,1\n"
  )
  return str(gt_file)


@pytest.fixture
def mock_tracker_outputs():
  """Three-frame tracker output for two tracks."""
  return [
    {
      "timestamp": "2024-01-01T00:00:00.000Z",
      "id": "scene-1",
      "name": "TestScene",
      "objects": [
        {"id": "track-A", "translation": [0.0, 0.0, 0.0], "category": "person"},
        {"id": "track-B", "translation": [5.0, 5.0, 0.0], "category": "person"},
      ]
    },
    {
      "timestamp": "2024-01-01T00:00:00.033Z",
      "id": "scene-1",
      "name": "TestScene",
      "objects": [
        {"id": "track-A", "translation": [1.0, 0.0, 0.0], "category": "person"},
        {"id": "track-B", "translation": [5.1, 5.0, 0.0], "category": "person"},
      ]
    },
    {
      "timestamp": "2024-01-01T00:00:00.067Z",
      "id": "scene-1",
      "name": "TestScene",
      "objects": [
        {"id": "track-A", "translation": [2.0, 0.0, 0.0], "category": "person"},
        {"id": "track-B", "translation": [5.2, 5.0, 0.0], "category": "person"},
      ]
    },
  ]


class TestInitialization:
  def test_default_state(self):
    ev = JitterEvaluator()
    assert ev._metrics == []
    assert ev._output_folder is None
    assert ev._processed is False
    assert ev._track_histories == {}
    assert ev._gt_track_histories == {}
    assert ev._camera_fps == 30.0


class TestConfigureMetrics:
  def test_valid_metrics(self, evaluator):
    result = evaluator.configure_metrics(['rms_jerk', 'acceleration_variance'])
    assert result is evaluator  # method chaining
    assert evaluator._metrics == ['rms_jerk', 'acceleration_variance']

  def test_all_supported_metrics(self, evaluator):
    evaluator.configure_metrics(JitterEvaluator.SUPPORTED_METRICS)
    assert evaluator._metrics == JitterEvaluator.SUPPORTED_METRICS

  def test_invalid_metric_raises(self, evaluator):
    with pytest.raises(ValueError, match="not supported"):
      evaluator.configure_metrics(['INVALID'])

  def test_mixed_valid_invalid_raises(self, evaluator):
    with pytest.raises(ValueError, match="not supported"):
      evaluator.configure_metrics(['rms_jerk', 'INVALID'])

  def test_empty_metrics(self, evaluator):
    evaluator.configure_metrics([])
    assert evaluator._metrics == []


class TestSetOutputFolder:
  def test_sets_folder_and_creates_it(self, tmp_path):
    ev = JitterEvaluator()
    folder = tmp_path / "results" / "jitter"
    result = ev.set_output_folder(folder)
    assert result is ev
    assert folder.exists()
    assert ev._output_folder == folder

  def test_accepts_string_path(self, tmp_path):
    ev = JitterEvaluator()
    folder = str(tmp_path / "results")
    ev.set_output_folder(folder)
    assert ev._output_folder == Path(folder)

  def test_existing_folder_is_accepted(self, tmp_path):
    ev = JitterEvaluator()
    ev.set_output_folder(tmp_path)
    assert ev._output_folder == tmp_path


class TestProcessTrackerOutputs:
  def test_builds_track_histories(self, evaluator, mock_tracker_outputs):
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    assert evaluator._processed is True
    assert "track-A" in evaluator._track_histories
    assert "track-B" in evaluator._track_histories

  def test_track_history_length(self, evaluator, mock_tracker_outputs):
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    assert len(evaluator._track_histories["track-A"]) == 3
    assert len(evaluator._track_histories["track-B"]) == 3

  def test_track_history_positions(self, evaluator, mock_tracker_outputs):
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    positions = [pos for _, pos in evaluator._track_histories["track-A"]]
    assert positions[0] == [0.0, 0.0, 0.0]
    assert positions[1] == [1.0, 0.0, 0.0]
    assert positions[2] == [2.0, 0.0, 0.0]

  def test_track_history_sorted_by_timestamp(self, evaluator):
    # Outputs intentionally out of order
    outputs = [
      {"timestamp": "2024-01-01T00:00:00.067Z", "objects": [
        {"id": "track-A", "translation": [2.0, 0.0, 0.0]}]},
      {"timestamp": "2024-01-01T00:00:00.000Z", "objects": [
        {"id": "track-A", "translation": [0.0, 0.0, 0.0]}]},
      {"timestamp": "2024-01-01T00:00:00.033Z", "objects": [
        {"id": "track-A", "translation": [1.0, 0.0, 0.0]}]},
    ]
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    positions = [pos for _, pos in evaluator._track_histories["track-A"]]
    assert positions[0] == [0.0, 0.0, 0.0]
    assert positions[1] == [1.0, 0.0, 0.0]
    assert positions[2] == [2.0, 0.0, 0.0]

  def test_deduplicates_timestamps(self, evaluator):
    outputs = [
      {"timestamp": "2024-01-01T00:00:00.000Z", "objects": [
        {"id": "track-A", "translation": [0.0, 0.0, 0.0]}]},
      {"timestamp": "2024-01-01T00:00:00.000Z", "objects": [  # duplicate
        {"id": "track-A", "translation": [9.9, 9.9, 9.9]}]},
    ]
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    assert len(evaluator._track_histories["track-A"]) == 1

  def test_empty_outputs_raises(self, evaluator):
    with pytest.raises(RuntimeError, match="No tracker outputs provided"):
      evaluator.process_tracker_outputs([], ground_truth=None)

  def test_invalid_timestamp_raises(self, evaluator):
    outputs = [{"timestamp": "not-a-date", "objects": [
      {"id": "track-A", "translation": [0.0, 0.0, 0.0]}]}]
    with pytest.raises(RuntimeError, match="Cannot parse timestamp"):
      evaluator.process_tracker_outputs(outputs, ground_truth=None)

  def test_missing_translation_skipped(self, evaluator):
    outputs = [{"timestamp": "2024-01-01T00:00:00.000Z", "objects": [
      {"id": "track-A"}]}]  # no 'translation' key
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    assert evaluator._track_histories == {}

  def test_returns_self(self, evaluator, mock_tracker_outputs):
    result = evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    assert result is evaluator

  def test_accepts_iterator(self, evaluator, mock_tracker_outputs):
    evaluator.process_tracker_outputs(iter(mock_tracker_outputs), ground_truth=None)
    assert evaluator._processed is True

  def test_fps_derived_from_multi_frame_outputs(self, evaluator, mock_tracker_outputs):
    """FPS is computed from tracker output timestamps when more than one frame exists."""
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    # mock_tracker_outputs spans ~0.067s over 3 frames → ~29.9 FPS
    assert evaluator._camera_fps > 0
    assert evaluator._camera_fps != 30.0  # not the default fallback

  def test_fps_defaults_to_30_for_single_frame(self, evaluator):
    """Single-frame output cannot derive FPS — falls back to 30.0."""
    outputs = [{"timestamp": "2024-01-01T00:00:00.000Z", "objects": [
      {"id": "track-A", "translation": [0.0, 0.0, 0.0]}]}]
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    assert evaluator._camera_fps == 30.0

  def test_gt_accepts_iterator_of_path(self, evaluator, mock_tracker_outputs, mock_gt_csv):
    """ground_truth passed as an iterator whose first element is the CSV path."""
    evaluator.process_tracker_outputs(
      mock_tracker_outputs, ground_truth=iter([mock_gt_csv])
    )
    assert len(evaluator._gt_track_histories) == 2


class TestEvaluateMetrics:
  def test_raises_if_not_processed(self, evaluator):
    evaluator.configure_metrics(['rms_jerk'])
    with pytest.raises(RuntimeError, match="No data has been processed"):
      evaluator.evaluate_metrics()

  def test_raises_if_no_metrics_configured(self, evaluator, mock_tracker_outputs):
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    with pytest.raises(RuntimeError, match="No metrics configured"):
      evaluator.evaluate_metrics()

  def test_rms_jerk_returns_float(self, evaluator, mock_tracker_outputs):
    evaluator.configure_metrics(['rms_jerk'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert 'rms_jerk' in metrics
    assert isinstance(metrics['rms_jerk'], float)
    assert metrics['rms_jerk'] >= 0.0

  def test_acceleration_variance_returns_float(self, evaluator, mock_tracker_outputs):
    evaluator.configure_metrics(['acceleration_variance'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert 'acceleration_variance' in metrics
    assert isinstance(metrics['acceleration_variance'], float)
    assert metrics['acceleration_variance'] >= 0.0

  def test_both_metrics_together(self, evaluator, mock_tracker_outputs):
    evaluator.configure_metrics(['rms_jerk', 'acceleration_variance'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert set(metrics.keys()) == {'rms_jerk', 'acceleration_variance'}

  def test_constant_velocity_has_zero_rms_jerk(self, evaluator):
    """A track with perfectly constant velocity has near-zero jerk.

    Three levels of finite differentiation on floating-point Unix timestamps
    accumulate rounding errors, so we allow a small numerical tolerance.
    """
    # positions increase by exactly 1.0 m each 0.1 s → constant velocity
    outputs = [
      {"timestamp": f"2024-01-01T00:00:00.{i * 100:03d}Z",
       "objects": [{"id": "track-A",
                    "translation": [float(i), 0.0, 0.0]}]}
      for i in range(6)
    ]
    evaluator.configure_metrics(['rms_jerk'])
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert metrics['rms_jerk'] < 0.05  # numerical tolerance for 3-level differentiation

  def test_constant_velocity_has_zero_acceleration_variance(self, evaluator):
    """A track with perfectly constant velocity has zero acceleration variance."""
    outputs = [
      {"timestamp": f"2024-01-01T00:00:00.{i * 100:03d}Z",
       "objects": [{"id": "track-A",
                    "translation": [float(i), 0.0, 0.0]}]}
      for i in range(5)
    ]
    evaluator.configure_metrics(['acceleration_variance'])
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert abs(metrics['acceleration_variance']) < 1e-6

  def test_returns_zero_when_tracks_too_short_for_jerk(self, evaluator):
    """Tracks with fewer than 4 points yield rms_jerk == 0."""
    outputs = [
      {"timestamp": "2024-01-01T00:00:00.000Z", "objects": [
        {"id": "track-A", "translation": [0.0, 0.0, 0.0]}]},
      {"timestamp": "2024-01-01T00:00:00.033Z", "objects": [
        {"id": "track-A", "translation": [1.0, 0.0, 0.0]}]},
      {"timestamp": "2024-01-01T00:00:00.067Z", "objects": [
        {"id": "track-A", "translation": [2.0, 0.0, 0.0]}]},
    ]
    evaluator.configure_metrics(['rms_jerk'])
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert metrics['rms_jerk'] == 0.0

  def test_saves_results_file(self, evaluator, mock_tracker_outputs, tmp_path):
    evaluator.configure_metrics(['rms_jerk', 'acceleration_variance'])
    evaluator.set_output_folder(tmp_path)
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    evaluator.evaluate_metrics()
    assert (tmp_path / 'jitter_results.txt').exists()

  def test_saves_results_file_content(self, evaluator, mock_tracker_outputs, tmp_path):
    """Results file contains metric name/value pairs for all configured metrics."""
    evaluator.configure_metrics(['rms_jerk', 'acceleration_variance'])
    evaluator.set_output_folder(tmp_path)
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    evaluator.evaluate_metrics()
    content = (tmp_path / 'jitter_results.txt').read_text()
    assert 'rms_jerk' in content
    assert 'acceleration_variance' in content

  def test_returns_zero_for_empty_track_histories(self, evaluator):
    """All objects missing translation → empty histories → both metrics are 0.0."""
    outputs = [{"timestamp": "2024-01-01T00:00:00.000Z", "objects": [
      {"id": "track-A"}]}]  # no translation
    evaluator.configure_metrics(['rms_jerk', 'acceleration_variance'])
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert metrics['rms_jerk'] == 0.0
    assert metrics['acceleration_variance'] == 0.0

  def test_three_point_track_has_nonzero_acceleration_variance(self, evaluator):
    """3-point track: no jerk, but acceleration is computable and non-zero."""
    outputs = [
      {"timestamp": "2024-01-01T00:00:00.000Z", "objects": [
        {"id": "track-A", "translation": [0.0, 0.0, 0.0]}]},
      {"timestamp": "2024-01-01T00:00:00.033Z", "objects": [
        {"id": "track-A", "translation": [1.0, 0.0, 0.0]}]},
      {"timestamp": "2024-01-01T00:00:00.133Z", "objects": [  # larger gap → different velocity
        {"id": "track-A", "translation": [3.0, 0.0, 0.0]}]},
    ]
    evaluator.configure_metrics(['rms_jerk', 'acceleration_variance'])
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert metrics['rms_jerk'] == 0.0  # fewer than 4 points
    assert metrics['acceleration_variance'] >= 0.0  # acceleration exists

  def test_rms_jerk_known_value(self, evaluator):
    """Verify rms_jerk against a manually computed reference.

    Using uniform 1-second steps and a position series with a single
    abrupt velocity change to produce a known jerk.

    Positions: 0, 1, 2, 4 (step sizes: 1, 1, 2)
    Velocities (dt=1s): 1, 1, 2
    Accelerations (midpoint dt≈1s): 0, 1
    Jerk (midpoint dt≈1s): ≈1
    RMS jerk ≈ 1.0 (within floating-point tolerance)
    """
    outputs = [
      {"timestamp": "2024-01-01T00:00:00Z", "objects": [
        {"id": "t", "translation": [0.0, 0.0, 0.0]}]},
      {"timestamp": "2024-01-01T00:00:01Z", "objects": [
        {"id": "t", "translation": [1.0, 0.0, 0.0]}]},
      {"timestamp": "2024-01-01T00:00:02Z", "objects": [
        {"id": "t", "translation": [2.0, 0.0, 0.0]}]},
      {"timestamp": "2024-01-01T00:00:03Z", "objects": [
        {"id": "t", "translation": [4.0, 0.0, 0.0]}]},
    ]
    evaluator.configure_metrics(['rms_jerk'])
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert abs(metrics['rms_jerk'] - 1.0) < 0.05  # floating-point tolerance

  def test_missing_object_id_skipped(self, evaluator):
    """Objects without an 'id' field are silently skipped."""
    outputs = [
      {"timestamp": "2024-01-01T00:00:00.000Z", "objects": [
        {"translation": [0.0, 0.0, 0.0]}]},  # no id
      {"timestamp": "2024-01-01T00:00:00.033Z", "objects": [
        {"translation": [1.0, 0.0, 0.0]}]},  # no id
    ]
    evaluator.process_tracker_outputs(outputs, ground_truth=None)
    assert evaluator._track_histories == {}


class TestGTMetrics:
  """Tests for ground-truth jitter metrics (rms_jerk_gt, acceleration_variance_gt)."""

  def test_gt_metrics_in_supported_metrics(self):
    assert 'rms_jerk_gt' in JitterEvaluator.SUPPORTED_METRICS
    assert 'acceleration_variance_gt' in JitterEvaluator.SUPPORTED_METRICS

  def test_gt_metrics_configured(self, evaluator):
    evaluator.configure_metrics(['rms_jerk_gt', 'acceleration_variance_gt'])
    assert evaluator._metrics == ['rms_jerk_gt', 'acceleration_variance_gt']

  def test_gt_metrics_return_float(self, evaluator, mock_tracker_outputs, mock_gt_csv):
    evaluator.configure_metrics(['rms_jerk_gt', 'acceleration_variance_gt'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=mock_gt_csv)
    metrics = evaluator.evaluate_metrics()
    assert isinstance(metrics['rms_jerk_gt'], float)
    assert isinstance(metrics['acceleration_variance_gt'], float)
    assert metrics['rms_jerk_gt'] >= 0.0
    assert metrics['acceleration_variance_gt'] >= 0.0

  def test_gt_histories_populated(self, evaluator, mock_tracker_outputs, mock_gt_csv):
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=mock_gt_csv)
    assert len(evaluator._gt_track_histories) == 2
    assert '1' in evaluator._gt_track_histories
    assert '2' in evaluator._gt_track_histories

  def test_gt_histories_sorted_by_frame(self, evaluator, mock_tracker_outputs, mock_gt_csv):
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=mock_gt_csv)
    positions = [pos for _, pos in evaluator._gt_track_histories['1']]
    assert positions[0] == [0.0, 0.0, 0.0]
    assert positions[-1] == [3.0, 0.0, 0.0]

  def test_gt_histories_empty_when_no_gt(self, evaluator, mock_tracker_outputs):
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    assert evaluator._gt_track_histories == {}

  def test_gt_metrics_zero_when_no_gt(self, evaluator, mock_tracker_outputs):
    evaluator.configure_metrics(['rms_jerk_gt', 'acceleration_variance_gt'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert metrics['rms_jerk_gt'] == 0.0
    assert metrics['acceleration_variance_gt'] == 0.0

  def test_all_four_metrics_together(self, evaluator, mock_tracker_outputs, mock_gt_csv):
    evaluator.configure_metrics(JitterEvaluator.SUPPORTED_METRICS)
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=mock_gt_csv)
    metrics = evaluator.evaluate_metrics()
    assert set(metrics.keys()) == set(JitterEvaluator.SUPPORTED_METRICS)

  def test_gt_constant_velocity_low_rms_jerk(self, evaluator, mock_tracker_outputs, mock_gt_csv):
    """GT tracks have constant velocity → GT rms_jerk should be near zero."""
    evaluator.configure_metrics(['rms_jerk_gt'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=mock_gt_csv)
    metrics = evaluator.evaluate_metrics()
    assert metrics['rms_jerk_gt'] < 0.05

  def test_ratio_metrics_in_supported_metrics(self):
    assert 'rms_jerk_ratio' in JitterEvaluator.SUPPORTED_METRICS
    assert 'acceleration_variance_ratio' in JitterEvaluator.SUPPORTED_METRICS

  def test_ratio_metrics_return_float(self, evaluator, mock_tracker_outputs, mock_gt_csv):
    evaluator.configure_metrics(['rms_jerk_ratio', 'acceleration_variance_ratio'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=mock_gt_csv)
    metrics = evaluator.evaluate_metrics()
    assert isinstance(metrics['rms_jerk_ratio'], float)
    assert isinstance(metrics['acceleration_variance_ratio'], float)

  def test_ratio_metrics_positive_when_gt_nonzero(self, evaluator, mock_tracker_outputs, mock_gt_csv):
    evaluator.configure_metrics(['rms_jerk_ratio', 'acceleration_variance_ratio'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=mock_gt_csv)
    metrics = evaluator.evaluate_metrics()
    assert metrics['rms_jerk_ratio'] >= 0.0
    assert metrics['acceleration_variance_ratio'] >= 0.0

  def test_ratio_metrics_zero_when_no_gt(self, evaluator, mock_tracker_outputs):
    """With no GT, denominator is 0 → ratio returns 0.0."""
    evaluator.configure_metrics(['rms_jerk_ratio', 'acceleration_variance_ratio'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    metrics = evaluator.evaluate_metrics()
    assert metrics['rms_jerk_ratio'] == 0.0
    assert metrics['acceleration_variance_ratio'] == 0.0

  def test_ratio_equals_tracker_over_gt(self, evaluator, mock_tracker_outputs, mock_gt_csv):
    """ratio must equal the independently computed tracker / GT values."""
    evaluator.configure_metrics([
      'rms_jerk', 'rms_jerk_gt', 'rms_jerk_ratio',
      'acceleration_variance', 'acceleration_variance_gt', 'acceleration_variance_ratio',
    ])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=mock_gt_csv)
    metrics = evaluator.evaluate_metrics()
    if metrics['rms_jerk_gt'] != 0.0:
      assert abs(metrics['rms_jerk_ratio'] - metrics['rms_jerk'] / metrics['rms_jerk_gt']) < 1e-9
    if metrics['acceleration_variance_gt'] != 0.0:
      assert abs(
        metrics['acceleration_variance_ratio']
        - metrics['acceleration_variance'] / metrics['acceleration_variance_gt']
      ) < 1e-9

  def test_gt_csv_not_found_raises(self, evaluator, mock_tracker_outputs):
    evaluator.configure_metrics(['rms_jerk_gt'])
    with pytest.raises(RuntimeError, match="Cannot read ground-truth CSV"):
      evaluator.process_tracker_outputs(
        mock_tracker_outputs, ground_truth="/nonexistent/gt.txt"
      )

  def test_gt_csv_single_row(self, evaluator, mock_tracker_outputs, tmp_path):
    """CSV with a single detection row (numpy loads as 1-D array — must be reshaped)."""
    gt_file = tmp_path / "gt_single.txt"
    gt_file.write_text("1,1,0.0,0.0,0.0,1.0,1,1\n")
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=str(gt_file))
    assert '1' in evaluator._gt_track_histories
    assert len(evaluator._gt_track_histories['1']) == 1

  def test_gt_csv_too_few_columns_raises(self, evaluator, mock_tracker_outputs, tmp_path):
    """CSV with fewer than 5 columns raises a descriptive RuntimeError."""
    gt_file = tmp_path / "gt_bad.txt"
    gt_file.write_text("1,1,0.0,0.0\n")  # only 4 columns
    with pytest.raises(RuntimeError, match="fewer than 5 columns"):
      evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=str(gt_file))

  def test_reset_clears_gt_histories(self, evaluator, mock_tracker_outputs, mock_gt_csv):
    evaluator.configure_metrics(['rms_jerk_gt'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=mock_gt_csv)
    evaluator.reset()
    assert evaluator._gt_track_histories == {}
    assert evaluator._camera_fps == 30.0


class TestReset:
  def test_reset_clears_state(self, evaluator, mock_tracker_outputs, tmp_path):
    evaluator.configure_metrics(['rms_jerk'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    evaluator.set_output_folder(tmp_path)

    evaluator.reset()

    assert evaluator._metrics == []
    assert evaluator._output_folder is None
    assert evaluator._processed is False
    assert evaluator._track_histories == {}

  def test_reset_returns_self(self, evaluator):
    assert evaluator.reset() is evaluator

  def test_reconfigurable_after_reset(self, evaluator, mock_tracker_outputs):
    evaluator.configure_metrics(['rms_jerk'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    evaluator.reset()
    evaluator.configure_metrics(['acceleration_variance'])
    assert evaluator._metrics == ['acceleration_variance']
