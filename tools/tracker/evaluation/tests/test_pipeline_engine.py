# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for PipelineEngine implementation."""

import pytest
import sys
import yaml
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline_engine import PipelineEngine


@pytest.fixture
def temp_config_file():
  """Create temporary YAML configuration file."""
  config = {
    'dataset': {
      'class': 'datasets.metric_test_dataset.MetricTestDataset',
      'config': {
        'data_path': str(Path(__file__).parent.parent.parent.parent.parent / 'tests' / 'system' / 'metric' / 'test_data'),
        'cameras': ['x1', 'x2'],
        'camera_fps': 30
      }
    },
    'harness': {
      'class': 'harnesses.scene_controller_harness.SceneControllerHarness',
      'config': {
        'container_image': 'scenescape-controller:latest',
        'tracker_config_path': str(Path(__file__).parent.parent.parent.parent.parent / 'tests' / 'system' / 'metric' / 'test_data' / 'tracker-config-time-chunking.json')
      }
    },
    'evaluator': {
      'class': 'evaluators.trackeval_evaluator.TrackEvalEvaluator',
      'config': {
        'metrics': ['HOTA', 'MOTA', 'IDF1'],
        'result_folder': '/tmp/tracker_evaluation_results'
      }
    }
  }

  temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
  yaml.dump(config, temp_file)
  temp_file.close()

  yield temp_file.name

  # Cleanup
  Path(temp_file.name).unlink()


@pytest.fixture
def engine():
  """Create PipelineEngine instance."""
  return PipelineEngine()


class TestInitialization:
  """Test pipeline engine initialization."""

  def test_init(self):
    """Test basic initialization."""
    engine = PipelineEngine()
    assert engine._config is None
    assert engine._dataset is None
    assert engine._harness is None
    assert engine._evaluator is None
    assert engine._tracker_outputs is None


class TestLoadConfiguration:
  """Test configuration loading."""

  def test_load_configuration_success(self, engine, temp_config_file):
    """Test successful configuration loading."""
    result = engine.load_configuration(temp_config_file)

    assert result is engine  # Method chaining
    assert engine._config is not None
    assert engine._dataset is not None
    assert engine._harness is not None
    assert engine._evaluator is not None

  def test_load_configuration_file_not_found(self, engine):
    """Test configuration loading with non-existent file."""
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
      engine.load_configuration("/nonexistent/config.yaml")

  def test_load_configuration_invalid_yaml(self, engine):
    """Test configuration loading with invalid YAML."""
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    temp_file.write("invalid: yaml: content: [")
    temp_file.close()

    try:
      with pytest.raises(ValueError, match="Failed to parse YAML"):
        engine.load_configuration(temp_file.name)
    finally:
      Path(temp_file.name).unlink()

  def test_load_configuration_missing_section(self, engine):
    """Test configuration loading with missing section."""
    config = {
      'dataset': {
        'class': 'datasets.metric_test_dataset.MetricTestDataset',
        'config': {}
      }
      # Missing harness and evaluator sections
    }

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    yaml.dump(config, temp_file)
    temp_file.close()

    try:
      with pytest.raises(ValueError, match="missing required section"):
        engine.load_configuration(temp_file.name)
    finally:
      Path(temp_file.name).unlink()

  def test_load_configuration_missing_class(self, engine):
    """Test configuration loading with missing class field."""
    config = {
      'dataset': {
        'config': {}  # Missing 'class' field
      },
      'harness': {
        'class': 'harnesses.scene_controller_harness.SceneControllerHarness',
        'config': {}
      },
      'evaluator': {
        'class': 'evaluators.trackeval_evaluator.TrackEvalEvaluator',
        'config': {}
      }
    }

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    yaml.dump(config, temp_file)
    temp_file.close()

    try:
      with pytest.raises(ValueError, match="missing 'class' field"):
        engine.load_configuration(temp_file.name)
    finally:
      Path(temp_file.name).unlink()


class TestRun:
  """Test tracker execution."""

  @pytest.mark.integration
  def test_run_without_configuration(self, engine):
    """Test running without loading configuration first."""
    with pytest.raises(RuntimeError, match="Configuration not loaded"):
      engine.run()

  @pytest.mark.integration
  def test_run_success(self, engine, temp_config_file):
    """Test successful tracker execution."""
    engine.load_configuration(temp_config_file)
    result = engine.run()

    assert result is engine  # Method chaining
    assert engine._tracker_outputs is not None


class TestEvaluate:
  """Test metric evaluation."""

  @pytest.mark.integration
  def test_evaluate_without_run(self, engine, temp_config_file):
    """Test evaluating without running tracker first."""
    engine.load_configuration(temp_config_file)

    with pytest.raises(RuntimeError, match="Tracker outputs not available"):
      engine.evaluate()

  @pytest.mark.integration
  @pytest.mark.xfail(reason="Mock evaluator returns placeholder values")
  def test_evaluate_success(self, engine, temp_config_file):
    """Test successful metric evaluation."""
    engine.load_configuration(temp_config_file)
    engine.run()
    metrics = engine.evaluate()

    assert isinstance(metrics, dict)
    assert 'HOTA' in metrics
    assert 'MOTA' in metrics
    assert 'IDF1' in metrics
    assert all(isinstance(v, float) for v in metrics.values())


class TestMethodChaining:
  """Test method chaining."""

  @pytest.mark.integration
  @pytest.mark.xfail(reason="Mock evaluator returns placeholder values")
  def test_method_chaining(self, engine, temp_config_file):
    """Test that methods support chaining."""
    metrics = (engine
               .load_configuration(temp_config_file)
               .run()
               .evaluate())

    assert isinstance(metrics, dict)


class TestIntegration:
  """Integration tests."""

  @pytest.mark.integration
  @pytest.mark.xfail(reason="Mock evaluator returns placeholder values")
  def test_full_pipeline(self, engine, temp_config_file):
    """Test complete pipeline workflow."""
    # Load configuration
    engine.load_configuration(temp_config_file)

    # Run tracker
    engine.run()

    # Evaluate metrics
    metrics = engine.evaluate()

    # Verify results
    assert isinstance(metrics, dict)
    assert len(metrics) == 3
    assert all(k in metrics for k in ['HOTA', 'MOTA', 'IDF1'])
