# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MetricTestDataset implementation for tests/system/metric/dataset dataset."""

from typing import List, Dict, Any, Optional, Iterator
from pathlib import Path
import sys
import orjson
from contextlib import ExitStack

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from base.tracking_dataset import TrackingDataset
from utils.format_converters import read_json, convert_json_to_csv, stream_jsonl


class MetricTestDataset(TrackingDataset):
  """Dataset adapter for tests/system/metric/dataset.

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
      dataset_path: Path to tests/system/metric/dataset directory
    """
    self._dataset_path = Path(dataset_path)
    if not self._dataset_path.exists():
      raise ValueError(f"Dataset path does not exist: {dataset_path}")

    # State
    self._cameras: List[str] = self.SUPPORTED_CAMERAS.copy()
    self._camera_fps: float = self.DEFAULT_FPS
    self._scene_config: Optional[Dict[str, Any]] = None
    self._time_start: Optional[str] = None
    self._time_end: Optional[str] = None
    self._output_folder: Optional[Path] = None

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
    """Set inclusive time range for dataset filtering.

    Args:
      start: Start timestamp (inclusive). If None, uses earliest available timestamp.
      end: End timestamp (inclusive). If None, uses latest available timestamp.

    Returns:
      Self for method chaining

    Raises:
      ValueError: If start and end are provided but start > end.
    """
    if start is not None and end is not None and start > end:
      raise ValueError(
        "Invalid time range: start timestamp is later than end timestamp"
      )

    self._time_start = start
    self._time_end = end
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

  def set_output_folder(self, path: Path) -> 'MetricTestDataset':
    """Set dataset output folder for optional exports.

    Args:
      path: Destination directory for dataset artifacts.

    Returns:
      Self for method chaining
    """
    if not isinstance(path, Path):
      path = Path(path)

    path.mkdir(parents=True, exist_ok=True)
    self._output_folder = path
    return self

  def get_scene_config(self) -> Dict[str, Any]:
    """Get scene configuration in dataset-specific format.

    Returns:
      Dictionary with raw config.json from dataset (dataset-specific format).

    Raises:
      RuntimeError: If configuration cannot be loaded.
    """
    config_file = self._dataset_path / "config.json"
    if not config_file.exists():
      raise RuntimeError(f"Config file not found: {config_file}")
    return read_json(str(config_file))

  def get_inputs(self, camera: Optional[str] = None) -> Iterator[Dict[str, Any]]:
    """Get camera detection inputs in canonical format, sorted by timestamp.

    Args:
      camera: Specific camera ID, or None for all configured cameras

    Yields:
      Camera detection data in canonical Input Detection Format
      (see tools/tracker/evaluation/README.md#canonical-data-formats).
      Frames are yielded in chronological order (sorted by timestamp) across all cameras.

    Raises:
      ValueError: If camera not configured
    """
    cameras_to_process = [camera] if camera else self._cameras

    # When processing single camera, no sorting needed - yield directly
    if len(cameras_to_process) == 1:
      cam_id = cameras_to_process[0]
      input_file = self._get_input_filename(cam_id)

      for data in stream_jsonl(str(input_file)):
        timestamp = data.get('timestamp')
        if timestamp is None:
          continue
        if self._time_end is not None and timestamp > self._time_end:
          break
        if self._time_start is not None and timestamp < self._time_start:
          continue
        yield data
      return

    # Multi-camera: sort frames by timestamp
    # Open all camera files and initialize buffers
    with ExitStack() as stack:
      file_handles = []
      frame_buffer = []

      for cam_id in cameras_to_process:
        input_file = self._get_input_filename(cam_id)

        f = stack.enter_context(open(input_file, 'rb', buffering=1024 * 1024))
        file_handles.append(f)

        # Read first frame within range
        frame_buffer.append(self._read_next_frame_within_range(f))

      # Yield frames in timestamp order
      while any(frame is not None for frame in frame_buffer):
        # Find frame with minimum timestamp (alphabetical comparison works for ISO 8601)
        timestamps = [frame['timestamp'] if frame else 'Z' * 50 for frame in frame_buffer]
        min_idx = min(range(len(timestamps)), key=lambda i: timestamps[i])

        # Yield the frame with earliest timestamp
        yield frame_buffer[min_idx]

        # Read next frame from that camera respecting range
        frame_buffer[min_idx] = self._read_next_frame_within_range(
          file_handles[min_idx]
        )

  def get_ground_truth(self) -> str:
    """Get ground truth in evaluator input format.

    Returns:
      Path to CSV file with ground truth data in Ground Truth Format (MOTChallenge 3D CSV)
      (see tools/tracker/evaluation/README.md#canonical-data-formats).
    """
    gt_file = self._dataset_path / "gtLoc.json"
    if not gt_file.exists():
      raise FileNotFoundError(f"Ground truth file not found: {gt_file}")

    if self._output_folder is None:
      raise RuntimeError(
        "Dataset output folder not configured. Call set_output_folder() before get_ground_truth()."
      )

    sampling_stride = self._get_sampling_stride()

    gt_data = []
    filtered_frame_num = 0

    for base_frame_idx, entry in enumerate(stream_jsonl(str(gt_file))):
      timestamp = entry.get("timestamp")
      if timestamp is None:
        continue

      if self._time_end is not None and timestamp > self._time_end:
        break

      if self._time_start is not None and timestamp < self._time_start:
        continue

      if base_frame_idx % sampling_stride != 0:
        continue

      filtered_frame_num += 1

      objects = entry.get("objects", {})
      gt_data.extend([
        {
          "frame": filtered_frame_num,
          "object_id": obj["id"],
          "x": obj["translation"][0],
          "y": obj["translation"][1],
          "z": obj["translation"][2],
          "category": obj.get("category", category)
        }
        for category, category_objects in objects.items()
        for obj in category_objects
      ])
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

    output_file = self._output_folder / "ground_truth_motchallenge.csv"

    convert_json_to_csv(
      gt_data,
      mapping,
      str(output_file),
      include_header=False
    )

    return str(output_file)

  def reset(self) -> 'MetricTestDataset':
    """Reset dataset to initial state.

    Returns:
      Self for method chaining
    """
    self._cameras = self.SUPPORTED_CAMERAS.copy()
    self._camera_fps = self.DEFAULT_FPS
    self._scene_config = None
    self._time_start = None
    self._time_end = None
    self._output_folder = None
    return self

  def _get_sampling_stride(self) -> int:
    """Return how many base (30 FPS) frames correspond to one configured frame."""
    if self._camera_fps <= 0:
      raise RuntimeError("Camera FPS must be positive to sample ground truth")

    ratio = self.DEFAULT_FPS / self._camera_fps
    stride = int(round(ratio))

    if stride <= 0:
      raise RuntimeError("Invalid sampling stride computed for ground truth")

    if abs(stride - ratio) > 1e-6:
      raise RuntimeError(
        f"Ground truth base FPS ({self.DEFAULT_FPS}) is not divisible by configured FPS ({self._camera_fps})"
      )

    return stride

  def _read_next_frame_within_range(self, file_handle) -> Optional[Dict[str, Any]]:
    """Read next frame from file handle, applying time range constraints."""
    while True:
      line = file_handle.readline()
      if not line:
        return None

      chunk = line.strip()
      if not chunk:
        continue

      data = orjson.loads(chunk)
      timestamp = data.get('timestamp')

      if timestamp is None:
        continue

      if self._time_end is not None and timestamp > self._time_end:
        return None

      if self._time_start is not None and timestamp < self._time_start:
        continue

      return data

  def _get_input_filename(self, cam_id: str) -> Path:
    """Build absolute path to the camera JSONL input file."""
    if cam_id not in self._cameras:
      raise ValueError(f"Camera {cam_id} not in configured cameras")

    fps_suffix = f"_{int(self._camera_fps)}fps" if self._camera_fps != 30 else ""
    input_file = self._dataset_path / f"Cam_{cam_id}_0{fps_suffix}.json"

    if not input_file.exists():
      raise FileNotFoundError(f"Input file not found: {input_file}")

    return input_file
