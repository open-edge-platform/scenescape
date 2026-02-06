# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrackEvalEvaluator implementation.

These tests are marked as xfail because this is a mock implementation.
When the real TrackEval integration is completed, these tests should be
updated and the xfail markers removed.
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
  """Create mock tracker outputs."""
  return iter([
    {
      "timestamp": "2024-01-01T00:00:00.000Z",
      "objects": [
        {"id": 1, "x": 1.0, "y": 2.0, "z": 0.0},
        {"id": 2, "x": 3.0, "y": 4.0, "z": 0.0}
      ]
    },
    {
      "timestamp": "2024-01-01T00:00:01.000Z",
      "objects": [
        {"id": 1, "x": 1.1, "y": 2.1, "z": 0.0},
        {"id": 2, "x": 3.1, "y": 4.1, "z": 0.0}
      ]
    }
  ])


@pytest.fixture
def mock_ground_truth():
  """Create mock ground truth data."""
  return iter([
    {
      "timestamp": "2024-01-01T00:00:00.000Z",
      "objects": [
        {"id": 1, "x": 1.0, "y": 2.0, "z": 0.0},
        {"id": 2, "x": 3.0, "y": 4.0, "z": 0.0}
      ]
    },
    {
      "timestamp": "2024-01-01T00:00:01.000Z",
      "objects": [
        {"id": 1, "x": 1.1, "y": 2.1, "z": 0.0},
        {"id": 2, "x": 3.1, "y": 4.1, "z": 0.0}
      ]
    }
  ])


class TestInitialization:
  """Test evaluator initialization."""

  def test_init(self):
    """Test basic initialization."""
    evaluator = TrackEvalEvaluator()
    assert evaluator._metrics == []
    assert evaluator._result_folder is None
    assert evaluator._processed is False


class TestConfiguration:
  """Test configuration methods."""

  @pytest.mark.xfail(reason="Mock implementation - will validate with real TrackEval")
  def test_configure_metrics_valid(self, evaluator):
    """Test configuring valid metrics."""
    result = evaluator.configure_metrics(['HOTA', 'MOTA', 'IDF1'])
    
    assert result is evaluator  # Method chaining
    assert evaluator._metrics == ['HOTA', 'MOTA', 'IDF1']

  def test_configure_metrics_invalid(self, evaluator):
    """Test configuring invalid metrics."""
    with pytest.raises(ValueError, match="not supported"):
      evaluator.configure_metrics(['INVALID_METRIC'])

  @pytest.mark.xfail(reason="Mock implementation - will validate with real TrackEval")
  def test_configure_metrics_empty(self, evaluator):
    """Test configuring empty metrics list."""
    result = evaluator.configure_metrics([])
    
    assert result is evaluator
    assert evaluator._metrics == []

  @pytest.mark.xfail(reason="Mock implementation - will validate with real TrackEval")
  def test_set_result_folder_path(self, evaluator, temp_result_folder):
    """Test setting result folder with Path object."""
    result = evaluator.set_result_folder(temp_result_folder)
    
    assert result is evaluator  # Method chaining
    assert evaluator._result_folder == temp_result_folder
    assert temp_result_folder.exists()

  @pytest.mark.xfail(reason="Mock implementation - will validate with real TrackEval")
  def test_set_result_folder_string(self, evaluator, temp_result_folder):
    """Test setting result folder with string path."""
    result = evaluator.set_result_folder(str(temp_result_folder))
    
    assert result is evaluator
    assert evaluator._result_folder == temp_result_folder
    assert temp_result_folder.exists()

  @pytest.mark.xfail(reason="Mock implementation - will validate with real TrackEval")
  def test_set_result_folder_creates_directory(self, evaluator, temp_result_folder):
    """Test that set_result_folder creates directory if it doesn't exist."""
    new_folder = temp_result_folder / "new_subfolder"
    assert not new_folder.exists()
    
    evaluator.set_result_folder(new_folder)
    
    assert new_folder.exists()


class TestProcessing:
  """Test data processing methods."""

  @pytest.mark.xfail(reason="Mock implementation - will validate with real TrackEval")
  def test_process_tracker_outputs(self, evaluator, mock_tracker_outputs, mock_ground_truth):
    """Test processing tracker outputs and ground truth."""
    result = evaluator.process_tracker_outputs(mock_tracker_outputs, mock_ground_truth)
    
    assert result is evaluator  # Method chaining
    assert evaluator._processed is True
    assert len(evaluator._tracker_outputs) == 2
    assert len(evaluator._ground_truth) == 2

  @pytest.mark.xfail(reason="Mock implementation - will validate with real TrackEval")
  def test_process_tracker_outputs_empty(self, evaluator):
    """Test processing empty iterators."""
    result = evaluator.process_tracker_outputs(iter([]), iter([]))
    
    assert result is evaluator
    assert evaluator._processed is True
    assert len(evaluator._tracker_outputs) == 0
    assert len(evaluator._ground_truth) == 0


class TestEvaluation:
  """Test metric evaluation."""

  @pytest.mark.xfail(reason="Mock implementation - returns placeholder values")
  def test_evaluate_metrics_success(self, evaluator, mock_tracker_outputs, mock_ground_truth):
    """Test successful metric evaluation."""
    evaluator.configure_metrics(['HOTA', 'MOTA', 'IDF1'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, mock_ground_truth)
    
    results = evaluator.evaluate_metrics()
    
    assert isinstance(results, dict)
    assert 'HOTA' in results
    assert 'MOTA' in results
    assert 'IDF1' in results
    assert all(isinstance(v, float) for v in results.values())

  def test_evaluate_metrics_without_processing(self, evaluator):
    """Test evaluation fails without processing data first."""
    evaluator.configure_metrics(['HOTA'])
    
    with pytest.raises(RuntimeError, match="No data has been processed"):
      evaluator.evaluate_metrics()

  def test_evaluate_metrics_without_configuring(self, evaluator, mock_tracker_outputs, mock_ground_truth):
    """Test evaluation fails without configuring metrics first."""
    evaluator.process_tracker_outputs(mock_tracker_outputs, mock_ground_truth)
    
    with pytest.raises(RuntimeError, match="No metrics configured"):
      evaluator.evaluate_metrics()

  @pytest.mark.xfail(reason="Mock implementation - returns placeholder values")
  def test_evaluate_metrics_different_metric_types(self, evaluator, mock_tracker_outputs, mock_ground_truth):
    """Test evaluation with different metric types."""
    evaluator.configure_metrics(['HOTA', 'DetA', 'MOTA', 'IDF1', 'CLR_TP'])
    evaluator.process_tracker_outputs(mock_tracker_outputs, mock_ground_truth)
    
    results = evaluator.evaluate_metrics()
    
    # Check that different placeholder values are returned
    assert results['HOTA'] == 0.75  # HOTA-family
    assert results['DetA'] == 0.75  # HOTA-family
    assert results['MOTA'] == 0.80  # Summary metric
    assert results['IDF1'] == 0.80  # Summary metric
    assert results['CLR_TP'] == 0.0  # Count metric


class TestReset:
  """Test reset functionality."""

  @pytest.mark.xfail(reason="Mock implementation - will validate with real TrackEval")
  def test_reset(self, evaluator, mock_tracker_outputs, mock_ground_truth, temp_result_folder):
    """Test reset method."""
    # Configure and process
    evaluator.configure_metrics(['HOTA', 'MOTA'])
    evaluator.set_result_folder(temp_result_folder)
    evaluator.process_tracker_outputs(mock_tracker_outputs, mock_ground_truth)
    
    # Reset
    result = evaluator.reset()
    
    assert result is evaluator  # Method chaining
    assert evaluator._metrics == []
    assert evaluator._result_folder is None
    assert evaluator._processed is False
    assert len(evaluator._tracker_outputs) == 0
    assert len(evaluator._ground_truth) == 0


class TestMethodChaining:
  """Test method chaining."""

  @pytest.mark.xfail(reason="Mock implementation - will validate with real TrackEval")
  def test_method_chaining(self, evaluator, mock_tracker_outputs, mock_ground_truth, temp_result_folder):
    """Test that all configuration methods support chaining."""
    result = (evaluator
              .configure_metrics(['HOTA', 'MOTA'])
              .set_result_folder(temp_result_folder)
              .process_tracker_outputs(mock_tracker_outputs, mock_ground_truth))
    
    assert result is evaluator


class TestIntegration:
  """Integration tests combining multiple operations."""

  @pytest.mark.xfail(reason="Mock implementation - returns placeholder values")
  def test_full_workflow(self, evaluator, mock_tracker_outputs, mock_ground_truth, temp_result_folder):
    """Test complete evaluation workflow."""
    # Configure
    evaluator.configure_metrics(['HOTA', 'MOTA', 'IDF1'])
    evaluator.set_result_folder(temp_result_folder)
    
    # Process
    evaluator.process_tracker_outputs(mock_tracker_outputs, mock_ground_truth)
    
    # Evaluate
    results = evaluator.evaluate_metrics()
    
    # Verify
    assert isinstance(results, dict)
    assert len(results) == 3
    assert all(k in results for k in ['HOTA', 'MOTA', 'IDF1'])
    
    # Reset and verify
    evaluator.reset()
    assert evaluator._processed is False
