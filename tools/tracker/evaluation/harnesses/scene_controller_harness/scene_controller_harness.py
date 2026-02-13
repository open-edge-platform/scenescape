# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""SceneControllerHarness implementation for running tracker in scene controller container."""

import json
import tempfile
import shutil
from pathlib import Path
from typing import Iterator, Dict, Any, Optional
from python_on_whales import docker
import sys

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from base.tracker_harness import TrackerHarness
from utils.format_converters import write_jsonl


class SceneControllerHarness(TrackerHarness):
  """Tracker harness for SceneScape Scene Controller.

  This harness executes the tracker by running it inside the scene controller
  Docker container. It operates in **synchronous batch mode** - all inputs are
  provided in a single process_inputs() call and outputs are returned.

  Each instance is tied to a specific scene controller container image version.

  Configuration requires:
  - set_scene_config(): Scene configuration in dataset-specific format
  - set_custom_config(): tracker_config_path pointing to tracker configuration JSON

  Prerequisites:
  - Docker installed and running on the host machine
  - Scene controller container image available locally
  """

  def __init__(self, container_image: str):
    """Initialize SceneControllerHarness.

    Args:
      container_image: Scene controller Docker image (e.g., 'scenescape-controller:2026.0.0-dev')
    """
    self._container_image = container_image
    self._scene_config: Optional[Dict[str, Any]] = None
    self._tracker_config_path: Optional[str] = None
    self._temp_dir: Optional[Path] = None
    self._output_folder: Optional[Path] = None

  def set_scene_config(self, config: Dict[str, Any]) -> 'SceneControllerHarness':
    """Set scene and camera configuration in dataset-specific format.

    Args:
      config: Scene configuration in dataset-specific format (e.g., from dataset.get_scene_config()).

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If configuration is invalid.
    """
    if not isinstance(config, dict):
      raise ValueError("Scene config must be a dictionary")
    if 'name' not in config:
      raise ValueError("Scene config must contain 'name' field")

    self._scene_config = config
    return self

  def set_custom_config(self, config: Dict[str, Any]) -> 'SceneControllerHarness':
    """Set tracker-specific configuration.

    Args:
      config: Custom configuration dictionary with required key:
        - tracker_config_path (str): Path to tracker configuration JSON file

    Returns:
      Self for method chaining.

    Raises:
      ValueError: If configuration is invalid or missing required keys.
    """
    if not isinstance(config, dict):
      raise ValueError("Custom config must be a dictionary")

    if 'tracker_config_path' not in config:
      raise ValueError("Custom config must contain 'tracker_config_path'")

    self._tracker_config_path = config['tracker_config_path']

    # Validate tracker config file exists
    if not Path(self._tracker_config_path).exists():
      raise ValueError(f"Tracker config file not found: {self._tracker_config_path}")

    return self

  def set_output_folder(self, path: Path) -> 'SceneControllerHarness':
    """Set harness output folder for optional artifacts.

    Args:
      path: Destination directory for harness outputs.

    Returns:
      Self for method chaining.
    """
    if not isinstance(path, Path):
      path = Path(path)

    path.mkdir(parents=True, exist_ok=True)
    self._output_folder = path
    return self

  def process_inputs(self, inputs: Iterator[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    """Process input detections through the tracker synchronously.

    All inputs are consumed and processed in a single container execution.
    The tracker processes all frames sequentially and returns outputs.

    Args:
      inputs: Iterator of detection dictionaries in canonical Input Detection Format
        (see tools/tracker/evaluation/README.md#canonical-data-formats).

    Returns:
      Iterator of tracker outputs in canonical Tracker Output Format.

    Raises:
      RuntimeError: If processing fails or configuration is incomplete.
    """
    # Validate configuration
    if self._scene_config is None:
      raise RuntimeError("Scene config not set. Call set_scene_config() first.")
    if self._tracker_config_path is None:
      raise RuntimeError("Tracker config not set. Call set_custom_config() first.")

    # Create temporary directory for data exchange with container
    self._temp_dir = Path(tempfile.mkdtemp(prefix="scenescape_harness_"))
    print(f"Created temporary directory: {self._temp_dir}")

    try:
      # Write all inputs to single file for data exchange with container
      # (newline-delimited JSON format)
      self._write_input_file(inputs)
      input_file = self._temp_dir / "inputs.json"
      self._persist_artifact(input_file, "inputs.json")

      # Write scene configuration
      scene_config_file = self._temp_dir / "config.json"
      with open(scene_config_file, 'w') as f:
        json.dump(self._scene_config, f, indent=2)

      # Copy tracker configuration
      tracker_config_file = self._temp_dir / "tracker-config.json"
      shutil.copy(self._tracker_config_path, tracker_config_file)

      # Copy tracking script to temporary directory
      self._copy_tracking_script()

      # Run container
      output_file = self._temp_dir / "output.json"
      self._run_container()

      # Read and return outputs
      if output_file.exists():
        self._persist_artifact(output_file, "outputs.json")
        with open(output_file, 'r') as f:
          outputs = json.load(f)
        return iter(outputs)
      else:
        raise RuntimeError("Tracker execution completed but no output file generated")

    except Exception as e:
      raise RuntimeError(f"Tracker processing failed: {str(e)}") from e

    finally:
      # Clean up temporary directory
      if self._temp_dir and self._temp_dir.exists():
        shutil.rmtree(self._temp_dir)
        self._temp_dir = None

  def reset(self) -> 'SceneControllerHarness':
    """Reset harness state to initial configuration.

    Returns:
      Self for method chaining.
    """
    self._scene_config = None
    self._tracker_config_path = None

    # Clean up any remaining temp directory
    if self._temp_dir and self._temp_dir.exists():
      shutil.rmtree(self._temp_dir)
      self._temp_dir = None

    self._output_folder = None

    return self

  def _write_input_file(self, inputs: Iterator[Dict[str, Any]]) -> None:
    """Write all input frames to a single file.

    Inputs are written as newline-delimited JSON to enable data exchange
    with the container. The file is shared via volume mount.

    Args:
      inputs: Iterator of input detection frames
    """
    output_file = self._temp_dir / "inputs.json"
    write_jsonl(inputs, str(output_file))

  def _copy_tracking_script(self) -> None:
    """Copy tracking script to temporary directory."""
    script_source = Path(__file__).parent / "run_tracker.py"
    script_dest = self._temp_dir / "run_tracker.py"
    shutil.copy(script_source, script_dest)
    script_dest.chmod(0o755)

  def _run_container(self) -> None:
    """Run the tracker inside the scene controller container."""
    try:
      output = docker.run(
        self._container_image,
        ["/workspace/run_tracker.py"],
        volumes=[
          (str(self._temp_dir.absolute()), "/workspace")
        ],
        workdir="/workspace",
        entrypoint="python",
        remove=True,
        stream=True
      )
      # Stream output to console in real-time
      for stream_type, stream_content in output:
        print(f"[tracker {stream_type}] {stream_content.decode('utf-8')}", end='')

    except Exception as e:
      raise RuntimeError(f"Container execution failed: {str(e)}") from e

  def _persist_artifact(self, source: Path, filename: str) -> None:
    """Persist artifact to configured output folder if available."""
    if not self._output_folder or not source.exists():
      return

    destination = self._output_folder / filename
    shutil.copy(source, destination)
