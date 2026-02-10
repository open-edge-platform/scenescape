# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pipeline engine for tracker evaluation.

This module implements the PipelineEngine class which orchestrates the complete
tracker evaluation workflow:
1. Load configuration from YAML file
2. Instantiate and configure dataset, harness, and evaluator components
3. Run tracker on dataset inputs
4. Evaluate tracking quality metrics
"""

import sys
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import importlib


class PipelineEngine:
  """Pipeline engine for tracker evaluation.

  The PipelineEngine orchestrates the complete evaluation workflow by:
  - Loading YAML configuration
  - Dynamically importing and instantiating components
  - Configuring dataset, harness, and evaluator
  - Running tracker and computing metrics

  Configuration File Format:
    dataset:
      class: datasets.metric_test_dataset.MetricTestDataset
      config:
        data_path: /path/to/test_data
        cameras: [x1, x2]
        camera_fps: 30

    harness:
      class: harnesses.scene_controller_harness.SceneControllerHarness
      config:
        container_image: scenescape-controller:latest
        tracker_config_path: /path/to/tracker-config.json

    evaluator:
      class: evaluators.trackeval_evaluator.TrackEvalEvaluator
      config:
        metrics: [HOTA, MOTA, IDF1]
        result_folder: /path/to/results
  """

  def __init__(self):
    """Initialize PipelineEngine."""
    self._config: Optional[Dict[str, Any]] = None
    self._dataset = None
    self._harness = None
    self._evaluator = None
    self._tracker_outputs = None

  def load_configuration(self, config_path: str) -> 'PipelineEngine':
    """Load and parse YAML configuration file.

    This method:
    1. Loads and parses the YAML configuration file
    2. Imports dataset, harness, and evaluator modules
    3. Creates instances of the component classes
    4. Configures each instance with parameters from config file

    Args:
      config_path: Path to YAML configuration file.

    Returns:
      Self for method chaining.

    Raises:
      FileNotFoundError: If configuration file doesn't exist.
      ValueError: If configuration is invalid or missing required fields.
      ImportError: If component class cannot be imported.
      RuntimeError: On other errors during configuration.
    """
    config_path = Path(config_path)
    if not config_path.exists():
      raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Load YAML configuration
    try:
      with open(config_path, 'r') as f:
        self._config = yaml.safe_load(f)
    except yaml.YAMLError as e:
      raise ValueError(f"Failed to parse YAML configuration: {e}") from e

    # Validate configuration structure
    self._validate_configuration()

    # Import and instantiate components
    try:
      self._dataset = self._create_component('dataset')
      self._harness = self._create_component('harness')
      self._evaluator = self._create_component('evaluator')
    except Exception as e:
      raise RuntimeError(f"Failed to create components: {e}") from e

    # Configure components
    try:
      self._configure_dataset()
      self._configure_harness()
      self._configure_evaluator()
    except Exception as e:
      raise RuntimeError(f"Failed to configure components: {e}") from e

    return self

  def run(self) -> 'PipelineEngine':
    """Run the tracker on the dataset.

    Executes the tracker harness with inputs from the dataset and
    stores the tracker outputs for evaluation.

    Returns:
      Self for method chaining.

    Raises:
      RuntimeError: If configuration not loaded or tracker execution fails.
    """
    if self._dataset is None or self._harness is None:
      raise RuntimeError(
        "Configuration not loaded. Call load_configuration() first."
      )

    try:
      # Get inputs from dataset
      inputs = self._dataset.get_inputs()

      # Configure harness with scene config
      scene_config = self._dataset.get_scene_config()
      self._harness.set_scene_config(scene_config)

      # Run tracker
      self._tracker_outputs = self._harness.process_inputs(inputs)

      return self

    except Exception as e:
      raise RuntimeError(f"Tracker execution failed: {e}") from e

  def evaluate(self) -> Dict[str, float]:
    """Evaluate metrics based on dataset ground-truth.

    Computes tracking quality metrics by comparing tracker outputs
    against ground-truth data from the dataset.

    Returns:
      Dictionary mapping metric names to computed values.

    Raises:
      RuntimeError: If tracker hasn't been run or evaluation fails.
    """
    if self._tracker_outputs is None:
      raise RuntimeError(
        "Tracker outputs not available. Call run() first."
      )

    if self._evaluator is None:
      raise RuntimeError(
        "Evaluator not configured. Call load_configuration() first."
      )

    try:
      # Get ground truth from dataset
      ground_truth = self._dataset.get_ground_truth()

      # Process tracker outputs and ground truth
      self._evaluator.process_tracker_outputs(
        tracker_outputs=self._tracker_outputs,
        ground_truth=ground_truth
      )

      # Evaluate metrics
      metrics = self._evaluator.evaluate_metrics()

      return metrics

    except Exception as e:
      raise RuntimeError(f"Metric evaluation failed: {e}") from e

  def _validate_configuration(self):
    """Validate configuration structure.

    Raises:
      ValueError: If configuration is missing required fields.
    """
    if not isinstance(self._config, dict):
      raise ValueError("Configuration must be a dictionary")

    required_sections = ['dataset', 'harness', 'evaluator']
    for section in required_sections:
      if section not in self._config:
        raise ValueError(f"Configuration missing required section: {section}")

      if 'class' not in self._config[section]:
        raise ValueError(f"Section '{section}' missing 'class' field")

      if 'config' not in self._config[section]:
        raise ValueError(f"Section '{section}' missing 'config' field")

  def _create_component(self, component_type: str):
    """Dynamically import and instantiate a component.

    Args:
      component_type: Component type ('dataset', 'harness', or 'evaluator').

    Returns:
      Instantiated component object.

    Raises:
      ImportError: If module or class cannot be imported.
    """
    class_path = self._config[component_type]['class']

    # Split into module path and class name
    parts = class_path.split('.')
    class_name = parts[-1]
    module_path = '.'.join(parts[:-1])

    # Import module
    try:
      module = importlib.import_module(module_path)
    except ImportError as e:
      raise ImportError(
        f"Failed to import module '{module_path}': {e}"
      ) from e

    # Get class from module
    if not hasattr(module, class_name):
      raise ImportError(
        f"Module '{module_path}' does not have class '{class_name}'"
      )

    component_class = getattr(module, class_name)

    # Instantiate component
    # Check if constructor needs arguments
    component_config = self._config[component_type]['config']

    # For harness, check if container_image is in config (constructor argument)
    if component_type == 'harness' and 'container_image' in component_config:
      return component_class(container_image=component_config['container_image'])

    # For dataset, check if data_path is in config (constructor argument)
    if component_type == 'dataset' and 'data_path' in component_config:
      return component_class(component_config['data_path'])

    # Default: no-argument constructor
    return component_class()

  def _configure_dataset(self):
    """Configure dataset component."""
    config = self._config['dataset']['config']

    # Configure cameras if specified
    if 'cameras' in config:
      self._dataset.set_cameras(config['cameras'])

    # Configure camera FPS if specified
    if 'camera_fps' in config:
      self._dataset.set_camera_fps(config['camera_fps'])

    # Configure scene if specified
    if 'scene' in config:
      self._dataset.set_scene(config['scene'])

    # Configure time range if specified
    if 'start_time' in config or 'end_time' in config:
      start = config.get('start_time')
      end = config.get('end_time')
      self._dataset.set_time_range(start, end)

    # Configure custom config if specified
    if 'custom_config' in config:
      self._dataset.set_custom_config(config['custom_config'])

  def _configure_harness(self):
    """Configure harness component."""
    config = self._config['harness']['config']

    # Set tracker config path (required for SceneControllerHarness)
    custom_config = {}

    if 'tracker_config_path' in config:
      custom_config['tracker_config_path'] = config['tracker_config_path']

    # Add any additional custom configuration
    if 'custom_config' in config:
      custom_config.update(config['custom_config'])

    if custom_config:
      self._harness.set_custom_config(custom_config)

  def _configure_evaluator(self):
    """Configure evaluator component."""
    config = self._config['evaluator']['config']

    # Configure metrics if specified
    if 'metrics' in config:
      self._evaluator.configure_metrics(config['metrics'])

    # Configure result folder if specified
    if 'result_folder' in config:
      result_folder = Path(config['result_folder'])
      self._evaluator.set_result_folder(result_folder)


def main():
  """Main entry point for running pipeline from command line.

  Usage:
    python -m pipeline_engine config.yaml
  """
  if len(sys.argv) != 2:
    print("Usage: python -m pipeline_engine <config.yaml>")
    sys.exit(1)

  config_path = sys.argv[1]

  try:
    # Create pipeline engine
    engine = PipelineEngine()

    # Load configuration
    print(f"Loading configuration from {config_path}...")
    engine.load_configuration(config_path)

    # Run tracker
    print("Running tracker...")
    engine.run()

    # Evaluate metrics
    print("Evaluating metrics...")
    metrics = engine.evaluate()

    # Print results
    print("\n=== Evaluation Results ===")
    for metric_name, metric_value in metrics.items():
      print(f"{metric_name}: {metric_value:.4f}")

  except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
  main()
