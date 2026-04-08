# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for JitterEvaluator implementation."""

import pytest
import sys
from pathlib import Path
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from evaluators.jitter_evaluator import JitterEvaluator


@pytest.fixture
def evaluator():
  return JitterEvaluator()


@pytest.fixture
def temp_result_folder():
  temp_dir = Path(tempfile.mkdtemp(prefix="jitter_test_"))
  yield temp_dir
  if temp_dir.exists():
    shutil.rmtree(temp_dir)


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


class TestEvaluateMetrics:
  def test_raises_if_not_processed(self, evaluator):
    evaluator.configure_metrics(['rms_jerk'])
    with pytest.raises(RuntimeError, match="No data has been processed"):
      evaluator.evaluate_metrics()

  def test_raises_if_no_metrics_configured(self, evaluator, mock_tracker_outputs):
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    with pytest.raises(RuntimeError, match="No metrics configured"):
      evaluator.evaluate_metrics()

  def test_raises_not_implemented(self, evaluator, mock_tracker_outputs):
    evaluator.configure_metrics(['rms_jerk'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    with pytest.raises(NotImplementedError):
      evaluator.evaluate_metrics()


class TestReset:
  def test_reset_clears_state(self, evaluator, mock_tracker_outputs):
    evaluator.configure_metrics(['rms_jerk'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, ground_truth=None)
    evaluator.set_output_folder(Path(tempfile.mkdtemp()))

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
