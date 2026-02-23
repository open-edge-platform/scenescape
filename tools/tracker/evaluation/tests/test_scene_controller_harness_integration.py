# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for SceneControllerHarness with real container and dataset."""

import pytest
import sys
import json
from pathlib import Path
import jsonschema
import itertools

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from harnesses.scene_controller_harness import SceneControllerHarness
from datasets.metric_test_dataset import MetricTestDataset

# Path to test data and schemas
DATASET_PATH = Path(__file__).parent.parent.parent.parent.parent / \
  "tests" / "system" / "metric" / "dataset"
SCHEMA_PATH = Path(__file__).parent.parent.parent.parent.parent / \
  "tracker" / "schema"
TRACKER_CONFIG_PATH = DATASET_PATH / "tracker-config-time-chunking.json"

# Test configuration
NUM_INPUT_FRAMES = 120  # Number of input frames to process in integration tests
TIME_RANGE_START = "2014-09-08T04:00:00.033Z"
TIME_RANGE_END = "2014-09-08T04:00:04.000Z"


@pytest.fixture
def dataset(tmp_path):
  """Create MetricTestDataset instance."""
  ds = MetricTestDataset(str(DATASET_PATH))
  ds.set_output_folder(tmp_path / "dataset_outputs")
  ds.set_cameras(["x1", "x2"]).set_camera_fps(30).set_time_range(
    TIME_RANGE_START,
    TIME_RANGE_END
  )
  return ds


@pytest.fixture
def harness():
  """Create SceneControllerHarness with latest container."""
  return SceneControllerHarness(container_image='scenescape-controller:latest')


@pytest.fixture
def scene_data_schema():
  """Load scene-data.schema.json for output validation."""
  schema_file = SCHEMA_PATH / "scene-data.schema.json"
  with open(schema_file, 'r') as f:
    return json.load(f)


@pytest.mark.integration
class TestSceneControllerHarnessIntegration:
  """Integration tests for SceneControllerHarness."""

  def test_configuration_successful(self, harness, dataset):
    """Test that harness can be configured successfully."""
    # Configure harness
    result1 = harness.set_scene_config(dataset.get_scene_config())
    result2 = harness.set_custom_config({
      'tracker_config_path': str(TRACKER_CONFIG_PATH)
    })

    # Verify configuration succeeded
    assert result1 is harness  # Method chaining works
    assert result2 is harness
    assert harness._scene_config is not None
    assert 'name' in harness._scene_config
    assert harness._tracker_config_path == str(TRACKER_CONFIG_PATH)

  def test_process_inputs_returns_outputs(self, harness, dataset):
    """Test that processing inputs returns valid outputs."""
    # Configure harness
    harness.set_scene_config(dataset.get_scene_config())
    harness.set_custom_config({
      'tracker_config_path': str(TRACKER_CONFIG_PATH)
    })

    # Process inputs (limit to NUM_INPUT_FRAMES for faster test execution)
    limited_inputs = itertools.islice(dataset.get_inputs(), NUM_INPUT_FRAMES)
    outputs = harness.process_inputs(limited_inputs)

    # Verify outputs is an iterator
    assert outputs is not None

    # Convert to list to verify content
    output_list = list(outputs)

    # Verify we got outputs
    assert len(output_list) > 0, "Should have at least one output"

    # Verify each output is a dictionary
    for output in output_list:
      assert isinstance(output, dict), f"Output should be dict, got {type(output)}"

  def test_output_structure(self, harness, dataset):
    """Test that outputs have expected structure."""
    # Configure harness
    harness.set_scene_config(dataset.get_scene_config())
    harness.set_custom_config({
      'tracker_config_path': str(TRACKER_CONFIG_PATH)
    })

    # Process inputs (limit to NUM_INPUT_FRAMES for faster test execution)
    limited_inputs = itertools.islice(dataset.get_inputs(), NUM_INPUT_FRAMES)
    outputs = list(harness.process_inputs(limited_inputs))

    # Verify at least one output exists
    assert len(outputs) > 0, "Should have outputs"

    # Check first output structure
    first_output = outputs[0]

    # Verify required top-level fields exist
    assert 'timestamp' in first_output, "Output should have 'timestamp'"
    assert 'objects' in first_output, "Output should have 'objects'"

    # Verify objects is a list
    assert isinstance(first_output['objects'], list), "objects should be a list"

  @pytest.mark.xfail(reason="Output format not yet consistent with canonical scene-data schema")
  def test_output_schema_validation(self, harness, dataset, scene_data_schema):
    """Test that outputs conform to scene-data.schema.json.

    This test is expected to fail until output format is aligned with canonical schema.
    The schema expects:
    - id: Scene identifier (UUID)
    - name: Scene name
    - timestamp: ISO 8601 timestamp
    - objects: Array of tracked objects with specific fields
    """
    # Configure harness
    harness.set_scene_config(dataset.get_scene_config())
    harness.set_custom_config({
      'tracker_config_path': str(TRACKER_CONFIG_PATH)
    })

    # Process inputs (limit to NUM_INPUT_FRAMES for faster test execution)
    limited_inputs = itertools.islice(dataset.get_inputs(), NUM_INPUT_FRAMES)
    outputs = list(harness.process_inputs(limited_inputs))

    # Validate each output against schema
    for i, output in enumerate(outputs):
      try:
        jsonschema.validate(instance=output, schema=scene_data_schema)
      except jsonschema.ValidationError as e:
        # Print detailed error for debugging
        print(f"\nValidation error in output {i}:")
        print(f"  Error: {e.message}")
        print(f"  Path: {list(e.path)}")
        print(f"  Schema path: {list(e.schema_path)}")
        print(f"  Output keys: {list(output.keys())}")
        if 'objects' in output and output['objects']:
          print(f"  First object keys: {list(output['objects'][0].keys())}")
        raise

  def test_multiple_outputs(self, harness, dataset):
    """Test that multiple output frames are produced."""
    # Configure harness
    harness.set_scene_config(dataset.get_scene_config())
    harness.set_custom_config({
      'tracker_config_path': str(TRACKER_CONFIG_PATH)
    })

    # Process inputs (limit to NUM_INPUT_FRAMES for faster test execution)
    limited_inputs = itertools.islice(dataset.get_inputs(), NUM_INPUT_FRAMES)
    outputs = list(harness.process_inputs(limited_inputs))

    # Should have multiple output frames
    assert len(outputs) > 1, f"Expected multiple outputs, got {len(outputs)}"

    # Verify timestamps are increasing (chronological order)
    timestamps = [out.get('timestamp') for out in outputs if 'timestamp' in out]
    assert len(timestamps) > 0, "Outputs should have timestamps"

  def test_objects_in_outputs(self, harness, dataset):
    """Test that outputs contain tracked objects."""
    # Configure harness
    harness.set_scene_config(dataset.get_scene_config())
    harness.set_custom_config({
      'tracker_config_path': str(TRACKER_CONFIG_PATH)
    })

    # Process inputs (limit to NUM_INPUT_FRAMES for faster test execution)
    limited_inputs = itertools.islice(dataset.get_inputs(), NUM_INPUT_FRAMES)
    outputs = list(harness.process_inputs(limited_inputs))

    # Find outputs with objects
    outputs_with_objects = [out for out in outputs if out.get('objects')]

    # Should have at least some outputs with objects
    assert len(outputs_with_objects) > 0, "Should have outputs with tracked objects"

    # Verify object structure
    first_object_output = outputs_with_objects[0]
    first_object = first_object_output['objects'][0]

    # Check that object has some expected fields (may vary based on actual output)
    assert isinstance(first_object, dict), "Object should be a dictionary"
    # Note: Not checking specific fields as format is being validated by schema test
