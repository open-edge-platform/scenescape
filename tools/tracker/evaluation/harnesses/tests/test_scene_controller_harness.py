# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for SceneControllerHarness implementation."""

import pytest
import sys
import json
import tempfile
from pathlib import Path
import jsonschema

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from harnesses.scene_controller_harness import SceneControllerHarness

# Path to schemas
SCHEMA_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / \
  "tracker" / "schema"


@pytest.fixture
def harness():
  """Create SceneControllerHarness instance."""
  return SceneControllerHarness()


@pytest.fixture
def sample_scene_config():
  """Create sample raw scene configuration."""
  return {
    "name": "Test_Scene",
    "map": "test_map.png",
    "scale": 38.1,
    "sensors": {
      "Cam_x1_0": {
        "camera points": [[201, 119], [592, 118]],
        "map points": [[3, 15, 0], [10, 15, 0]],
        "intrinsics": [964.24, 964.63, 400.0, 300.0],
        "width": 800.0,
        "height": 600.0
      }
    }
  }


@pytest.fixture
def tracker_config_file(tmp_path):
  """Create temporary tracker config file."""
  config = {
    "max_unreliable_time_s": 2.0,
    "non_measurement_time_dynamic_s": 1.0,
    "non_measurement_time_static_s": 3.0,
    "time_chunking_enabled": False,
    "ref_camera_frame_rate": 30
  }
  config_file = tmp_path / "tracker-config.json"
  with open(config_file, 'w') as f:
    json.dump(config, f)
  return str(config_file)


@pytest.fixture
def scene_data_schema():
  """Load scene-data.schema.json for output validation."""
  schema_file = SCHEMA_PATH / "scene-data.schema.json"
  with open(schema_file, 'r') as f:
    return json.load(f)


class TestInitialization:
  """Test harness initialization."""

  def test_init(self, harness):
    """Test harness can be instantiated."""
    assert harness is not None
    assert harness._scene_config is None
    assert harness._container_image is None
    assert harness._tracker_config_path is None


class TestConfiguration:
  """Test configuration methods."""

  def test_set_scene_config_valid(self, harness, sample_scene_config):
    """Test setting valid scene config."""
    result = harness.set_scene_config(sample_scene_config)
    assert result is harness  # Method chaining
    assert harness._scene_config == sample_scene_config

  def test_set_scene_config_invalid_type(self, harness):
    """Test setting invalid scene config type."""
    with pytest.raises(ValueError, match="must be a dictionary"):
      harness.set_scene_config("not a dict")

  def test_set_scene_config_missing_name(self, harness):
    """Test setting scene config without name."""
    with pytest.raises(ValueError, match="must contain 'name'"):
      harness.set_scene_config({"sensors": {}})

  def test_set_custom_config_valid(self, harness, tracker_config_file):
    """Test setting valid custom config."""
    config = {
      "container_image": "scenescape-controller:test",
      "tracker_config_path": tracker_config_file
    }
    result = harness.set_custom_config(config)
    assert result is harness  # Method chaining
    assert harness._container_image == "scenescape-controller:test"
    assert harness._tracker_config_path == tracker_config_file

  def test_set_custom_config_invalid_type(self, harness):
    """Test setting invalid custom config type."""
    with pytest.raises(ValueError, match="must be a dictionary"):
      harness.set_custom_config("not a dict")

  def test_set_custom_config_missing_container_image(self, harness, tracker_config_file):
    """Test setting custom config without container_image."""
    with pytest.raises(ValueError, match="must contain 'container_image'"):
      harness.set_custom_config({"tracker_config_path": tracker_config_file})

  def test_set_custom_config_missing_tracker_config(self, harness):
    """Test setting custom config without tracker_config_path."""
    with pytest.raises(ValueError, match="must contain 'tracker_config_path'"):
      harness.set_custom_config({"container_image": "test:latest"})

  def test_set_custom_config_invalid_tracker_path(self, harness):
    """Test setting custom config with non-existent tracker config."""
    with pytest.raises(ValueError, match="not found"):
      harness.set_custom_config({
        "container_image": "test:latest",
        "tracker_config_path": "/nonexistent/path.json"
      })

  def test_set_callback_outputs_ready(self, harness):
    """Test setting outputs callback."""
    def callback(outputs):
      pass

    result = harness.set_callback_outputs_ready(callback)
    assert result is harness  # Method chaining
    assert harness._callback_outputs_ready is callback

  def test_set_callback_on_failure(self, harness):
    """Test setting failure callback."""
    def callback(timestamp, error):
      pass

    result = harness.set_callback_on_failure(callback)
    assert result is harness  # Method chaining
    assert harness._callback_on_failure is callback

  def test_reset(self, harness, sample_scene_config, tracker_config_file):
    """Test reset method."""
    # Configure harness
    harness.set_scene_config(sample_scene_config)
    harness.set_custom_config({
      "container_image": "test:latest",
      "tracker_config_path": tracker_config_file
    })

    # Reset
    result = harness.reset()
    assert result is harness  # Method chaining
    assert harness._scene_config is None
    assert harness._container_image is None
    assert harness._tracker_config_path is None


class TestProcessInputs:
  """Test process_inputs method."""

  def test_process_inputs_without_scene_config(self, harness):
    """Test process_inputs fails without scene config."""
    with pytest.raises(RuntimeError, match="Scene config not set"):
      harness.process_inputs(iter([]))

  def test_process_inputs_without_custom_config(self, harness, sample_scene_config):
    """Test process_inputs fails without custom config."""
    harness.set_scene_config(sample_scene_config)
    with pytest.raises(RuntimeError, match="Custom config not set"):
      harness.process_inputs(iter([]))


class TestMethodChaining:
  """Test method chaining."""

  def test_method_chaining(self, harness, sample_scene_config, tracker_config_file):
    """Test all methods support chaining."""
    result = harness \
      .set_scene_config(sample_scene_config) \
      .set_custom_config({
        "container_image": "test:latest",
        "tracker_config_path": tracker_config_file
      }) \
      .set_callback_outputs_ready(lambda x: None) \
      .set_callback_on_failure(lambda x, y: None)

    assert result is harness


class TestOutputValidation:
  """Test output validation against canonical schema."""

  def test_validate_outputs_against_schema(self, scene_data_schema):
    """Test that tracker outputs conform to scene-data.schema.json."""
    # Sample tracker output matching scene-data schema
    sample_output = {
      "id": "3bc091c7-e449-46a0-9540-29c499bca18c",
      "name": "Retail",
      "timestamp": "2026-01-20T10:05:01.590Z",
      "objects": [
        {
          "id": "8cce2bc7-51fc-4a6e-8c5d-a73ac72d3eb2",
          "category": "person",
          "translation": [-0.33, 2.48, 0.0],
          "velocity": [-0.04, 0.2, 0.0],
          "size": [0.5, 0.5, 1.85],
          "rotation": [0, 0, 0, 1]
        }
      ]
    }

    # Validate against schema
    jsonschema.validate(instance=sample_output, schema=scene_data_schema)

  def test_validate_empty_outputs(self, scene_data_schema):
    """Test validation of outputs with no objects."""
    sample_output = {
      "id": "3bc091c7-e449-46a0-9540-29c499bca18c",
      "name": "Retail",
      "timestamp": "2026-01-20T10:05:01.590Z",
      "objects": []
    }
    
    # Validate against schema
    jsonschema.validate(instance=sample_output, schema=scene_data_schema)
