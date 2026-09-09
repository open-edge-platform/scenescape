# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""WildtrackDataset adapter for the tracker evaluation pipeline.

Reads the canonical artifacts produced by ``datasets.wildtrack.preprocess``
(scene_config.json, per-camera detection JSONL, gtLoc.json) and exposes them
through the :class:`TrackingDataset` interface.

The scene configuration is emitted with explicit per-camera intrinsics +
extrinsics (canonical camera->world pose), matching what the production
Manager serializes for the controller / tracker.  Cameras may be selected by
integer id (0-6) or by canonical name (``cam0``..``cam6``).
"""

from typing import List, Dict, Any, Optional, Iterator, Union
from pathlib import Path
from contextlib import ExitStack
import sys

import orjson

sys.path.insert(0, str(Path(__file__).parent.parent))

from base.tracking_dataset import TrackingDataset
from utils.format_converters import read_json, write_jsonl, stream_jsonl


class WildtrackDataset(TrackingDataset):
  """Dataset adapter for the preprocessed Wildtrack dataset.

  Contains:
  - Scene: Wildtrack (single built-in scene)
  - Cameras: cam0..cam6 (7 static cameras)
  - FPS: 2 (native annotation cadence; no interpolation)
  - Ground truth: gtLoc.json with object locations (decoded grid positions)
  - Scene config: scene_config.json with explicit intrinsics + extrinsics
  """

  SCENE_NAME = "Wildtrack"
  NUM_CAMERAS = 7
  SUPPORTED_CAMERAS = [f"cam{i}" for i in range(NUM_CAMERAS)]
  SUPPORTED_FPS = [2]
  DEFAULT_FPS = 2

  def __init__(self, dataset_path: str):
    """Initialize WildtrackDataset.

    Args:
      dataset_path: Path to the preprocessed Wildtrack artifacts directory.
    """
    self._dataset_path = Path(dataset_path)
    if not self._dataset_path.exists():
      raise ValueError(f"Dataset path does not exist: {dataset_path}")

    self._cameras: List[str] = self.SUPPORTED_CAMERAS.copy()
    self._camera_fps: float = self.DEFAULT_FPS
    self._scene_config: Optional[Dict[str, Any]] = None
    self._time_start: Optional[str] = None
    self._time_end: Optional[str] = None
    self._object_categories: Optional[List[str]] = None
    self._output_folder: Optional[Path] = None

  @classmethod
  def _normalize_camera(cls, camera: Union[str, int]) -> str:
    """Normalize a camera selector (int 0-6 or ``camN``) to a canonical id."""
    if isinstance(camera, bool):
      raise ValueError(f"Invalid camera selector: {camera}")
    if isinstance(camera, int):
      cam_id = f"cam{camera}"
    else:
      cam_id = str(camera)
    if cam_id not in cls.SUPPORTED_CAMERAS:
      raise ValueError(
        f"Unsupported camera: {camera}. Supported ids: {cls.SUPPORTED_CAMERAS} "
        f"(or integers 0-{cls.NUM_CAMERAS - 1})"
      )
    return cam_id

  def set_scene(self, scene: Optional[str] = None) -> 'WildtrackDataset':
    """Set scene (only the built-in Wildtrack scene is supported)."""
    if scene is not None and scene != self.SCENE_NAME:
      raise NotImplementedError(
        f"Only '{self.SCENE_NAME}' scene is supported. Requested: '{scene}'"
      )
    return self

  def set_cameras(
    self,
    cameras: Optional[List[Union[str, int]]] = None
  ) -> 'WildtrackDataset':
    """Set cameras to use.

    Args:
      cameras: List of camera selectors (integers 0-6 or ``cam0``..``cam6``).
               If None, uses all 7 cameras.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If an unsupported camera is requested.
    """
    if cameras is None:
      self._cameras = self.SUPPORTED_CAMERAS.copy()
    else:
      self._cameras = [self._normalize_camera(cam) for cam in cameras]
    return self

  def set_time_range(
    self,
    start: Optional[str] = None,
    end: Optional[str] = None
  ) -> 'WildtrackDataset':
    """Set inclusive time range for dataset filtering."""
    if start is not None and end is not None and start > end:
      raise ValueError(
        "Invalid time range: start timestamp is later than end timestamp"
      )
    self._time_start = start
    self._time_end = end
    return self

  def set_camera_fps(self, camera_fps: float) -> 'WildtrackDataset':
    """Set camera FPS (only the native 2 FPS is supported)."""
    if camera_fps not in self.SUPPORTED_FPS:
      raise ValueError(
        f"Unsupported FPS: {camera_fps}. Supported: {self.SUPPORTED_FPS}"
      )
    self._camera_fps = camera_fps
    return self

  def set_object_categories(
    self,
    categories: Optional[List[str]] = None
  ) -> 'WildtrackDataset':
    """Set the object categories to include in inputs and ground truth."""
    if categories is not None and len(categories) == 0:
      raise ValueError("Categories list must not be empty")
    self._object_categories = categories
    return self

  def set_custom_config(self, config: Dict[str, Any]) -> 'WildtrackDataset':
    """Set custom configuration (not supported)."""
    raise NotImplementedError("Custom configuration not supported")

  def set_output_folder(self, path: Path) -> 'WildtrackDataset':
    """Set dataset output folder for optional exports."""
    if not isinstance(path, Path):
      path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    self._output_folder = path
    return self

  def get_scene_config(self) -> Dict[str, Any]:
    """Get scene configuration in dataset-specific format.

    Returns:
      Dictionary with scene_config.json (explicit intrinsics + extrinsics).

    Raises:
      RuntimeError: If configuration cannot be loaded.
    """
    config_file = self._dataset_path / "scene_config.json"
    if not config_file.exists():
      raise RuntimeError(f"Config file not found: {config_file}")
    return read_json(str(config_file))

  def get_inputs(self, camera: Optional[str] = None) -> Iterator[Dict[str, Any]]:
    """Get camera detection inputs in canonical format, sorted by timestamp.

    Args:
      camera: Specific camera selector (int or ``camN``), or None for all
              configured cameras.

    Yields:
      Camera detection data in canonical Input Detection Format, in
      chronological order (sorted by timestamp) across all cameras.
    """
    if camera is not None:
      cameras_to_process = [self._normalize_camera(camera)]
    else:
      cameras_to_process = self._cameras

    if len(cameras_to_process) == 1:
      input_file = self._get_input_filename(cameras_to_process[0])
      for data in stream_jsonl(str(input_file)):
        timestamp = data.get('timestamp')
        if timestamp is None:
          continue
        if self._time_end is not None and timestamp > self._time_end:
          break
        if self._time_start is not None and timestamp < self._time_start:
          continue
        yield self._filter_categories(data)
      return

    with ExitStack() as stack:
      file_handles = []
      frame_buffer = []
      for cam_id in cameras_to_process:
        input_file = self._get_input_filename(cam_id)
        f = stack.enter_context(open(input_file, 'rb', buffering=1024 * 1024))
        file_handles.append(f)
        frame_buffer.append(self._read_next_frame_within_range(f))

      while any(frame is not None for frame in frame_buffer):
        timestamps = [frame['timestamp'] if frame else 'Z' * 50 for frame in frame_buffer]
        min_idx = min(range(len(timestamps)), key=lambda i: timestamps[i])
        yield self._filter_categories(frame_buffer[min_idx])
        frame_buffer[min_idx] = self._read_next_frame_within_range(file_handles[min_idx])

  def get_ground_truth(self) -> str:
    """Get ground truth in evaluator input format.

    Returns:
      Path to the JSONL file with ground truth in the canonical Tracker Output
      Format (absolute ISO timestamps, flattened ``objects`` array).
    """
    gt_file = self._dataset_path / "gtLoc.json"
    if not gt_file.exists():
      raise FileNotFoundError(f"Ground truth file not found: {gt_file}")

    if self._output_folder is None:
      raise RuntimeError(
        "Dataset output folder not configured. "
        "Call set_output_folder() before get_ground_truth()."
      )

    gt_frames = []

    for entry in stream_jsonl(str(gt_file)):
      timestamp = entry.get("timestamp")
      if timestamp is None:
        continue
      if self._time_end is not None and timestamp > self._time_end:
        break
      if self._time_start is not None and timestamp < self._time_start:
        continue

      objects = entry.get("objects", {})
      gt_frames.append({
        "timestamp": timestamp,
        "objects": [
          {
            "id": obj["id"],
            "category": obj.get("category", category),
            "translation": obj["translation"],
          }
          for category, category_objects in objects.items()
          if self._object_categories is None or category in self._object_categories
          for obj in category_objects
        ]
      })

    output_file = self._output_folder / "ground_truth.jsonl"
    write_jsonl(gt_frames, str(output_file))
    return str(output_file)

  def reset(self) -> 'WildtrackDataset':
    """Reset dataset to initial state."""
    self._cameras = self.SUPPORTED_CAMERAS.copy()
    self._camera_fps = self.DEFAULT_FPS
    self._scene_config = None
    self._time_start = None
    self._time_end = None
    self._object_categories = None
    self._output_folder = None
    return self

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
    input_file = self._dataset_path / f"{cam_id}.json"
    if not input_file.exists():
      raise FileNotFoundError(f"Input file not found: {input_file}")
    return input_file

  def _filter_categories(self, frame: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *frame* with only the configured object categories."""
    if self._object_categories is None:
      return frame
    filtered = {**frame}
    filtered["objects"] = {
      cat: objs for cat, objs in frame.get("objects", {}).items()
      if cat in self._object_categories
    }
    return filtered
