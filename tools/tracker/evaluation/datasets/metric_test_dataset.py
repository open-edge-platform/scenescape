# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MetricTestDataset implementation for tests/system/metric/test_data dataset."""

from typing import List, Dict, Any, Optional, Iterator
from pathlib import Path
import sys
import rapidjson
import tempfile

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from base.tracking_dataset import TrackingDataset
from utils.format_converters import read_json, convert_json_to_csv


class MetricTestDataset(TrackingDataset):
  """Dataset adapter for tests/system/metric/test_data.

  This dataset contains:
  - Scene: Retail_Demo (single built-in scene)
  - Cameras: x1, x2 (Cam_x1_0, Cam_x2_0)
  - FPS options: 1, 10, 30 (separate JSON files per FPS)
  - Ground truth: gtLoc.json with object locations
  - Scene config: config.json with camera calibration
  """

  # Constants
  SCENE_NAME = "Retail_Demo"
  SUPPORTED_CAMERAS = ["x1", "x2"]
  SUPPORTED_FPS = [1, 10, 30]
  DEFAULT_FPS = 30

  def __init__(self, dataset_path: str):
    """Initialize MetricTestDataset.

    Args:
      dataset_path: Path to tests/system/metric/test_data directory
    """
    self._dataset_path = Path(dataset_path)
    if not self._dataset_path.exists():
      raise ValueError(f"Dataset path does not exist: {dataset_path}")

    # State
    self._cameras: List[str] = self.SUPPORTED_CAMERAS.copy()
    self._camera_fps: float = self.DEFAULT_FPS
    self._scene_config: Optional[Dict[str, Any]] = None

  def set_scene(self, scene: Optional[str] = None) -> 'MetricTestDataset':
    """Set scene (not supported - only Retail_Demo available).

    Args:
      scene: Scene identifier (must be None or "Retail_Demo")

    Returns:
      Self for method chaining

    Raises:
      NotImplementedError: Scene selection not supported
    """
    if scene is not None and scene != self.SCENE_NAME:
      raise NotImplementedError(
        f"Only '{self.SCENE_NAME}' scene is supported. "
        f"Requested: '{scene}'"
      )
    return self

  def set_cameras(self, cameras: Optional[List[str]] = None) -> 'MetricTestDataset':
    """Set cameras to use.

    Args:
      cameras: List of camera IDs (subset of ["x1", "x2"])

    Returns:
      Self for method chaining

    Raises:
      ValueError: If unsupported camera requested
    """
    if cameras is None:
      self._cameras = self.SUPPORTED_CAMERAS.copy()
    else:
      for cam in cameras:
        if cam not in self.SUPPORTED_CAMERAS:
          raise ValueError(
            f"Unsupported camera: {cam}. "
            f"Supported: {self.SUPPORTED_CAMERAS}"
          )
      self._cameras = cameras
    return self

  def set_time_range(
    self,
    start: Optional[str] = None,
    end: Optional[str] = None
  ) -> 'MetricTestDataset':
    """Set time range (not supported - only full sequence available).

    Args:
      start: Start timestamp
      end: End timestamp

    Returns:
      Self for method chaining

    Raises:
      NotImplementedError: Time range filtering not supported
    """
    if start is not None or end is not None:
      raise NotImplementedError(
        "Time range filtering not supported. "
        "Only full sequence available."
      )
    return self

  def set_camera_fps(self, camera_fps: float) -> 'MetricTestDataset':
    """Set camera FPS for input selection.

    Args:
      camera_fps: Camera FPS (must be 1, 10, or 30)

    Returns:
      Self for method chaining

    Raises:
      ValueError: If unsupported FPS requested
    """
    if camera_fps not in self.SUPPORTED_FPS:
      raise ValueError(
        f"Unsupported FPS: {camera_fps}. "
        f"Supported: {self.SUPPORTED_FPS}"
      )
    self._camera_fps = camera_fps
    return self

  def set_custom_config(self, config: Dict[str, Any]) -> 'MetricTestDataset':
    """Set custom configuration (not supported).

    Args:
      config: Custom configuration dictionary

    Returns:
      Self for method chaining

    Raises:
      NotImplementedError: Custom configuration not supported
    """
    raise NotImplementedError("Custom configuration not supported")

  def get_scene_config(self) -> Dict[str, Any]:
    """Get scene configuration in canonical format.

    Returns:
      Scene configuration in canonical Scene Configuration Format
      (see tools/tracker/evaluation/README.md#canonical-data-formats).
    """
    if self._scene_config is None:
      self._scene_config = self._load_scene_config()
    return self._scene_config

  def get_scene_config_raw(self) -> Dict[str, Any]:
    """Get raw scene configuration in dataset-specific format.

    Returns:
      Dictionary with raw config.json from dataset.

    Raises:
      RuntimeError: If configuration cannot be loaded.
    """
    config_file = self._dataset_path / "config.json"
    if not config_file.exists():
      raise RuntimeError(f"Config file not found: {config_file}")
    return read_json(str(config_file))

  def get_inputs(self, camera: Optional[str] = None) -> Iterator[Dict[str, Any]]:
    """Get camera detection inputs in canonical format.

    Args:
      camera: Specific camera ID, or None for all configured cameras

    Yields:
      Camera detection data in canonical Input Detection Format
      (see tools/tracker/evaluation/README.md#canonical-data-formats).

    Raises:
      ValueError: If camera not configured
    """
    cameras_to_process = [camera] if camera else self._cameras

    for cam_id in cameras_to_process:
      if cam_id not in self._cameras:
        raise ValueError(f"Camera {cam_id} not in configured cameras")

      # Select appropriate file based on FPS
      fps_suffix = f"_{int(self._camera_fps)}fps" if self._camera_fps != 30 else ""
      input_file = self._dataset_path / f"Cam_{cam_id}_0{fps_suffix}.json"

      if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

      # Read input file (newline-delimited JSON)
      with open(input_file, 'r') as f:
        for line in f:
          if line.strip():
            data = rapidjson.loads(line.strip())
            yield data

  def get_ground_truth(self) -> str:
    """Get ground truth in evaluator input format.

    Returns:
      Path to CSV file with ground truth data in Ground Truth Format (MOTChallenge 3D CSV)
      (see tools/tracker/evaluation/README.md#canonical-data-formats).
    """
    gt_file = self._dataset_path / "gtLoc.json"
    if not gt_file.exists():
      raise FileNotFoundError(f"Ground truth file not found: {gt_file}")

    # Read ground truth (newline-delimited JSON)
    gt_data = []
    frame_num = 1
    with open(gt_file, 'r') as f:
      for line in f:
        if line.strip():
          entry = rapidjson.loads(line.strip())

          # Extract all objects from all categories
          if "objects" in entry:
            for category, objects in entry["objects"].items():
              for obj in objects:
                gt_data.append({
                  "frame": frame_num,
                  "object_id": obj["id"],
                  "x": obj["translation"][0],
                  "y": obj["translation"][1],
                  "z": obj["translation"][2],
                  "category": obj.get("category", category)
                })
          frame_num += 1

    # Convert to Ground Truth Format (MOTChallenge 3D CSV)
    # See tools/tracker/evaluation/README.md#canonical-data-formats for format specification
    mapping = {
      "frame": {"pointer": "/frame"},
      "id": {"pointer": "/object_id"},
      "x": {"pointer": "/x"},
      "y": {"pointer": "/y"},
      "z": {"pointer": "/z"},
      "conf": {"value": 1.0},
      "class": {"value": 1},
      "visibility": {"value": 1}
    }

    # Create temporary file for CSV output
    temp_file = tempfile.NamedTemporaryFile(
      mode='w',
      suffix='.csv',
      delete=False,
      prefix='gt_motchallenge_'
    )
    temp_file.close()

    convert_json_to_csv(
      gt_data,
      mapping,
      temp_file.name,
      include_header=False
    )

    return temp_file.name

  def reset(self) -> 'MetricTestDataset':
    """Reset dataset to initial state.

    Returns:
      Self for method chaining
    """
    self._cameras = self.SUPPORTED_CAMERAS.copy()
    self._camera_fps = self.DEFAULT_FPS
    self._scene_config = None
    return self

  def _load_scene_config(self) -> Dict[str, Any]:
    """Load and convert scene configuration to canonical format.

    Returns:
      Scene configuration dict matching scene.schema.json
    """
    config_file = self._dataset_path / "config.json"
    if not config_file.exists():
      raise FileNotFoundError(f"Config file not found: {config_file}")

    raw_config = read_json(str(config_file))

    # Convert to canonical format
    cameras = []
    for cam_id in self._cameras:
      sensor_key = f"Cam_{cam_id}_0"
      if sensor_key not in raw_config.get("sensors", {}):
        raise ValueError(f"Camera {cam_id} not found in config")

      sensor = raw_config["sensors"][sensor_key]
      intrinsics_list = sensor.get("intrinsics", [])

      camera = {
        "uid": sensor_key,
        "name": sensor_key,
        "intrinsics": {
          "fx": intrinsics_list[0] if len(intrinsics_list) > 0 else 0.0,
          "fy": intrinsics_list[1] if len(intrinsics_list) > 1 else 0.0,
          "cx": intrinsics_list[2] if len(intrinsics_list) > 2 else 0.0,
          "cy": intrinsics_list[3] if len(intrinsics_list) > 3 else 0.0
        },
        "distortion": {"k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0}
      }
      cameras.append(camera)

    return {
      "uid": "metric_test_scene",
      "name": raw_config.get("name", self.SCENE_NAME),
      "cameras": cameras
    }
