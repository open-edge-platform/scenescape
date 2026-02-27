# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for PipelineEngine implementation."""

import pytest
import sys
import yaml
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline_engine import PipelineEngine


TEST_TIME_RANGE_START = "2014-09-08T04:00:00.033Z"
TEST_TIME_RANGE_END = "2014-09-08T04:00:04.000Z"


@pytest.fixture
def temp_output_dir():
  """Create temporary directory for pipeline outputs."""
  temp_dir = tempfile.mkdtemp(prefix='test_pipeline_')
  yield temp_dir
  # Cleanup
  shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_config_file(temp_output_dir):
  """Create temporary YAML configuration file."""
  config = {
    'pipeline': {
      'output': {
        'path': temp_output_dir
      }
    },
    'dataset': {
      'class': 'datasets.metric_test_dataset.MetricTestDataset',
      'config': {
        'data_path': str(Path(__file__).parent.parent.parent.parent.parent / 'tests' / 'system' / 'metric' / 'dataset'),
        'cameras': ['x1', 'x2'],
        'camera_fps': 30,
        'start_time': TEST_TIME_RANGE_START,
        'end_time': TEST_TIME_RANGE_END
      }
    },
    'harness': {
      'class': 'harnesses.scene_controller_harness.SceneControllerHarness',
      'config': {
        'container_image': 'scenescape-controller:latest',
        'tracker_config_path': str(Path(__file__).parent.parent.parent.parent.parent / 'tests' / 'system' / 'metric' / 'dataset' / 'tracker-config-time-chunking.json')
      }
    },
    'evaluators': [
      {
        'class': 'evaluators.trackeval_evaluator.TrackEvalEvaluator',
        'config': {
          'metrics': ['HOTA', 'MOTA', 'IDF1']
        }
      }
    ]
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

  def test_load_configuration_missing_section(self, engine, temp_output_dir):
    """Test configuration loading with missing section."""
    config = {
      'pipeline': {
        'output': {
          'path': temp_output_dir
        }
      },
      'dataset': {
        'class': 'datasets.metric_test_dataset.MetricTestDataset',
        'config': {}
      }
      # Missing harness and evaluators sections
    }

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    yaml.dump(config, temp_file)
    temp_file.close()

    try:
      with pytest.raises(ValueError, match="missing required section"):
        engine.load_configuration(temp_file.name)
    finally:
      Path(temp_file.name).unlink()

  def test_load_configuration_missing_pipeline_section(self, engine):
    """Test configuration loading with missing pipeline section."""
    config = {
      'dataset': {
        'class': 'datasets.metric_test_dataset.MetricTestDataset',
        'config': {}
      },
      'harness': {
        'class': 'harnesses.scene_controller_harness.SceneControllerHarness',
        'config': {}
      },
      'evaluators': [
        {
          'class': 'evaluators.trackeval_evaluator.TrackEvalEvaluator',
          'config': {}
        }
      ]
      # Missing pipeline section
    }

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    yaml.dump(config, temp_file)
    temp_file.close()

    try:
      with pytest.raises(ValueError, match="missing required section: pipeline"):
        engine.load_configuration(temp_file.name)
    finally:
      Path(temp_file.name).unlink()

  def test_load_configuration_missing_output_path(self, engine):
    """Test configuration loading with missing pipeline.output.path."""
    config = {
      'pipeline': {
        'output': {}  # Missing 'path'
      },
      'dataset': {
        'class': 'datasets.metric_test_dataset.MetricTestDataset',
        'config': {}
      },
      'harness': {
        'class': 'harnesses.scene_controller_harness.SceneControllerHarness',
        'config': {}
      },
      'evaluators': [
        {
          'class': 'evaluators.trackeval_evaluator.TrackEvalEvaluator',
          'config': {}
        }
      ]
    }

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    yaml.dump(config, temp_file)
    temp_file.close()

    try:
      with pytest.raises(ValueError, match="missing required field: pipeline.output.path"):
        engine.load_configuration(temp_file.name)
    finally:
      Path(temp_file.name).unlink()

  def test_load_configuration_missing_class(self, engine, temp_output_dir):
    """Test configuration loading with missing class field."""
    config = {
      'pipeline': {
        'output': {
          'path': temp_output_dir
        }
      },
      'dataset': {
        'config': {}  # Missing 'class' field
      },
      'harness': {
        'class': 'harnesses.scene_controller_harness.SceneControllerHarness',
        'config': {}
      },
      'evaluators': [
        {
          'class': 'evaluators.trackeval_evaluator.TrackEvalEvaluator',
          'config': {}
        }
      ]
    }

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    yaml.dump(config, temp_file)
    temp_file.close()

    try:
      with pytest.raises(ValueError, match="missing 'class' field"):
        engine.load_configuration(temp_file.name)
    finally:
      Path(temp_file.name).unlink()

  def test_load_configuration_evaluators_not_list(self, engine, temp_output_dir):
    """Test configuration loading with evaluators not a list."""
    config = {
      'pipeline': {
        'output': {
          'path': temp_output_dir
        }
      },
      'dataset': {
        'class': 'datasets.metric_test_dataset.MetricTestDataset',
        'config': {}
      },
      'harness': {
        'class': 'harnesses.scene_controller_harness.SceneControllerHarness',
        'config': {}
      },
      'evaluators': {
        'class': 'evaluators.trackeval_evaluator.TrackEvalEvaluator',
        'config': {}
      }
    }

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    yaml.dump(config, temp_file)
    temp_file.close()

    try:
      with pytest.raises(ValueError, match="Section 'evaluators' must be a list"):
        engine.load_configuration(temp_file.name)
    finally:
      Path(temp_file.name).unlink()

  def test_load_configuration_evaluators_empty(self, engine, temp_output_dir):
    """Test configuration loading with empty evaluators list."""
    config = {
      'pipeline': {
        'output': {
          'path': temp_output_dir
        }
      },
      'dataset': {
        'class': 'datasets.metric_test_dataset.MetricTestDataset',
        'config': {}
      },
      'harness': {
        'class': 'harnesses.scene_controller_harness.SceneControllerHarness',
        'config': {}
      },
      'evaluators': []
    }

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    yaml.dump(config, temp_file)
    temp_file.close()

    try:
      with pytest.raises(ValueError, match="must contain at least one evaluator"):
        engine.load_configuration(temp_file.name)
    finally:
      Path(temp_file.name).unlink()

  def test_load_configuration_multiple_evaluators_fails(self, engine, temp_output_dir):
    """Test that multiple evaluators fail in Phase 1."""
    config = {
      'pipeline': {
        'output': {
          'path': temp_output_dir
        }
      },
      'dataset': {
        'class': 'datasets.metric_test_dataset.MetricTestDataset',
        'config': {}
      },
      'harness': {
        'class': 'harnesses.scene_controller_harness.SceneControllerHarness',
        'config': {}
      },
      'evaluators': [
        {
          'class': 'evaluators.trackeval_evaluator.TrackEvalEvaluator',
          'config': {}
        },
        {
          'class': 'evaluators.trackeval_evaluator.TrackEvalEvaluator',
          'config': {}
        }
      ]
    }

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    yaml.dump(config, temp_file)
    temp_file.close()

    try:
      with pytest.raises(ValueError, match="only a single evaluator is supported"):
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
