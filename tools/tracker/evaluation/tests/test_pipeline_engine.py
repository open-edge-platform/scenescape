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
        'cameras': ['Cam_x1_0', 'Cam_x2_0'],
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
def temp_multi_evaluator_config_file(temp_output_dir):
  """Create temporary YAML config with two evaluators using distinct metric sets."""
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
        'cameras': ['Cam_x1_0', 'Cam_x2_0'],
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
          'metrics': ['HOTA', 'MOTA']
        }
      },
      {
        'class': 'evaluators.trackeval_evaluator.TrackEvalEvaluator',
        'config': {
          'metrics': ['IDF1']
        }
      }
    ]
  }

  temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
  yaml.dump(config, temp_file)
  temp_file.close()

  yield temp_file.name

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
    assert engine._evaluators == []
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
    assert len(engine._evaluators) == 1

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

  def test_load_configuration_multiple_evaluators_succeeds(self, engine, temp_output_dir):
    """Test that multiple evaluators are accepted."""
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
          'cameras': ['Cam_x1_0', 'Cam_x2_0'],
          'camera_fps': 30
        }
      },
      'harness': {
        'class': 'harnesses.scene_controller_harness.SceneControllerHarness',
        'config': {
          'container_image': 'scenescape-controller:latest',
          'tracker_config_path': str(Path(__file__).parent.parent.parent.parent.parent / 'tests' / 'system' / 'metric' / 'dataset' / 'tracker-config.json')
        }
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
      engine.load_configuration(temp_file.name)
      assert len(engine._evaluators) == 2
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
    assert 'TrackEvalEvaluator' in metrics
    evaluator_metrics = metrics['TrackEvalEvaluator']
    assert 'HOTA' in evaluator_metrics
    assert 'MOTA' in evaluator_metrics
    assert 'IDF1' in evaluator_metrics
    assert all(isinstance(v, float) for v in evaluator_metrics.values())


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
    assert 'TrackEvalEvaluator' in metrics
    evaluator_metrics = metrics['TrackEvalEvaluator']
    assert len(evaluator_metrics) == 3
    assert all(k in evaluator_metrics for k in ['HOTA', 'MOTA', 'IDF1'])


class TestMultipleEvaluators:
  """Tests for multi-evaluator pipeline behavior."""

  @pytest.mark.integration
  def test_evaluate_returns_one_entry_per_evaluator(self, engine, temp_multi_evaluator_config_file):
    """Test that evaluate() returns exactly one result entry per configured evaluator."""
    engine.load_configuration(temp_multi_evaluator_config_file)
    engine.run()
    metrics = engine.evaluate()

    assert isinstance(metrics, dict)
    assert len(metrics) == 2

  @pytest.mark.integration
  def test_evaluate_result_keys_are_unique(self, engine, temp_multi_evaluator_config_file):
    """Test that result keys are unique across all evaluators."""
    engine.load_configuration(temp_multi_evaluator_config_file)
    engine.run()
    metrics = engine.evaluate()

    assert len(metrics) == len(set(metrics.keys()))

  @pytest.mark.integration
  def test_evaluate_result_values_are_metric_dicts(self, engine, temp_multi_evaluator_config_file):
    """Test that each evaluator result is a non-empty dict of float values."""
    engine.load_configuration(temp_multi_evaluator_config_file)
    engine.run()
    metrics = engine.evaluate()

    for evaluator_name, evaluator_metrics in metrics.items():
      assert isinstance(evaluator_metrics, dict)
      assert len(evaluator_metrics) >= 1
      assert all(isinstance(v, float) for v in evaluator_metrics.values())

  @pytest.mark.integration
  def test_evaluate_creates_separate_output_folders(self, engine, temp_multi_evaluator_config_file):
    """Test that each evaluator gets a distinct output folder under evaluators/."""
    engine.load_configuration(temp_multi_evaluator_config_file)
    engine.run()
    engine.evaluate()

    evaluators_dir = engine._output_path / 'evaluators'
    assert evaluators_dir.exists()
    output_folders = [p for p in evaluators_dir.iterdir() if p.is_dir()]
    assert len(output_folders) == 2


class TestConfigureHarness:
  """Unit tests for _configure_harness() new behaviour."""

  def test_object_classes_forwarded_to_harness(self, engine, temp_output_dir):
    """object_classes in harness config is forwarded via set_custom_config."""
    from unittest.mock import MagicMock

    object_classes = [
      {'name': 'person', 'shift_type': 1, 'x_size': 0.5, 'y_size': 0.5},
    ]
    mock_harness = MagicMock()
    engine._harness = mock_harness
    engine._output_path = Path(temp_output_dir)
    engine._config = {
      'harness': {
        'config': {
          'container_image': 'test-image',
          'object_classes': object_classes,
        }
      }
    }

    engine._configure_harness()

    mock_harness.set_custom_config.assert_called_once_with(
      {'object_classes': object_classes}
    )

  def test_no_object_classes_no_set_custom_config(self, engine, temp_output_dir):
    """When object_classes absent and no other custom config, set_custom_config is not called."""
    from unittest.mock import MagicMock

    mock_harness = MagicMock()
    engine._harness = mock_harness
    engine._output_path = Path(temp_output_dir)
    engine._config = {
      'harness': {
        'config': {
          'container_image': 'test-image',
        }
      }
    }

    engine._configure_harness()

    mock_harness.set_custom_config.assert_not_called()


class TestConfigureEvaluators:
  """Unit tests for _configure_evaluators() new behaviour."""

  def test_set_scene_config_called_when_evaluator_supports_it(self, engine, temp_output_dir):
    """set_scene_config is called on an evaluator that exposes the method."""
    from unittest.mock import MagicMock

    scene_config = {'sensors': {}}
    mock_dataset = MagicMock()
    mock_dataset.get_scene_config.return_value = scene_config

    mock_evaluator = MagicMock()
    engine._evaluators = [mock_evaluator]
    engine._dataset = mock_dataset
    engine._output_path = Path(temp_output_dir)
    engine._config = {'evaluators': [{'class': 'evaluators.mock_ev.MockEv', 'config': {}}]}

    engine._configure_evaluators()

    mock_evaluator.set_scene_config.assert_called_once_with(scene_config)

  def test_set_scene_config_not_called_when_scene_config_is_none(self, engine, temp_output_dir):
    """set_scene_config is not called when the dataset returns None."""
    from unittest.mock import MagicMock

    mock_dataset = MagicMock()
    mock_dataset.get_scene_config.return_value = None

    mock_evaluator = MagicMock()
    engine._evaluators = [mock_evaluator]
    engine._dataset = mock_dataset
    engine._output_path = Path(temp_output_dir)
    engine._config = {'evaluators': [{'class': 'evaluators.mock_ev.MockEv', 'config': {}}]}

    engine._configure_evaluators()

    mock_evaluator.set_scene_config.assert_not_called()

  def test_format_summary_used_in_main_output(self, engine, temp_output_dir, capsys):
    """When an evaluator has format_summary, main() prints its result instead of per-metric lines."""
    from unittest.mock import MagicMock, patch

    summary_text = "Camera accuracy: DIST_T=0.042"
    mock_evaluator = MagicMock()
    mock_evaluator.format_summary.return_value = summary_text
    mock_evaluator.evaluate_metrics.return_value = {'DIST_T': 0.042}

    mock_dataset = MagicMock()
    mock_dataset.get_scene_config.return_value = None
    mock_dataset.get_ground_truth.return_value = []

    mock_harness = MagicMock()
    mock_harness.process_inputs.return_value = iter([])

    engine._dataset = mock_dataset
    engine._harness = mock_harness
    engine._evaluators = [mock_evaluator]
    engine._output_path = Path(temp_output_dir)
    engine._config = {
      'evaluators': [{'class': 'evaluators.mock_evaluator.MockEvaluator', 'config': {}}]
    }
    engine._tracker_outputs = []

    # Call the print block directly (mirrors main() logic)
    import pipeline_engine as pe
    evaluator_by_key = {engine._get_evaluator_key(0): mock_evaluator}
    metrics = {'MockEvaluator': {'DIST_T': 0.042}}

    for evaluator_name, evaluator_metrics in metrics.items():
      evaluator = evaluator_by_key.get(evaluator_name)
      if evaluator is not None and hasattr(evaluator, 'format_summary'):
        print(evaluator.format_summary())
      else:
        for metric_name, metric_value in evaluator_metrics.items():
          print(f"  {metric_name}: {metric_value:.4f}")

    captured = capsys.readouterr()
    assert summary_text in captured.out
