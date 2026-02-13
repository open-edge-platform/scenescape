# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrackEvalEvaluator implementation.

Tests the complete integration with TrackEval library for computing
tracking metrics on 3D point tracking data.
"""

import pytest
import sys
from pathlib import Path
import tempfile
import shutil

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from evaluators.trackeval_evaluator import TrackEvalEvaluator


@pytest.fixture
def evaluator():
  """Create TrackEvalEvaluator instance."""
  return TrackEvalEvaluator()


@pytest.fixture
def temp_result_folder():
  """Create temporary folder for results."""
  temp_dir = Path(tempfile.mkdtemp(prefix="trackeval_test_"))
  yield temp_dir
  # Cleanup
  if temp_dir.exists():
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_tracker_outputs():
  """Create mock tracker outputs in canonical format."""
  return [
    {
      "timestamp": "2024-01-01T00:00:00.000Z",
      "id": "scene-1",
      "name": "TestScene",
      "objects": [
        {"id": "uuid-track-1", "translation": [1.0, 2.0, 0.0], "category": "person"},
        {"id": "uuid-track-2", "translation": [3.0, 4.0, 0.0], "category": "person"}
      ]
    },
    {
      "timestamp": "2024-01-01T00:00:00.033Z",  # ~30 FPS
      "id": "scene-1",
      "name": "TestScene",
      "objects": [
        {"id": "uuid-track-1", "translation": [1.1, 2.1, 0.0], "category": "person"},
        {"id": "uuid-track-2", "translation": [3.1, 4.1, 0.0], "category": "person"}
      ]
    }
  ]


@pytest.fixture
def mock_ground_truth_file(tmp_path):
  """Create mock ground truth CSV file in MOTChallenge 3D format."""
  gt_file = tmp_path / "gt.txt"
  # Format: frame,id,x,y,z,conf,class,visibility (no header)
  gt_content = """1,1,1.0,2.0,0.0,1.0,1,1
1,2,3.0,4.0,0.0,1.0,1,1
2,1,1.1,2.1,0.0,1.0,1,1
2,2,3.1,4.1,0.0,1.0,1,1"""
  gt_file.write_text(gt_content)
  return str(gt_file)


class TestInitialization:
  """Test evaluator initialization."""

  def test_init(self):
    """Test basic initialization."""
    evaluator = TrackEvalEvaluator()
    assert evaluator._metrics == []
    assert evaluator._output_folder is None
    assert evaluator._processed is False


class TestConfiguration:
  """Test configuration methods."""

  def test_configure_metrics_valid(self, evaluator):
    """Test configuring valid metrics."""
    result = evaluator.configure_metrics(['HOTA', 'MOTA', 'IDF1'])

    assert result is evaluator  # Method chaining
    assert evaluator._metrics == ['HOTA', 'MOTA', 'IDF1']

  def test_configure_metrics_invalid(self, evaluator):
    """Test configuring invalid metrics."""
    with pytest.raises(ValueError, match="not supported"):
      evaluator.configure_metrics(['INVALID_METRIC'])

  def test_configure_metrics_empty(self, evaluator):
    """Test configuring empty metrics list."""
    result = evaluator.configure_metrics([])

    assert result is evaluator
    assert evaluator._metrics == []

  def test_set_output_folder_path(self, evaluator, temp_result_folder):
    """Test setting output folder with Path object."""
    result = evaluator.set_output_folder(temp_result_folder)

    assert result is evaluator  # Method chaining
    assert evaluator._output_folder == temp_result_folder
    assert temp_result_folder.exists()

  def test_set_output_folder_string(self, evaluator, temp_result_folder):
    """Test setting output folder with string path."""
    result = evaluator.set_output_folder(str(temp_result_folder))

    assert result is evaluator
    assert evaluator._output_folder == temp_result_folder
    assert temp_result_folder.exists()

  def test_set_output_folder_creates_directory(self, evaluator, temp_result_folder):
    """Test that set_output_folder creates directory if it doesn't exist."""
    new_folder = temp_result_folder / "new_subfolder"
    assert not new_folder.exists()

    evaluator.set_output_folder(new_folder)

    assert new_folder.exists()


class TestProcessing:
  """Test data processing methods."""

  def test_process_tracker_outputs(self, evaluator, mock_tracker_outputs, mock_ground_truth_file):
    """Test processing tracker outputs and ground truth."""
    result = evaluator.process_tracker_outputs(
      iter(mock_tracker_outputs),
      mock_ground_truth_file  # Ground truth is a file path
    )

    assert result is evaluator  # Method chaining
    assert evaluator._processed is True
    assert evaluator._tracker_csv_path is not None
    assert evaluator._ground_truth_csv_path is not None

  def test_tracker_csv_copied_to_output_folder(
    self,
    evaluator,
    mock_tracker_outputs,
    mock_ground_truth_file,
    temp_result_folder
  ):
    """Test tracker CSV is mirrored to configured output folder."""
    evaluator.set_output_folder(temp_result_folder)
    evaluator.process_tracker_outputs(iter(mock_tracker_outputs), mock_ground_truth_file)

    expected_csv = temp_result_folder / f"{evaluator._seq_name}.txt"
    assert expected_csv.exists()

  def test_process_tracker_outputs_empty(self, evaluator, mock_ground_truth_file):
    """Test processing empty tracker outputs raises error."""
    with pytest.raises(RuntimeError, match="No tracker outputs provided"):
      evaluator.process_tracker_outputs(iter([]), mock_ground_truth_file)


class TestEvaluation:
  """Test metric evaluation."""

  def test_evaluate_metrics_success(self, evaluator, mock_tracker_outputs, mock_ground_truth_file):
    """Test successful metric evaluation."""
    evaluator.configure_metrics(['HOTA', 'MOTA', 'IDF1'])
    evaluator.process_tracker_outputs(iter(mock_tracker_outputs), mock_ground_truth_file)

    results = evaluator.evaluate_metrics()

    assert isinstance(results, dict)
    assert 'HOTA' in results
    assert 'MOTA' in results
    assert 'IDF1' in results
    assert all(isinstance(v, (int, float)) for v in results.values())
    # Perfect tracking should give high scores
    assert results['HOTA'] > 0.9  # High HOTA for perfect tracking
    assert results['MOTA'] > 0.9  # High MOTA for perfect tracking
    assert results['IDF1'] > 0.9  # High IDF1 for perfect tracking

  def test_evaluate_metrics_without_processing(self, evaluator):
    """Test evaluation fails without processing data first."""
    evaluator.configure_metrics(['HOTA'])

    with pytest.raises(RuntimeError, match="No data has been processed"):
      evaluator.evaluate_metrics()

  def test_evaluate_metrics_without_configuring(self, evaluator, mock_tracker_outputs, mock_ground_truth_file):
    """Test evaluation fails without configuring metrics first."""
    evaluator.process_tracker_outputs(iter(mock_tracker_outputs), mock_ground_truth_file)

    with pytest.raises(RuntimeError, match="No metrics configured"):
      evaluator.evaluate_metrics()

  def test_evaluate_metrics_different_metric_types(self, evaluator, mock_tracker_outputs, mock_ground_truth_file):
    """Test evaluation with different metric types."""
    evaluator.configure_metrics(['HOTA', 'DetA', 'MOTA', 'IDF1', 'CLR_TP'])
    evaluator.process_tracker_outputs(iter(mock_tracker_outputs), mock_ground_truth_file)

    results = evaluator.evaluate_metrics()

    # Check that all requested metrics are returned
    assert 'HOTA' in results
    assert 'DetA' in results
    assert 'MOTA' in results
    assert 'IDF1' in results
    assert 'CLR_TP' in results
    # All should be numeric
    assert all(isinstance(v, (int, float)) for v in results.values())


class TestReset:
  """Test reset functionality."""

  def test_reset(self, evaluator, mock_tracker_outputs, mock_ground_truth_file, temp_result_folder):
    """Test reset method."""
    # Configure and process
    evaluator.configure_metrics(['HOTA', 'MOTA'])
    evaluator.set_output_folder(temp_result_folder)
    evaluator.process_tracker_outputs(iter(mock_tracker_outputs), mock_ground_truth_file)

    # Reset
    result = evaluator.reset()

    assert result is evaluator  # Method chaining
    assert evaluator._metrics == []
    assert evaluator._output_folder is None
    assert evaluator._processed is False
    assert evaluator._temp_dir is None


class TestMethodChaining:
  """Test method chaining."""

  def test_method_chaining(self, evaluator, mock_tracker_outputs, mock_ground_truth_file, temp_result_folder):
    """Test that all configuration methods support chaining."""
    result = (evaluator
              .configure_metrics(['HOTA', 'MOTA'])
              .set_output_folder(temp_result_folder)
              .process_tracker_outputs(iter(mock_tracker_outputs), mock_ground_truth_file))

    assert result is evaluator


class TestIntegration:
  """Integration tests combining multiple operations."""

  def test_full_workflow(self, evaluator, mock_tracker_outputs, mock_ground_truth_file, temp_result_folder):
    """Test complete evaluation workflow."""
    # Configure
    evaluator.configure_metrics(['HOTA', 'MOTA', 'IDF1'])
    evaluator.set_output_folder(temp_result_folder)

    # Process
    evaluator.process_tracker_outputs(iter(mock_tracker_outputs), mock_ground_truth_file)

    # Evaluate
    results = evaluator.evaluate_metrics()

    # Verify
    assert isinstance(results, dict)
    assert len(results) == 3
    assert all(k in results for k in ['HOTA', 'MOTA', 'IDF1'])
    # Perfect tracking should give high scores
    assert all(v > 0.9 for v in results.values())

    # Reset and verify
    evaluator.reset()
    assert evaluator._processed is False
