# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Intel Corporation
"""PipelineRunner: run a DL Streamer pipeline-server pipeline from a camera settings file.

Usage as a library::

    from tools.pipeline_runner.pipeline_runner import PipelineRunner

    with PipelineRunner("camera_settings.json") as runner:
        detections = runner.collect(timeout=30)

Usage as a CLI tool::

    python -m tools.pipeline_runner --camera-settings-file camera_settings.json

The runner brings up the docker-compose stack, subscribes to the MQTT detection topic,
and tears everything down on exit (normal, exception, or OS signal).
"""

import argparse
import json
import os
import signal
import threading
import time
import sys
from pathlib import Path
from typing import Callable

import paho.mqtt.client as mqtt
from python_on_whales import DockerClient


# This file lives at <repo_root>/tools/pipeline_runner/pipeline_runner.py
# Adjust when moving this directory or file
_REPO_ROOT: Path = Path(__file__).parents[2]
_VERSION: str = (_REPO_ROOT / "version.txt").read_text().strip()

SUPPORTED_PROFILES = ["rtsp"]

DLSPS_CONFIG_FILE = "dlsps_config.json"
VOLUME_PREFIX = "scenescape"
CAM_SETTINGS_SCRIPT = "/workspace/tools/pipeline_runner/cam_settings_to_dlsps_config.py"
OUTPUT_DIR = "output"
DLS_METADATA_OUTPUT_FILE = "dls_metadata.jsonl"
SCENESCAPE_METADATA_FILE = "scenescape_metadata.jsonl"
COMPOSE_FILE = Path(__file__).parent / "docker-compose-ppl.yaml"
NPU_DEVICE = "/dev/accel"
NPU_OVERRIDE_FILE = Path(__file__).parent / "docker-compose-ppl.npu.yaml"

BROKER_HOST = "localhost"
BROKER_PORT = 1884
DETECTION_TOPIC = "scenescape/data/camera/{camera_id}"
BROKER_CONNECT_TIMEOUT = 30


class PipelineRunner:
  def __init__(
    self,
    camera_settings_file: str,
    profile: str | None = None,
    dump_dls_metadata: bool = False,
    model_configs_folder: str | None = None,
    output_dir: str | None = None,
  ):
    self.camera_settings_file = camera_settings_file
    self.profile = profile
    self.dump_dls_metadata = dump_dls_metadata

    self._root = _REPO_ROOT
    self.root_dir = str(self._root)
    self.secrets_dir = os.path.join(self.root_dir, "manager", "secrets")
    self.tools_dir = os.path.join(self.root_dir, "tools")
    self.model_configs_folder = model_configs_folder
    self.dlsps_config_file = str(COMPOSE_FILE.parent / DLSPS_CONFIG_FILE)
    self.output_dir = output_dir or str(COMPOSE_FILE.parent / OUTPUT_DIR)
    self.uid = os.getuid()
    self.gid = os.getgid()
    self.camera_id = self._get_camera_id()
    self._ppl_generator_image = f"scenescape-manager:{_VERSION}"
    self._running = False
    self._docker_client: DockerClient | None = None

  def _get_camera_id(self) -> str:
    with open(self.camera_settings_file) as f:
      return json.load(f)["sensor_id"]

  def _prepare_output(self):
    os.makedirs(self.output_dir, exist_ok=True)
    if self.dump_dls_metadata:
      dls_metadata_path = os.path.join(self.output_dir, DLS_METADATA_OUTPUT_FILE)
      if os.path.exists(dls_metadata_path):
        os.remove(dls_metadata_path)

  def _set_env_vars(self):
    os.environ.update({
      "DLSPS_CONFIG_FILE": self.dlsps_config_file,
      "ROOT_DIR": self.root_dir,
      "SECRETS_DIR": self.secrets_dir,
      "TOOLS_DIR": self.tools_dir,
      "OUTPUT_DIR": self.output_dir,
      "UID": str(self.uid),
      "GID": str(self.gid),
      "PROFILE": self.profile or "",
      "SCENESCAPE_METADATA_FILE": SCENESCAPE_METADATA_FILE,
      "CAMERA_ID": self.camera_id,
    })

  def _convert_cam_settings_to_dlsps_config(self):
    """Run cam_settings_to_dlsps_config.py inside the scenescape-manager container.

    The repo root is mounted as /workspace so all paths resolve inside the container.
    """
    docker = DockerClient()
    envs = {
      "PYTHONPATH": "/home/scenescape/SceneScape/",
    }
    if self.dump_dls_metadata:
      envs["METADATA_OUTPUT_FILE"] = (
        f"/home/pipeline-server/output/{DLS_METADATA_OUTPUT_FILE}"
      )

    # Make paths relative to repo root so they resolve inside the container
    cam_settings_in_container = "/workspace/" + str(
      Path(self.camera_settings_file).resolve().relative_to(self._root)
    )
    dlsps_config_in_container = "/workspace/" + str(
      Path(self.dlsps_config_file).resolve().relative_to(self._root)
    )
    # Model configs: default to the Docker volume path (matching the shell script).
    # If the user provided an explicit path, map it into /workspace/.
    if self.model_configs_folder:
      model_configs_in_container = "/workspace/" + str(
        Path(self.model_configs_folder).resolve().relative_to(self._root)
      )
    else:
      model_configs_in_container = "/models/model_configs"

    cmd = [
      CAM_SETTINGS_SCRIPT,
      "--camera-settings", cam_settings_in_container,
      "--config_folder", model_configs_in_container,
      "--output_path", dlsps_config_in_container,
    ]
    if self.dump_dls_metadata:
      cmd.append("--dump-dls-metadata")

    docker.run(
      self._ppl_generator_image,
      cmd,
      remove=True,
      envs=envs,
      user=f"{self.uid}:{self.gid}",
      entrypoint="python",
      volumes=[
        (str(self._root), "/workspace"),
        (f"{VOLUME_PREFIX}_vol-models", "/models"),
      ],
      workdir="/workspace",
    )

  def _make_docker_client(self) -> DockerClient:
    compose_files = [str(COMPOSE_FILE)]
    if os.path.exists(NPU_DEVICE):
      compose_files.append(str(NPU_OVERRIDE_FILE))
    return DockerClient(
      compose_files=compose_files,
      compose_profiles=[self.profile] if self.profile else [],
    )

  def start(self) -> "PipelineRunner":
    """Prepare config and bring up the docker compose stack.

    Returns self to allow chaining or use as a context manager.
    """
    self._prepare_output()

    # Convert camera settings to DLSPS config (runs inside scenescape-manager container)
    self._convert_cam_settings_to_dlsps_config()

    # Inject docker compose variables into the process environment
    self._set_env_vars()

    # Run docker compose (equivalent to: docker compose -f docker-compose-ppl.yaml [--profile PROFILE] up -d)
    self._docker_client = self._make_docker_client()
    try:
      self._docker_client.compose.up(detach=True)
      self._running = True
    except Exception:
      # Best-effort cleanup: if compose.up() failed after starting some
      # services, attempt to bring the stack down even though _running is
      # still False and down() would otherwise be a no-op.
      if self._docker_client is not None:
        try:
          self._docker_client.compose.down()
        except Exception:
          # Suppress cleanup errors to avoid masking the original failure.
          pass
      raise
    return self

  def stop(self) -> None:
    """Stop all compose services (containers are kept; can be restarted)."""
    if self._running:
      self._docker_client.compose.stop()

  def down(self) -> None:
    """Stop and remove all compose services and containers (full cleanup)."""
    if self._running:
      self._docker_client.compose.down()
      self._running = False

  def get_logs(self) -> str:
    """Return combined stdout+stderr logs from all compose services."""
    return self._docker_client.compose.logs()

  @classmethod
  def teardown(cls) -> None:
    """Tear down all pipeline compose services from outside a running PipelineRunner.

    Useful when the runner process has already exited but containers are still
    running in the background. Equivalent to running ``docker compose down``
    against the pipeline compose file.
    """
    root_dir = str(_REPO_ROOT)
    secrets_dir = os.path.join(root_dir, "manager", "secrets")
    dlsps_config_file = str(COMPOSE_FILE.parent / DLSPS_CONFIG_FILE)
    # docker-compose-ppl.yaml references DLSPS_CONFIG_FILE via a config section;
    # the file must exist for compose to parse the YAML without errors.
    Path(dlsps_config_file).touch()
    os.environ.update({
      "DLSPS_CONFIG_FILE": dlsps_config_file,
      "ROOT_DIR": root_dir,
      "SECRETS_DIR": secrets_dir,
      "TOOLS_DIR": os.path.join(root_dir, "tools"),
      "OUTPUT_DIR": str(COMPOSE_FILE.parent / OUTPUT_DIR),
      "UID": str(os.getuid()),
      "GID": str(os.getgid()),
      "PROFILE": "",
      "SCENESCAPE_METADATA_FILE": SCENESCAPE_METADATA_FILE,
      "CAMERA_ID": "",
    })
    compose_files = [str(COMPOSE_FILE)]
    if os.path.exists(NPU_DEVICE):
      compose_files.append(str(NPU_OVERRIDE_FILE))
    # Include all supported profiles so profile-gated services (e.g. rtsp) are
    # also stopped regardless of which profile was used to start the pipeline.
    DockerClient(compose_files=compose_files, compose_profiles=SUPPORTED_PROFILES).compose.down()

  def __enter__(self) -> "PipelineRunner":
    return self.start()

  def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    if exc_type is not None and self._running:
      print("\n--- Docker Compose container logs (captured on failure) ---", file=sys.stderr)
      try:
        print(self.get_logs(), file=sys.stderr)
      except Exception as log_err:
        print(f"(Failed to retrieve container logs: {log_err})", file=sys.stderr)
      print("--- End of container logs ---\n", file=sys.stderr)
    self.down()

  def collect(
    self,
    timeout: float | None = None,
    min_detections: int | None = None,
    message_callback: Callable[[dict], None] | None = None,
  ) -> list[dict]:
    """Subscribe to the camera MQTT topic and collect detection messages.

    Stops collecting when *either* condition is satisfied:
      - ``timeout`` seconds have elapsed (if provided)
      - at least ``min_detections`` messages have been received (if provided)

    At least one of ``timeout`` or ``min_detections`` must be given.

    Args:
        timeout: Maximum number of seconds to wait for messages.
        min_detections: Stop as soon as this many messages have been received.
        message_callback: Optional callable invoked with each parsed message
            as it arrives (useful for real-time inspection in tests).

    Returns:
        List of parsed JSON dicts collected from the detection topic.
    """
    if timeout is None and min_detections is None:
      raise ValueError("At least one of 'timeout' or 'min_detections' must be provided.")

    topic = DETECTION_TOPIC.format(camera_id=self.camera_id)
    messages: list[dict] = []
    stop_event = threading.Event()

    def on_connect(client, userdata, flags, rc):
      if rc == 0:
        client.subscribe(topic)

    def on_message(client, userdata, msg):
      try:
        payload = json.loads(msg.payload.decode())
      except json.JSONDecodeError:
        return
      messages.append(payload)
      if message_callback is not None:
        message_callback(payload)
      if min_detections is not None and len(messages) >= min_detections:
        stop_event.set()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    ca_cert = os.path.join(self.secrets_dir, "certs", "scenescape-ca.pem")
    client.tls_set(ca_certs=ca_cert)
    client.tls_insecure_set(True)  # hostname won't match "localhost"

    # Wait for the broker to become ready before subscribing
    deadline = time.monotonic() + BROKER_CONNECT_TIMEOUT
    while True:
      try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        break
      except (ConnectionRefusedError, OSError):
        if time.monotonic() >= deadline:
          raise TimeoutError(
            f"Broker at {BROKER_HOST}:{BROKER_PORT} did not become ready "
            f"within {BROKER_CONNECT_TIMEOUT}s."
          )
        time.sleep(1)

    client.loop_start()
    try:
      stop_event.wait(timeout=timeout)
    finally:
      client.loop_stop()
      client.disconnect()

    return messages


def parse_args():
  parser = argparse.ArgumentParser(
    description="Run a DL Streamer pipeline server pipeline from a camera settings file.",
  )
  parser.add_argument(
    "--camera-settings-file",
    metavar="CAMERA_SETTINGS_FILE",
    help="Path to the camera settings JSON file.",
  )
  parser.add_argument(
    "--profile",
    metavar="PROFILE",
    nargs="?",
    default=None,
    choices=SUPPORTED_PROFILES,
    help=f"Optional compose profile to activate. Supported profiles: {SUPPORTED_PROFILES}",
  )
  parser.add_argument(
    "--dump-dls-metadata",
    action="store_true",
    default=os.environ.get("DUMP_DLS_METADATA", "false").lower() == "true",
    help=(
      "Enable metadata dumping in DLStreamer format. "
      "Can also be set via the DUMP_DLS_METADATA environment variable."
    ),
  )
  parser.add_argument(
    "--output-dir",
    metavar="OUTPUT_DIR",
    default=None,
    help=(
      "Directory where output metadata files are written. "
      f"Defaults to '{OUTPUT_DIR}/' next to this script."
    ),
  )
  parser.add_argument(
    "--down",
    action="store_true",
    default=False,
    help=(
      "Tear down all pipeline containers and exit. "
      "Use this to clean up containers that are still running after the pipeline runner process has exited."
    ),
  )
  return parser.parse_args()


def main():
  args = parse_args()
  if args.down:
    PipelineRunner.teardown()
    return
  if not args.camera_settings_file:
    print("error: --camera-settings-file is required", file=sys.stderr)
    sys.exit(1)
  runner = PipelineRunner(
    camera_settings_file=args.camera_settings_file,
    profile=args.profile,
    dump_dls_metadata=args.dump_dls_metadata,
    output_dir=args.output_dir,
  )
  runner.start()


if __name__ == "__main__":
  main()
