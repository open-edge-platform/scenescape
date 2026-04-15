# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for CameraProjectionHarness."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from harnesses.camera_projection_harness import CameraProjectionHarness


@pytest.fixture
def harness():
  return CameraProjectionHarness(container_image="scenescape-controller:test")


@pytest.fixture
def sample_scene_config():
  return {
    "name": "Test_Scene",
    "scale": 38.1,
    "sensors": {
      "Cam_x1_0": {
        "camera points": [[201, 119], [592, 118], [781, 579], [2, 579]],
        "map points": [[3, 15, 0], [10, 15, 0], [10, 5, 0], [3, 5, 0]],
        "intrinsics": [964.24, 964.63, 400.0, 300.0],
        "width": 800.0,
        "height": 600.0,
      }
    },
  }


@pytest.fixture
def sample_inputs():
  return [
    {
      "timestamp": "2024-01-01T00:00:00.000Z",
      "id": "Cam_x1_0",
      "frame": 0,
      "objects": {
        "person": [
          {
            "id": 0,
            "category": "person",
            "confidence": 1.0,
            "bounding_box": {"x": -0.105, "y": -0.174, "height": 0.092, "width": 0.029},
          }
        ]
      },
    }
  ]


class TestInitialization:
  def test_init_default_image(self):
    h = CameraProjectionHarness()
    assert h._container_image == "scenescape-controller:latest"

  def test_init_custom_image(self):
    h = CameraProjectionHarness(container_image="my-image:v1")
    assert h._container_image == "my-image:v1"

  def test_initial_state(self, harness):
    assert harness._scene_config is None
    assert harness._output_folder is None
    assert harness._temp_dir is None
    assert harness._object_classes == []


class TestSetSceneConfig:
  def test_valid_config(self, harness, sample_scene_config):
    result = harness.set_scene_config(sample_scene_config)
    assert result is harness  # method chaining
    assert harness._scene_config == sample_scene_config

  def test_invalid_type(self, harness):
    with pytest.raises(ValueError, match="must be a dictionary"):
      harness.set_scene_config("not a dict")

  def test_missing_sensors(self, harness):
    with pytest.raises(ValueError, match="'sensors'"):
      harness.set_scene_config({"name": "test"})

  def test_missing_name(self, harness):
    with pytest.raises(ValueError, match="'name'"):
      harness.set_scene_config({"sensors": {}})


class TestSetCustomConfig:
  def test_override_container_image(self, harness):
    harness.set_custom_config({"container_image": "other:latest"})
    assert harness._container_image == "other:latest"

  def test_empty_config(self, harness):
    original_image = harness._container_image
    harness.set_custom_config({})
    assert harness._container_image == original_image

  def test_invalid_type(self, harness):
    with pytest.raises(ValueError, match="must be a dictionary"):
      harness.set_custom_config("bad")

  def test_object_classes_stored(self, harness):
    """set_custom_config stores the object_classes list."""
    classes = [{"name": "person", "shift_type": 1, "x_size": 0.5, "y_size": 0.5}]
    harness.set_custom_config({"object_classes": classes})
    assert harness._object_classes == classes

  def test_object_classes_empty_list_accepted(self, harness):
    """set_custom_config accepts an empty object_classes list."""
    harness.set_custom_config({"object_classes": []})
    assert harness._object_classes == []


class TestSetOutputFolder:
  def test_creates_directory(self, harness, tmp_path):
    folder = tmp_path / "harness_out" / "sub"
    harness.set_output_folder(folder)
    assert folder.exists()
    assert harness._output_folder == folder

  def test_accepts_string_path(self, harness, tmp_path):
    harness.set_output_folder(str(tmp_path))
    assert harness._output_folder == tmp_path


class TestProcessInputsValidation:
  def test_raises_without_scene_config(self, harness, sample_inputs):
    with pytest.raises(RuntimeError, match="Scene config not set"):
      list(harness.process_inputs(iter(sample_inputs)))


class TestReset:
  def test_reset_clears_state(self, harness, sample_scene_config, tmp_path):
    harness.set_scene_config(sample_scene_config)
    harness.set_output_folder(tmp_path)
    harness.reset()
    assert harness._scene_config is None
    assert harness._output_folder is None

  def test_reset_clears_object_classes(self, harness):
    """reset() removes any stored object_classes."""
    harness.set_custom_config({"object_classes": [{"name": "person"}]})
    harness.reset()
    assert harness._object_classes == []


class TestProcessInputsFull:
  def test_process_inputs_success(
    self, harness, sample_scene_config, sample_inputs, tmp_path
  ):
    """process_inputs returns projected output when container succeeds."""
    harness.set_scene_config(sample_scene_config)
    harness.set_output_folder(tmp_path)

    expected = [{"timestamp": "2024-01-01T00:00:00.000Z", "objects": []}]

    def fake_run_container():
      (harness._temp_dir / "output.json").write_text(json.dumps(expected))

    harness._run_container = fake_run_container
    result = list(harness.process_inputs(iter(sample_inputs)))
    assert result == expected

  def test_process_inputs_container_failure_raises(
    self, harness, sample_scene_config, sample_inputs
  ):
    """process_inputs raises RuntimeError when the container fails."""
    harness.set_scene_config(sample_scene_config)

    def fail_run_container():
      raise RuntimeError("Docker not available")

    harness._run_container = fail_run_container
    with pytest.raises(RuntimeError, match="Projection processing failed"):
      list(harness.process_inputs(iter(sample_inputs)))

  def test_process_inputs_missing_output_raises(
    self, harness, sample_scene_config, sample_inputs
  ):
    """process_inputs raises when container exits without writing output.json."""
    harness.set_scene_config(sample_scene_config)

    harness._run_container = lambda: None  # does NOT write output.json
    with pytest.raises(RuntimeError, match="Projection processing failed|no output.json"):
      list(harness.process_inputs(iter(sample_inputs)))


class TestPrivateHelpers:
  def test_copy_projection_script(self, harness, sample_scene_config, tmp_path):
    """_copy_projection_script copies run_projection.py into _temp_dir."""
    harness.set_scene_config(sample_scene_config)
    harness._temp_dir = tmp_path / "workdir"
    harness._temp_dir.mkdir()
    harness._copy_projection_script()
    assert (harness._temp_dir / "run_projection.py").exists()

  def test_persist_artifact_with_output_folder(self, harness, tmp_path):
    """_persist_artifact copies the file when output folder is set."""
    source = tmp_path / "data.txt"
    source.write_text("hello")
    harness.set_output_folder(tmp_path / "out")
    harness._persist_artifact(source, "copy.txt")
    assert (tmp_path / "out" / "copy.txt").exists()

  def test_persist_artifact_noop_without_folder(self, harness, tmp_path):
    """_persist_artifact does nothing when no output folder is configured."""
    source = tmp_path / "data.txt"
    source.write_text("hello")
    harness._persist_artifact(source, "copy.txt")  # must not raise
    assert not (tmp_path / "copy.txt").exists()
