# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for WildtrackDataset and the Wildtrack preprocessing helpers.

The adapter tests run against the committed preprocessed artifacts under
``tests/system/metric/wildtrack_dataset``.  The calibration tests exercise the pure
helper functions and do not depend on the (external) raw dataset.
"""

import json
import sys
from pathlib import Path

import numpy as np
import cv2
import pytest
import jsonschema

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datasets.wildtrack_dataset import WildtrackDataset
from datasets.wildtrack import calibration as wt
from utils.format_converters import read_csv_to_dataframe, stream_jsonl

REPO_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent
DATASET_PATH = REPO_ROOT / "tests" / "system" / "metric" / "wildtrack_dataset"
SCHEMA_PATH = REPO_ROOT / "tracker" / "schema"

GT_COLUMNS = ["frame", "id", "x", "y", "z", "conf", "class", "vis"]


@pytest.fixture
def dataset(tmp_path):
  """Create a WildtrackDataset with an output folder configured."""
  ds = WildtrackDataset(str(DATASET_PATH))
  ds.set_output_folder(tmp_path / "dataset_outputs")
  return ds


@pytest.fixture
def camera_data_schema():
  """Load camera-data.schema.json."""
  with open(SCHEMA_PATH / "camera-data.schema.json") as f:
    return json.load(f)


class TestCalibrationHelpers:
  """Unit tests for pure calibration / decoding helpers."""

  def test_camera_id_for_view(self):
    assert wt.camera_id_for_view(0) == "cam0"
    assert wt.camera_id_for_view(6) == "cam6"
    with pytest.raises(ValueError):
      wt.camera_id_for_view(7)

  def test_decode_position_id_origin(self):
    x, y = wt.decode_position_id(0)
    assert x == pytest.approx(-3.0)
    assert y == pytest.approx(-9.0)

  def test_decode_position_id_known(self):
    # positionID 456826 -> grid (346, 951) -> (5.65, 14.775) m.
    x, y = wt.decode_position_id(456826)
    assert x == pytest.approx(5.65)
    assert y == pytest.approx(14.775)

  def test_decode_position_id_out_of_range(self):
    with pytest.raises(ValueError):
      wt.decode_position_id(wt.GRID_WIDTH * wt.GRID_HEIGHT)

  def test_extrinsics_to_pose_roundtrip(self):
    """Canonical pose must reproduce the same projection as raw rvec/tvec."""
    rvec = np.array([[1.759], [0.467], [-0.331]], dtype=np.float64)
    tvec_cm = np.array([[-525.89], [45.40], [986.72]], dtype=np.float64)
    pose = wt.extrinsics_to_pose(rvec, tvec_cm)

    # Rebuild world->camera from the canonical (metres) pose.
    from scipy.spatial.transform import Rotation
    r_cw = Rotation.from_euler("XYZ", pose["rotation"], degrees=True).as_matrix()
    centre_m = np.array(pose["translation"], dtype=np.float64).reshape(3, 1)
    r_wc = r_cw.T
    t_wc_m = -r_wc @ centre_m
    rvec_canon, _ = cv2.Rodrigues(r_wc)

    k = np.array([[1743.4, 0, 934.5], [0, 1735.2, 444.4], [0, 0, 1]], dtype=np.float64)
    point_cm = np.array([[120.0, 350.0, 0.0]], dtype=np.float64)
    point_m = point_cm / wt.CM_PER_M

    px_raw, _ = cv2.projectPoints(point_cm, rvec, tvec_cm, k, None)
    px_canon, _ = cv2.projectPoints(point_m, rvec_canon, t_wc_m, k, None)
    assert px_raw.reshape(2) == pytest.approx(px_canon.reshape(2), abs=1e-3)


class TestInitialization:
  """Test dataset initialization."""

  def test_init_valid_path(self):
    ds = WildtrackDataset(str(DATASET_PATH))
    assert ds._cameras == [f"cam{i}" for i in range(7)]
    assert ds._camera_fps == 2

  def test_init_invalid_path(self):
    with pytest.raises(ValueError, match="Dataset path does not exist"):
      WildtrackDataset("/nonexistent/path")


class TestConfiguration:
  """Test dataset configuration methods."""

  def test_set_cameras_by_int(self, dataset):
    dataset.set_cameras([0, 3, 6])
    assert dataset._cameras == ["cam0", "cam3", "cam6"]

  def test_set_cameras_by_name(self, dataset):
    dataset.set_cameras(["cam1", "cam2"])
    assert dataset._cameras == ["cam1", "cam2"]

  def test_set_cameras_invalid(self, dataset):
    with pytest.raises(ValueError, match="Unsupported camera"):
      dataset.set_cameras([7])

  def test_set_camera_fps_valid(self, dataset):
    dataset.set_camera_fps(2)
    assert dataset._camera_fps == 2

  def test_set_camera_fps_invalid(self, dataset):
    with pytest.raises(ValueError, match="Unsupported FPS"):
      dataset.set_camera_fps(30)

  def test_set_scene_invalid(self, dataset):
    with pytest.raises(NotImplementedError):
      dataset.set_scene("Other")

  def test_set_time_range_invalid(self, dataset):
    with pytest.raises(ValueError, match="Invalid time range"):
      dataset.set_time_range("2024-01-01T00:00:10.000Z", "2024-01-01T00:00:00.000Z")


class TestSceneConfig:
  """Test scene configuration output."""

  def test_scene_config_cameras(self, dataset):
    config = dataset.get_scene_config()
    assert config["name"] == "Wildtrack"
    assert set(config["sensors"].keys()) == {f"cam{i}" for i in range(7)}

  def test_scene_config_has_explicit_extrinsics(self, dataset):
    config = dataset.get_scene_config()
    for cam_id, sensor in config["sensors"].items():
      assert len(sensor["intrinsics"]) == 4
      extr = sensor["extrinsics"]
      assert len(extr["translation"]) == 3
      assert len(extr["rotation"]) == 3
      assert len(extr["scale"]) == 3
      assert "camera points" not in sensor


class TestInputs:
  """Test canonical detection inputs."""

  def test_inputs_single_camera_schema(self, dataset, camera_data_schema):
    dataset.set_cameras([0])
    frames = list(dataset.get_inputs(camera=0))
    assert len(frames) == 400
    for frame in frames[:20]:
      jsonschema.validate(frame, camera_data_schema)
      assert frame["id"] == "cam0"

  def test_inputs_multi_camera_sorted(self, dataset):
    dataset.set_cameras([0, 1, 2])
    timestamps = [frame["timestamp"] for frame in dataset.get_inputs()]
    assert timestamps == sorted(timestamps)
    # Three cameras x 400 frames.
    assert len(timestamps) == 3 * 400

  def test_inputs_normalized_box_matches_pixels(self, dataset):
    config = dataset.get_scene_config()
    fx, fy, cx, cy = config["sensors"]["cam0"]["intrinsics"]
    dataset.set_cameras([0])
    for frame in dataset.get_inputs(camera=0):
      people = frame["objects"].get("person", [])
      if not people:
        continue
      obj = people[0]
      px = obj["bounding_box_px"]
      norm = obj["bounding_box"]
      assert norm["x"] == pytest.approx((px["x"] - cx) / fx)
      assert norm["y"] == pytest.approx((px["y"] - cy) / fy)
      return


class TestGroundTruth:
  """Test ground-truth CSV output."""

  def test_ground_truth_format(self, dataset):
    gt_path = dataset.get_ground_truth()
    df = read_csv_to_dataframe(gt_path, has_header=False, column_names=GT_COLUMNS)
    assert df.shape[1] == 8
    # Frame numbers are 1-indexed and within [1, 400].
    assert df["frame"].min() == 1
    assert df["frame"].max() == 400
    # z is always 0, class/conf/visibility constants.
    assert (df["z"] == 0).all()
    assert (df["conf"] == 1.0).all()
    assert (df["class"] == 1).all()

  def test_ground_truth_row_count_matches_source(self, dataset):
    gt_path = dataset.get_ground_truth()
    df = read_csv_to_dataframe(gt_path, has_header=False, column_names=GT_COLUMNS)
    source_rows = sum(
      len(entry["objects"].get("person", []))
      for entry in stream_jsonl(str(DATASET_PATH / "gtLoc.json"))
    )
    assert len(df) == source_rows

  def test_ground_truth_requires_output_folder(self):
    ds = WildtrackDataset(str(DATASET_PATH))
    with pytest.raises(RuntimeError, match="output folder not configured"):
      ds.get_ground_truth()


class TestReset:
  """Test reset behavior."""

  def test_reset(self, dataset):
    dataset.set_cameras([0]).set_time_range("2024-01-01T00:00:00.000Z")
    dataset.reset()
    assert dataset._cameras == [f"cam{i}" for i in range(7)]
    assert dataset._time_start is None
