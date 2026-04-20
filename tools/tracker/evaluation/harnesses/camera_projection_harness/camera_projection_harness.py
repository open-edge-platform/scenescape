# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""CameraProjectionHarness: projects per-camera bounding-box detections to world
coordinates and returns results in canonical Tracker Output Format.

Harness bypasses the full tracking pipeline
and only applies camera-pose projection.  This lets us measure the raw position
error introduced by each camera's calibration before any tracker fusion.

Each detected object is projected independently per camera so that evaluators
can measure:
  - Average distance error per object per camera (calibration accuracy)
  - Visibility per object per camera (how many frames each camera sees each object)

The projection relies on scene_common (which requires OpenCV and open3d), so it
is executed inside a Docker container that has those dependencies pre-installed
(default: scenescape-controller:latest).

Object IDs in the output are encoded as ``{camera_id}:{object_id}`` so
CameraAccuracyEvaluator can split them back into camera and object parts.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from python_on_whales import docker

# Add parent directories to path so the base class can be imported when this
# module is used standalone (the pipeline engine already patches sys.path, but
# unit tests may not).
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from base.tracker_harness import TrackerHarness
from utils.format_converters import write_jsonl

DEFAULT_CONTAINER_IMAGE = "scenescape-controller:latest"


class CameraProjectionHarness(TrackerHarness):
  """Tracker harness that projects camera detections to world coordinates.

  This harness executes ``run_projection.py`` inside a *scenescape-controller*
  Docker container.  The container already contains ``scene_common`` with full
  dependencies (OpenCV, open3d), which are not required on the host.

  **Workflow**:
  1. Write input detections and scene config to a shared temp directory.
  2. Mount the temp directory into the container and execute
     ``run_projection.py``, which projects every bounding-box bottom-centre to
     world coordinates using ``CameraPose.cameraPointToWorldPoint()``.
  3. Read ``output.json`` produced by the container and return it as an
     iterator of canonical Tracker Output Format dicts.

  **Object ID encoding**:
  Each output object ID is ``"{camera_id}:{object_id}"`` (e.g.
  ``"Cam_x1_0:0"``).  ``CameraAccuracyEvaluator`` parses these to group
  results per camera and per object.

  **Custom config keys** (all optional):
    - ``container_image`` (str): Docker image to use.
    - ``object_classes`` (list): Per-category projection settings.  Each entry
      is a dict with ``name``, ``shift_type`` (1 or 2), ``x_size``,
      ``y_size`` (object footprint in metres).  Controls TYPE_2 angle
      compensation and camloc size offset in ``run_projection.py``.
  """

  def __init__(self, container_image: str = DEFAULT_CONTAINER_IMAGE):
    """Initialise the harness.

    Args:
      container_image: Docker image that has scene_common installed.
                       Defaults to ``scenescape-controller:latest``.
    """
    self._container_image: str = container_image
    self._scene_config: Optional[Dict[str, Any]] = None
    self._object_classes: list = []
    self._temp_dir: Optional[Path] = None
    self._output_folder: Optional[Path] = None

  # ------------------------------------------------------------------
  # TrackerHarness interface
  # ------------------------------------------------------------------

  def set_scene_config(self, config: Dict[str, Any]) -> 'CameraProjectionHarness':
    """Set scene and camera configuration.

    Args:
      config: Raw scene config dict (e.g. from ``MetricTestDataset.get_scene_config()``).
              Must contain a ``"sensors"`` key with per-camera calibration data.

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If the config dict is invalid.
    """
    if not isinstance(config, dict):
      raise ValueError("Scene config must be a dictionary")
    if 'sensors' not in config:
      raise ValueError("Scene config must contain a 'sensors' key")
    if 'name' not in config:
      raise ValueError("Scene config must contain a 'name' key")
    self._scene_config = config
    return self

  def set_custom_config(self, config: Dict[str, Any]) -> 'CameraProjectionHarness':
    """Set optional harness-specific configuration.

    Accepted keys:
      - ``container_image``: Override the Docker image to use.

    Args:
      config: Custom configuration dictionary.

    Returns:
      Self for method chaining.
    """
    if not isinstance(config, dict):
      raise ValueError("Custom config must be a dictionary")
    if 'container_image' in config:
      self._container_image = config['container_image']
    if 'object_classes' in config:
      self._object_classes = list(config['object_classes'])
    return self

  def set_output_folder(self, path: Path) -> 'CameraProjectionHarness':
    """Set folder for harness artefacts (inputs.json, outputs.json).

    Args:
      path: Destination directory; created if it does not exist.

    Returns:
      Self for method chaining.
    """
    if not isinstance(path, Path):
      path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    self._output_folder = path
    return self

  def process_inputs(
    self,
    inputs: Iterator[Dict[str, Any]],
  ) -> Iterator[Dict[str, Any]]:
    """Project all camera detections to world coordinates.

    Runs ``run_projection.py`` inside the configured Docker container and
    returns the projected results in canonical Tracker Output Format.

    Each output frame corresponds to one camera-detection frame and contains
    only objects visible in that specific camera.  Object IDs are encoded as
    ``"{camera_id}:{object_id}"``.

    Args:
      inputs: Iterator of canonical Input Detection Format dicts.

    Returns:
      Iterator of canonical Tracker Output Format dicts.

    Raises:
      RuntimeError: If configuration is missing or container execution fails.
    """
    if self._scene_config is None:
      raise RuntimeError("Scene config not set. Call set_scene_config() first.")

    self._temp_dir = Path(tempfile.mkdtemp(prefix="cam_proj_harness_"))
    print(f"Created temporary directory: {self._temp_dir}")

    try:
      # Write inputs
      input_file = self._temp_dir / "inputs.json"
      write_jsonl(inputs, str(input_file))
      self._persist_artifact(input_file, "inputs.json")

      # Write scene config
      config_file = self._temp_dir / "config.json"
      with open(config_file, 'w') as f:
        json.dump(self._scene_config, f, indent=2)

      # Write projection params (object classes)
      params = {"object_classes": self._object_classes}
      params_file = self._temp_dir / "params.json"
      with open(params_file, 'w') as f:
        json.dump(params, f, indent=2)

      # Copy projection script
      self._copy_projection_script()

      # Run projection in container
      self._run_container()

      # Read output
      output_file = self._temp_dir / "output.json"
      if not output_file.exists():
        raise RuntimeError(
          "Container finished but no output.json was produced"
        )

      self._persist_artifact(output_file, "outputs.json")
      with open(output_file, 'r') as f:
        outputs = json.load(f)

      return iter(outputs)

    except Exception as exc:
      raise RuntimeError(f"Projection processing failed: {exc}") from exc

    finally:
      if self._temp_dir and self._temp_dir.exists():
        shutil.rmtree(self._temp_dir)
        self._temp_dir = None

  def reset(self) -> 'CameraProjectionHarness':
    """Reset harness state.

    Returns:
      Self for method chaining.
    """
    self._scene_config = None
    self._object_classes = []
    if self._temp_dir and self._temp_dir.exists():
      shutil.rmtree(self._temp_dir)
    self._temp_dir = None
    self._output_folder = None
    return self

  # ------------------------------------------------------------------
  # Private helpers
  # ------------------------------------------------------------------

  def _copy_projection_script(self) -> None:
    """Copy run_projection.py to the shared temp directory."""
    script_source = Path(__file__).parent / "run_projection.py"
    script_dest = self._temp_dir / "run_projection.py"
    shutil.copy(script_source, script_dest)
    script_dest.chmod(0o755)

  def _run_container(self) -> None:
    """Execute run_projection.py inside the Docker container."""
    try:
      output = docker.run(
        self._container_image,
        ["/workspace/run_projection.py"],
        volumes=[(str(self._temp_dir.absolute()), "/workspace")],
        workdir="/workspace",
        entrypoint="python3",
        user=f"{os.getuid()}:{os.getgid()}",
        remove=True,
        stream=True,
      )
      for stream_type, stream_content in output:
        print(f"[projection {stream_type}] {stream_content.decode('utf-8')}", end='')
    except Exception as exc:
      raise RuntimeError(f"Container execution failed: {exc}") from exc

  def _persist_artifact(self, source: Path, filename: str) -> None:
    """Copy *source* to the configured output folder when available."""
    if not self._output_folder or not source.exists():
      return
    shutil.copy(source, self._output_folder / filename)
