# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for SceneControllerHarness implementation."""

import pytest
import sys
import json
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from harnesses.scene_controller_harness import SceneControllerHarness

# Path to schemas
SCHEMA_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / \
  "tracker" / "schema"


@pytest.fixture
def harness():
  """Create SceneControllerHarness instance."""
  return SceneControllerHarness(container_image='scenescape-controller:test')


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

  def test_init(self):
    """Test basic initialization with container image."""
    harness = SceneControllerHarness(container_image='test:latest')
    assert harness._container_image == 'test:latest'
    assert harness._scene_config is None
    assert harness._tracker_config_path is None


class TestConfiguration:
  """Test configuration methods."""

  def test_set_scene_config_valid(self, harness, sample_scene_config):
    """Test setting valid scene configuration."""
    result = harness.set_scene_config(sample_scene_config)

    assert result is harness  # Method chaining
    assert harness._scene_config == sample_scene_config

  def test_set_scene_config_invalid_type(self, harness):
    """Test setting invalid scene config type."""
    with pytest.raises(ValueError, match="Scene config must be a dictionary"):
      harness.set_scene_config("not a dict")

  def test_set_scene_config_missing_name(self, harness):
    """Test setting scene config without name field."""
    with pytest.raises(ValueError, match="Scene config must contain 'name' field"):
      harness.set_scene_config({"map": "test.png"})

  def test_set_custom_config_valid(self, harness, tracker_config_file):
    """Test setting valid custom configuration."""
    result = harness.set_custom_config({
      "tracker_config_path": tracker_config_file
    })

    assert result is harness  # Method chaining
    assert harness._tracker_config_path == tracker_config_file

  def test_set_custom_config_invalid_type(self, harness):
    """Test setting invalid custom config type."""
    with pytest.raises(ValueError, match="must be a dictionary"):
      harness.set_custom_config("not a dict")

  def test_set_custom_config_missing_tracker_config(self, harness):
    """Test setting custom config without tracker_config_path."""
    with pytest.raises(ValueError, match="must contain 'tracker_config_path'"):
      harness.set_custom_config({})

  def test_set_custom_config_invalid_tracker_path(self, harness):
    """Test setting custom config with non-existent tracker config."""
    with pytest.raises(ValueError, match="not found"):
      harness.set_custom_config({
        "tracker_config_path": "/nonexistent/path.json"
      })

  def test_reset(self, harness, sample_scene_config, tracker_config_file):
    """Test reset method."""
    # Configure harness
    harness.set_scene_config(sample_scene_config)
    harness.set_custom_config({
      "tracker_config_path": tracker_config_file
    })

    # Reset
    result = harness.reset()
    assert result is harness  # Method chaining
    assert harness._scene_config is None
    assert harness._tracker_config_path is None


class TestProcessInputs:
  """Test process_inputs method."""

  def test_process_inputs_without_config(self, harness):
    """Test process_inputs fails without configuration."""
    with pytest.raises(RuntimeError, match="Scene config not set"):
      harness.process_inputs(iter([]))

  def test_process_inputs_without_tracker_config(self, harness, sample_scene_config):
    """Test process_inputs fails without tracker config."""
    # Only set scene config, not tracker config
    harness.set_scene_config(sample_scene_config)
    with pytest.raises(RuntimeError, match="Tracker config not set"):
      harness.process_inputs(iter([]))


class TestMethodChaining:
  """Test method chaining."""

  def test_method_chaining(self, harness, sample_scene_config, tracker_config_file):
    """Test configuration methods support chaining."""
    result = harness \
      .set_scene_config(sample_scene_config) \
      .set_custom_config({
        "tracker_config_path": tracker_config_file
      })

    assert result is harness
