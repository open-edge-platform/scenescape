# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Collect calibration frames from one or more SceneScape cameras via MQTT.

Usage:
    python capture_calibration_frames.py \
        --deploy-dir ~/scenescape-deployment \
        --cameras camera1 camera2 \
        --out-dir /tmp/frames

Outputs one file per camera: <out_dir>/<camera_id>.jpg
"""

import base64
import argparse
import json
import subprocess
import time
from pathlib import Path


def collect_frames(
  project: str,
  deploy_dir: Path,
  camera_ids: list[str],
  out_dir: Path,
  timeout_per_camera: int = 30,
) -> None:
  """Collect calibration frames using TLS mosquitto clients on the deployment Docker network."""
  network = f"{project}_scenescape"
  ca_file = deploy_dir / "secrets" / "certs" / "scenescape-ca.pem"
  if not ca_file.is_file():
    raise FileNotFoundError(f"CA cert not found: {ca_file}")

  out_dir.mkdir(parents=True, exist_ok=True)
  mqtt_tls = ["--cafile", "/ca.pem", "--insecure"]
  ca_mount = ["-v", f"{ca_file.resolve()}:/ca.pem:ro"]

  for camera_id in camera_ids:
    image_topic = f"scenescape/image/calibration/camera/{camera_id}"
    cmd_topic = f"scenescape/cmd/camera/{camera_id}"
    sub_cmd = [
      "docker", "run", "--rm", "--network", network,
      *ca_mount,
      "eclipse-mosquitto:2", "mosquitto_sub",
      "-h", "broker.scenescape.intel.com", "-p", "1883",
      *mqtt_tls,
      "-t", image_topic, "-C", "1", "-W", str(timeout_per_camera),
    ]
    pub_cmd = [
      "docker", "run", "--rm", "--network", network,
      *ca_mount,
      "eclipse-mosquitto:2", "mosquitto_pub",
      "-h", "broker.scenescape.intel.com", "-p", "1883",
      *mqtt_tls,
      "-t", cmd_topic, "-m", "getcalibrationimage",
    ]

    sub = subprocess.Popen(sub_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1)
    subprocess.run(pub_cmd, check=True)
    out, err = sub.communicate(timeout=timeout_per_camera + 15)
    if sub.returncode != 0:
      raise TimeoutError(f"No calibration image received from {camera_id}: {err.strip()}")

    payload = json.loads(out)
    img_bytes = base64.b64decode(payload["image"])
    if not (img_bytes.startswith(b"\xff\xd8\xff") and img_bytes.endswith(b"\xff\xd9")):
      raise ValueError(f"Calibration image from {camera_id} is not a valid JPEG")

    out_path = out_dir / f"{camera_id}.jpg"
    out_path.write_bytes(img_bytes)
    print(f"Saved {out_path} ({len(img_bytes)} bytes, timestamp={payload.get('timestamp')})")

  print(f"Collected {len(camera_ids)} frame(s): {camera_ids}")


def main() -> None:
  parser = argparse.ArgumentParser(description="Collect calibration frames from SceneScape cameras via MQTT")
  parser.add_argument(
    "--deploy-dir",
    required=True,
    type=Path,
    help="Deployment directory (must contain secrets/certs/scenescape-ca.pem)",
  )
  parser.add_argument("--cameras", required=True, nargs="+", metavar="CAMERA_ID", help="One or more camera IDs")
  parser.add_argument("--out-dir", required=True, type=Path, help="Directory to write captured JPEG files")
  parser.add_argument("--project", default="scenescape", help="Docker Compose project name (default: scenescape)")
  parser.add_argument("--timeout-per-camera", type=int, default=30, metavar="SECONDS", help="Seconds to wait per camera (default: 30)")
  args = parser.parse_args()

  collect_frames(
    project=args.project,
    deploy_dir=args.deploy_dir,
    camera_ids=args.cameras,
    out_dir=args.out_dir,
    timeout_per_camera=args.timeout_per_camera,
  )


if __name__ == "__main__":
  main()
