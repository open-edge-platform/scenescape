# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for RollingTerrainDataset (shared logic is covered by the Wildtrack tests)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datasets.rolling_terrain_dataset import RollingTerrainDataset
from utils.format_converters import stream_jsonl

DATASET_PATH = (
  Path(__file__).parent.parent.parent.parent.parent.parent
  / "tests" / "system" / "metric" / "rolling_terrain_dataset"
)
NUM_FRAMES = 685


@pytest.fixture
def dataset(tmp_path):
  ds = RollingTerrainDataset(str(DATASET_PATH))
  ds.set_output_folder(tmp_path / "dataset_outputs")
  return ds


def test_defaults(dataset):
  assert dataset._cameras == ["cam_front_left", "cam_back_right"]
  assert dataset._camera_fps == 20


def test_unsupported_camera_and_fps(dataset):
  with pytest.raises(ValueError, match="Unsupported camera"):
    dataset.set_cameras(["cam0"])
  with pytest.raises(ValueError, match="Unsupported FPS"):
    dataset.set_camera_fps(10)


def test_scene_config_has_sensors_and_absolute_mesh_path(dataset):
  config = dataset.get_scene_config()
  assert set(config["sensors"]) == set(dataset._cameras)
  assert "cameras" not in config
  assert config["map"] == str((DATASET_PATH / "scene.glb").resolve())


def test_inputs_sorted_across_cameras(dataset):
  timestamps = [frame["timestamp"] for frame in dataset.get_inputs()]
  assert len(timestamps) == 2 * NUM_FRAMES
  assert timestamps == sorted(timestamps)


def test_ground_truth_is_non_planar(dataset):
  frames = list(stream_jsonl(dataset.get_ground_truth()))
  assert len(frames) == NUM_FRAMES
  heights = {obj["translation"][2] for frame in frames for obj in frame["objects"]}
  assert max(heights) - min(heights) > 0.5
