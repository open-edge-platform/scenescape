# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for UnityDataset implementation."""

import pytest
import sys
import json
from pathlib import Path
from typing import Optional
from itertools import groupby
import jsonschema

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datasets.unity_dataset import UnityDataset
from utils.format_converters import stream_jsonl

# Path to test dataset
DATASET_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / \
  "tests" / "system" / "metric" / "unity_dataset"

# Path to schemas
SCHEMA_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / \
  "tracker" / "schema"


def _collect_expected_gt_entries(
  start: Optional[str] = None,
  end: Optional[str] = None,
  camera_fps: float = UnityDataset.DEFAULT_FPS
):
  """Collect raw ground-truth frames honoring time range and FPS stride."""
  gt_file = DATASET_PATH / "gtLoc.json"
  if camera_fps <= 0:
    raise ValueError("camera_fps must be positive")

  stride_ratio = UnityDataset.DEFAULT_FPS / camera_fps
  stride = int(round(stride_ratio))

  if stride <= 0 or abs(stride - stride_ratio) > 1e-6:
    raise ValueError("Ground truth FPS (30) must be divisible by camera FPS")

  entries = []
  for frame_idx, entry in enumerate(stream_jsonl(str(gt_file))):
    timestamp = entry.get("timestamp")
    if timestamp is None:
      continue

    if end is not None and timestamp > end:
      break
    if start is not None and timestamp < start:
      continue
    if frame_idx % stride != 0:
      continue

    entries.append(entry)

  return entries


def _count_objects(entries):
  """Return total number of objects across the provided GT entries."""
  total = 0
  for entry in entries:
    objects = entry.get("objects", {})
    for category_objects in objects.values():
      total += len(category_objects)
  return total


def _gt_objects(gt_frames):
  """Flatten canonical GT JSONL frames into a list of objects."""
  return [obj for frame in gt_frames for obj in frame["objects"]]


@pytest.fixture
def dataset(tmp_path):
  """Create UnityDataset instance with output folder configured."""
  ds = UnityDataset(str(DATASET_PATH))
  ds.set_output_folder(tmp_path / "dataset_outputs")
  return ds


@pytest.fixture
def scene_schema():
  """Load scene.schema.json."""
  schema_file = SCHEMA_PATH / "scene.schema.json"
  with open(schema_file, 'r') as f:
    return json.load(f)


@pytest.fixture
def camera_data_schema():
  """Load camera-data.schema.json."""
  schema_file = SCHEMA_PATH / "camera-data.schema.json"
  with open(schema_file, 'r') as f:
    return json.load(f)


class TestInitialization:
  """Test dataset initialization."""

  def test_init_valid_path(self):
    """Test initialization with valid dataset path."""
    ds = UnityDataset(str(DATASET_PATH))
    assert ds._dataset_path == DATASET_PATH
    assert ds._cameras == ["Cam_x1_0", "Cam_x2_0"]
    assert ds._camera_fps == 30

  def test_init_invalid_path(self):
    """Test initialization with invalid path."""
    with pytest.raises(ValueError, match="Dataset path does not exist"):
      UnityDataset("/nonexistent/path")


class TestConfiguration:
  """Test dataset configuration methods."""

  def test_set_scene_default(self, dataset):
    """Test set_scene with default (None)."""
    result = dataset.set_scene(None)
    assert result is dataset  # Method chaining

  def test_set_scene_retail_demo(self, dataset):
    """Test set_scene with Unity."""
    result = dataset.set_scene("Unity")
    assert result is dataset

  def test_set_scene_unsupported(self, dataset):
    """Test set_scene with unsupported scene."""
    with pytest.raises(NotImplementedError, match="Only 'Unity' scene"):
      dataset.set_scene("UnknownScene")

  def test_set_cameras_default(self, dataset):
    """Test set_cameras with default (None)."""
    dataset.set_cameras(["Cam_x1_0"])
    result = dataset.set_cameras(None)
    assert result is dataset
    assert dataset._cameras == ["Cam_x1_0", "Cam_x2_0"]

  def test_set_cameras_subset(self, dataset):
    """Test set_cameras with valid subset."""
    result = dataset.set_cameras(["Cam_x1_0"])
    assert result is dataset
    assert dataset._cameras == ["Cam_x1_0"]

  def test_set_cameras_unsupported(self, dataset):
    """Test set_cameras with unsupported camera."""
    with pytest.raises(ValueError, match="Unsupported camera"):
      dataset.set_cameras(["Cam_x3_0"])

  def test_set_time_range_filters_single_camera(self, dataset):
    """Test set_time_range filters frames inclusively for a camera."""
    start = "2014-09-08T04:00:00.264Z"
    end = "2014-09-08T04:00:00.561Z"

    dataset.set_cameras(["Cam_x1_0"]).set_time_range(start, end)
    inputs = list(dataset.get_inputs("Cam_x1_0"))

    assert inputs
    timestamps = [frame["timestamp"] for frame in inputs]
    assert all(start <= ts <= end for ts in timestamps)
    assert start in timestamps
    assert end in timestamps

  def test_set_time_range_open_start(self, dataset):
    """Test set_time_range handles None start (earliest timestamp)."""
    end = "2014-09-08T04:00:00.198Z"
    dataset.set_cameras(["Cam_x1_0"]).set_time_range(None, end)

    inputs = list(dataset.get_inputs("Cam_x1_0"))
    assert inputs
    assert inputs[-1]["timestamp"] == end

  def test_set_time_range_open_end(self, dataset):
    """Test set_time_range handles None end (latest timestamp)."""
    start = "2014-09-08T04:00:00.990Z"
    dataset.set_cameras(["Cam_x1_0"]).set_time_range(start, None)

    inputs = list(dataset.get_inputs("Cam_x1_0"))
    assert inputs
    assert inputs[0]["timestamp"] == start

  def test_set_time_range_invalid_order(self, dataset):
    """Test set_time_range validates start <= end when both provided."""
    with pytest.raises(ValueError, match="Invalid time range"):
      dataset.set_time_range(
        "2014-09-08T04:00:01.000Z",
        "2014-09-08T04:00:00.500Z"
      )

  def test_set_time_range_reset_restores_full_sequence(self, dataset):
    """Test reset clears time range filters for subsequent reads."""
    dataset.set_cameras(["Cam_x1_0"])
    full_inputs = list(dataset.get_inputs("Cam_x1_0"))

    dataset.set_time_range(
      "2014-09-08T04:00:00.264Z",
      "2014-09-08T04:00:00.561Z"
    )
    filtered_inputs = list(dataset.get_inputs("Cam_x1_0"))
    assert len(filtered_inputs) < len(full_inputs)

    dataset.reset().set_cameras(["Cam_x1_0"])
    reset_inputs = list(dataset.get_inputs("Cam_x1_0"))
    assert len(reset_inputs) == len(full_inputs)

  def test_set_camera_fps_valid(self, dataset):
    """Test set_camera_fps with valid FPS values."""
    for fps in [1, 10, 30]:
      result = dataset.set_camera_fps(fps)
      assert result is dataset
      assert dataset._camera_fps == fps

  def test_set_camera_fps_invalid(self, dataset):
    """Test set_camera_fps with invalid FPS."""
    with pytest.raises(ValueError, match="Unsupported FPS"):
      dataset.set_camera_fps(60)

  def test_set_custom_config_not_supported(self, dataset):
    """Test set_custom_config raises NotImplementedError."""
    with pytest.raises(NotImplementedError, match="Custom configuration"):
      dataset.set_custom_config({"key": "value"})

  def test_reset(self, dataset):
    """Test reset method."""
    dataset.set_cameras(["Cam_x1_0"]).set_camera_fps(10).set_time_range(
      "2014-09-08T04:00:00.033Z",
      "2014-09-08T04:00:00.165Z"
    )
    result = dataset.reset()
    assert result is dataset
    assert dataset._cameras == ["Cam_x1_0", "Cam_x2_0"]
    assert dataset._camera_fps == 30
    assert dataset._scene_config is None
    assert dataset._time_start is None
    assert dataset._time_end is None
    assert dataset._output_folder is None


class TestSceneConfig:
  """Test get_scene_config method."""

  def test_get_scene_config_structure(self, dataset):
    """Test scene config has correct structure (raw format)."""
    config = dataset.get_scene_config()

    # Verify raw config.json structure
    assert "name" in config
    assert "sensors" in config
    assert "map" in config
    assert "scale" in config
    assert config["name"] == "Unity"

  @pytest.mark.xfail(reason="Scene config format not yet aligned with canonical schema")
  def test_get_scene_config_matches_schema(self, dataset, scene_schema):
    """Test scene config matches JSON schema.

    This test is expected to fail because get_scene_config() currently returns
    dataset-specific format (raw config.json) instead of canonical format.
    """
    config = dataset.get_scene_config()
    jsonschema.validate(instance=config, schema=scene_schema)

  def test_get_scene_config_sensors_structure(self, dataset):
    """Test scene config sensors structure (raw format)."""
    config = dataset.get_scene_config()

    # Verify sensors structure (dataset-specific format)
    sensors = config["sensors"]
    assert isinstance(sensors, dict)
    assert "Cam_x1_0" in sensors
    assert "Cam_x2_0" in sensors

    for camera_name in ["Cam_x1_0", "Cam_x2_0"]:
      camera = sensors[camera_name]
      assert "camera points" in camera
      assert "map points" in camera
      assert "intrinsics" in camera
      assert "width" in camera
      assert "height" in camera



class TestGetInputs:
  """Test get_inputs method."""

  def test_get_inputs_30fps(self, dataset):
    """Test get_inputs with default 30 FPS."""
    dataset.set_camera_fps(30).set_cameras(["Cam_x1_0"])
    inputs = list(dataset.get_inputs("Cam_x1_0"))

    assert len(inputs) > 0
    assert all("timestamp" in inp for inp in inputs)
    assert all("id" in inp for inp in inputs)
    assert all("objects" in inp for inp in inputs)

  def test_get_inputs_1fps(self, dataset):
    """Test get_inputs with 1 FPS."""
    dataset.set_camera_fps(1).set_cameras(["Cam_x1_0"])
    inputs = list(dataset.get_inputs("Cam_x1_0"))

    assert len(inputs) > 0
    # 1 FPS should have fewer frames
    assert len(inputs) < 100  # Approximately 30-80 frames

  def test_get_inputs_10fps(self, dataset):
    """Test get_inputs with 10 FPS."""
    dataset.set_camera_fps(10).set_cameras(["Cam_x1_0"])
    inputs = list(dataset.get_inputs("Cam_x1_0"))

    assert len(inputs) > 0

  def test_get_inputs_matches_schema(self, dataset, camera_data_schema):
    """Test inputs match camera-data schema."""
    dataset.set_cameras(["Cam_x1_0"])
    inputs = list(dataset.get_inputs("Cam_x1_0"))

    # Validate first few inputs
    for inp in inputs[:5]:
      jsonschema.validate(instance=inp, schema=camera_data_schema)

  def test_get_inputs_all_cameras(self, dataset):
    """Test get_inputs without camera arg returns all."""
    dataset.set_cameras(["Cam_x1_0", "Cam_x2_0"])
    inputs = list(dataset.get_inputs())

    # Should get inputs from both cameras
    camera_ids = set(inp["id"] for inp in inputs)
    assert "Cam_x1_0" in camera_ids
    assert "Cam_x2_0" in camera_ids

  def test_get_inputs_unconfigured_camera(self, dataset):
    """Test get_inputs with unconfigured camera."""
    dataset.set_cameras(["Cam_x1_0"])
    with pytest.raises(ValueError, match="not in configured cameras"):
      list(dataset.get_inputs("Cam_x2_0"))

  def test_get_inputs_sorted_by_timestamp(self, dataset):
    """Test get_inputs returns frames sorted by timestamp across all cameras."""
    dataset.set_cameras(["Cam_x1_0", "Cam_x2_0"]).set_camera_fps(30)
    inputs = list(dataset.get_inputs())

    # Convert ISO timestamps to epoch floats for accurate comparison
    # (copied from scene_common.timestamp.get_epoch_time to avoid dependency)
    from datetime import datetime, timezone
    DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"

    def get_epoch_time(timestamp: str) -> float:
      utc_time = datetime.strptime(timestamp, f"{DATETIME_FORMAT}Z").replace(tzinfo=timezone.utc)
      return utc_time.timestamp()

    timestamps = [get_epoch_time(inp["timestamp"]) for inp in inputs]

    assert all(a <= b for a, b in zip(timestamps, timestamps[1:])), \
      "Frames are not sorted by timestamp"

  def _collect_tie_groups(self, inputs):
    """Return timestamp groups where more than one camera appears."""
    tie_groups = []
    for ts, group in groupby(inputs, key=lambda f: f["timestamp"]):
      cam_ids = [f["id"] for f in group]
      if len(cam_ids) > 1:
        tie_groups.append((ts, cam_ids))
    return tie_groups

  def _assert_camera_order_in_tie_groups(self, tie_groups, cameras):
    """Assert every tie group follows the given camera order."""
    assert tie_groups, "No shared timestamps found between cameras — test data changed"
    for ts, cam_ids in tie_groups:
      configured_order = [c for c in cameras if c in cam_ids]
      assert cam_ids == configured_order, (
        f"At timestamp {ts}: camera order {cam_ids} "
        f"does not match configured order {configured_order}"
      )

  def test_get_inputs_preserves_camera_order_for_same_timestamp(self, dataset):
    """Test that get_inputs preserves configured camera order for equal timestamps."""
    cameras = ["Cam_x1_0", "Cam_x2_0"]
    dataset.set_cameras(cameras).set_camera_fps(30)
    inputs = list(dataset.get_inputs())
    tie_groups = self._collect_tie_groups(inputs)
    self._assert_camera_order_in_tie_groups(tie_groups, cameras)

  def test_get_inputs_reversed_camera_order_for_same_timestamp(self, dataset):
    """Test that reversing configured camera order changes output order for equal timestamps."""
    cameras_reversed = ["Cam_x2_0", "Cam_x1_0"]
    dataset.set_cameras(cameras_reversed).set_camera_fps(30)
    inputs = list(dataset.get_inputs())
    tie_groups = self._collect_tie_groups(inputs)
    self._assert_camera_order_in_tie_groups(tie_groups, cameras_reversed)


class TestGetGroundTruth:
  """Test get_ground_truth method."""

  def test_get_ground_truth_returns_path(self, dataset):
    """Test get_ground_truth returns valid file path."""
    gt_path = dataset.get_ground_truth()
    assert isinstance(gt_path, str)
    assert Path(gt_path).exists()
    assert gt_path.endswith('.jsonl')
    expected_path = dataset._output_folder / "ground_truth.jsonl"
    assert Path(gt_path) == expected_path

  def test_get_ground_truth_jsonl_format(self, dataset):
    """Test ground truth JSONL has canonical tracker-output structure."""
    gt_path = dataset.get_ground_truth()

    frames = list(stream_jsonl(gt_path))
    assert len(frames) > 0
    for frame in frames:
      assert "timestamp" in frame
      assert isinstance(frame["objects"], list)
    objects = _gt_objects(frames)
    assert len(objects) > 0
    for obj in objects:
      assert "id" in obj
      assert "category" in obj
      assert len(obj["translation"]) == 3

  def test_get_ground_truth_absolute_timestamps(self, dataset):
    """Ground truth carries the source absolute ISO timestamps."""
    gt_path = dataset.get_ground_truth()

    frames = list(stream_jsonl(gt_path))
    timestamps = [frame["timestamp"] for frame in frames]

    # Timestamps come straight from the source dataset (absolute, ISO 8601).
    assert timestamps[0] == "2014-09-08T04:00:00.033Z"
    # Strictly increasing (chronological order preserved).
    assert timestamps == sorted(timestamps)

  def test_get_ground_truth_coordinates(self, dataset):
    """Test ground truth coordinates are reasonable."""
    gt_path = dataset.get_ground_truth()

    objects = _gt_objects(list(stream_jsonl(gt_path)))
    xs = [obj["translation"][0] for obj in objects]
    ys = [obj["translation"][1] for obj in objects]
    zs = [obj["translation"][2] for obj in objects]

    # Coordinates should be in reasonable range for the scene.
    assert min(xs) >= -1.0
    assert max(xs) <= 12.0
    assert min(ys) >= -1.0
    assert max(ys) <= 16.0
    assert min(zs) == 0.0  # Ground plane

  def test_get_ground_truth_respects_time_range(self, dataset):
    """Ground truth should only include frames inside configured time range."""
    start = "2014-09-08T04:00:00.033Z"
    end = "2014-09-08T04:00:00.330Z"
    dataset.set_time_range(start, end)

    gt_path = dataset.get_ground_truth()
    frames = list(stream_jsonl(gt_path))

    expected_entries = _collect_expected_gt_entries(start=start, end=end)
    expected_timestamps = [entry["timestamp"] for entry in expected_entries]

    assert [frame["timestamp"] for frame in frames] == expected_timestamps
    assert len(_gt_objects(frames)) == _count_objects(expected_entries)

  def test_get_ground_truth_respects_camera_fps_sampling(self, dataset):
    """Ground truth should be downsampled to match configured camera FPS."""
    end = "2014-09-08T04:00:00.330Z"
    dataset.set_camera_fps(10).set_time_range(None, end)

    gt_path = dataset.get_ground_truth()
    frames = list(stream_jsonl(gt_path))

    expected_entries = _collect_expected_gt_entries(end=end, camera_fps=10)
    expected_timestamps = [entry["timestamp"] for entry in expected_entries]

    assert [frame["timestamp"] for frame in frames] == expected_timestamps
    assert len(_gt_objects(frames)) == _count_objects(expected_entries)


class TestIntegration:
  """Integration tests combining multiple operations."""

  def test_full_workflow(self, dataset):
    """Test complete dataset workflow."""
    # Configure
    dataset.set_cameras(["Cam_x1_0"]).set_camera_fps(10)

    # Get scene config (raw format)
    scene_config = dataset.get_scene_config()
    assert "name" in scene_config
    assert "sensors" in scene_config
    assert scene_config["name"] == "Unity"

    # Get inputs
    inputs = list(dataset.get_inputs())
    assert len(inputs) > 0

    # Get ground truth
    gt_path = dataset.get_ground_truth()
    expected_path = dataset._output_folder / "ground_truth.jsonl"
    assert Path(gt_path) == expected_path
    assert Path(gt_path).exists()

    # Reset and verify
    dataset.reset()
    assert dataset._cameras == ["Cam_x1_0", "Cam_x2_0"]
    assert dataset._camera_fps == 30

  def test_method_chaining(self, dataset):
    """Test method chaining works correctly."""
    result = (dataset
              .set_scene("Unity")
              .set_cameras(["Cam_x1_0", "Cam_x2_0"])
              .set_camera_fps(10)
              .reset())

    assert result is dataset


class TestTimestampIntervals:
  """Test timestamp intervals match configured FPS."""

  def _get_epoch_time(self, timestamp: str) -> float:
    """Convert ISO timestamp to epoch seconds."""
    from datetime import datetime, timezone
    DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
    utc_time = datetime.strptime(timestamp, f"{DATETIME_FORMAT}Z").replace(tzinfo=timezone.utc)
    return utc_time.timestamp()

  def _verify_fps_intervals(self, dataset, camera: str, fps: float):
    """Verify timestamp intervals match expected FPS with ~5% tolerance."""
    # Configure dataset
    dataset.set_cameras([camera]).set_camera_fps(fps)

    # Get inputs for the camera
    inputs = list(dataset.get_inputs(camera))

    # Need at least 2 frames to calculate intervals
    assert len(inputs) >= 2, f"Need at least 2 frames for {camera} at {fps} FPS"

    # Extract timestamps and convert to epoch seconds
    timestamps = [self._get_epoch_time(inp["timestamp"]) for inp in inputs]

    # Calculate intervals between consecutive frames
    intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps) - 1)]

    # Expected interval in seconds
    expected_interval = 1.0 / fps

    # Verify all intervals are within 5% of expected
    for i, interval in enumerate(intervals):
      relative_error = abs(interval - expected_interval) / expected_interval
      assert relative_error <= 0.05, \
        f"Frame {i} to {i+1}: interval={interval:.6f}s, expected={expected_interval:.6f}s, " \
        f"relative_error={relative_error*100:.2f}% (max 5%)"

  def test_camera_x1_fps_1(self, dataset):
    """Test camera x1 at 1 FPS has correct timestamp intervals."""
    self._verify_fps_intervals(dataset, "Cam_x1_0", 1)

  def test_camera_x1_fps_10(self, dataset):
    """Test camera x1 at 10 FPS has correct timestamp intervals."""
    self._verify_fps_intervals(dataset, "Cam_x1_0", 10)

  def test_camera_x1_fps_30(self, dataset):
    """Test camera x1 at 30 FPS has correct timestamp intervals."""
    self._verify_fps_intervals(dataset, "Cam_x1_0", 30)

  def test_camera_x2_fps_1(self, dataset):
    """Test camera x2 at 1 FPS has correct timestamp intervals."""
    self._verify_fps_intervals(dataset, "Cam_x2_0", 1)

  def test_camera_x2_fps_10(self, dataset):
    """Test camera x2 at 10 FPS has correct timestamp intervals."""
    self._verify_fps_intervals(dataset, "Cam_x2_0", 10)

  def test_camera_x2_fps_30(self, dataset):
    """Test camera x2 at 30 FPS has correct timestamp intervals."""
    self._verify_fps_intervals(dataset, "Cam_x2_0", 30)


class TestObjectCategories:
  """Test set_object_categories filtering."""

  def test_set_object_categories_returns_self(self, dataset):
    """Method returns self for chaining."""
    result = dataset.set_object_categories(["person"])
    assert result is dataset

  def test_set_object_categories_none_resets(self, dataset):
    """Passing None removes the category filter."""
    dataset.set_object_categories(["person"])
    dataset.set_object_categories(None)
    assert dataset._object_categories is None

  def test_set_object_categories_empty_raises(self, dataset):
    """Empty list raises ValueError."""
    with pytest.raises(ValueError, match="must not be empty"):
      dataset.set_object_categories([])

  def test_inputs_filtered_by_category(self, dataset):
    """Inputs contain only the requested categories."""
    dataset.set_cameras(["Cam_x1_0"]).set_object_categories(["person"])
    inputs = list(dataset.get_inputs("Cam_x1_0"))

    assert len(inputs) > 0
    for frame in inputs:
      assert set(frame["objects"].keys()) <= {"person"}
    # At least some frames should contain person objects
    frames_with_person = [f for f in inputs if "person" in f["objects"]]
    assert len(frames_with_person) > 0

  def test_inputs_multiple_categories(self, dataset):
    """Multiple categories are all included."""
    dataset.set_cameras(["Cam_x1_0"]).set_object_categories(["person", "FW190D"])
    inputs = list(dataset.get_inputs("Cam_x1_0"))

    assert len(inputs) > 0
    categories_seen = set()
    for frame in inputs:
      categories_seen.update(frame["objects"].keys())
    assert categories_seen == {"person", "FW190D"}

  def test_inputs_no_filter_returns_all(self, dataset):
    """Without category filter, all categories are returned."""
    dataset.set_cameras(["Cam_x1_0"])
    inputs = list(dataset.get_inputs("Cam_x1_0"))

    categories_seen = set()
    for frame in inputs:
      categories_seen.update(frame["objects"].keys())
    assert len(categories_seen) >= 2

  def test_inputs_frame_count_unchanged(self, dataset):
    """Category filtering does not change the number of frames."""
    dataset.set_cameras(["Cam_x1_0"])
    all_inputs = list(dataset.get_inputs("Cam_x1_0"))

    dataset.set_object_categories(["person"])
    filtered_inputs = list(dataset.get_inputs("Cam_x1_0"))

    assert len(filtered_inputs) == len(all_inputs)

  def test_ground_truth_filtered_by_category(self, dataset):
    """Ground truth contains fewer objects when filtered by category."""
    gt_all = dataset.get_ground_truth()
    objects_all = _gt_objects(list(stream_jsonl(gt_all)))

    dataset.set_object_categories(["person"])
    gt_filtered = dataset.get_ground_truth()
    objects_filtered = _gt_objects(list(stream_jsonl(gt_filtered)))

    assert len(objects_filtered) < len(objects_all)
    assert len(objects_filtered) > 0

  def test_ground_truth_category_ids_match(self, dataset):
    """Filtered GT only contains object IDs from the requested categories."""
    # In the dataset, "person" category has IDs 0 and 1,
    # "Person" has ID 0, "FW190D" has ID 2
    dataset.set_object_categories(["FW190D"])
    gt_path = dataset.get_ground_truth()
    objects = _gt_objects(list(stream_jsonl(gt_path)))

    assert {obj["id"] for obj in objects} == {2}

  def test_reset_clears_categories(self, dataset):
    """Reset removes the category filter."""
    dataset.set_object_categories(["person"])
    dataset.reset()
    assert dataset._object_categories is None

  def test_multi_camera_inputs_filtered(self, dataset):
    """Category filtering works for multi-camera merge path."""
    dataset.set_cameras(["Cam_x1_0", "Cam_x2_0"])
    dataset.set_object_categories(["person"])
    inputs = list(dataset.get_inputs())

    assert len(inputs) > 0
    for frame in inputs:
      assert set(frame["objects"].keys()) <= {"person"}

