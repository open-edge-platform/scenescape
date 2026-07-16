# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Generate pipeline-config.json for user-provided cameras and RTSP streams.

Implements the specification in references/pipeline-config.md.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

# RFC 1123 hostname / dotted-IPv4 chars only. Rejects anything else (e.g. stray
# control characters) that could otherwise flow into the generated .env file's
# no_proxy value.
_VALID_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9.-]+$")

from deploy_inputs import load_inputs, validate_camera_streams

MODEL_XML = (
  "/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/"
  "person-detection-retail-0013.xml"
)
MODEL_PROC = "/home/pipeline-server/model-proc-files/person-detection-retail-0013.json"
SSCAPE_ADAPTER = "/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py"

PIPELINE_PARAMETERS = {
  "type": "object",
  "properties": {
    "ntp_config": {
      "element": {"name": "timesync", "property": "kwarg", "format": "json"},
      "type": "object",
      "properties": {"ntpServer": {"type": "string"}},
    },
    "frame_ntp_config": {
      "element": {"name": "timesync", "property": "kwarg", "format": "json"},
      "type": "object",
      "properties": {
        "useFrameNtpTimestamp": {
          "type": "boolean",
          "description": (
            "When true, use the NTP timestamp embedded in the RTSP frame metadata "
            "instead of the post-decode system time."
          ),
        },
      },
    },
    "camera_config": {
      "element": {"name": "datapublisher", "property": "kwarg", "format": "json"},
      "type": "object",
      "properties": {
        "cameraid": {"type": "string"},
        "metadatagenpolicy": {
          "type": "string",
          "description": (
            "Meta data generation policy, one of "
            "detectionPolicy(default),reidPolicy,classificationPolicy"
          ),
        },
        "publish_frame": {
          "type": "boolean",
          "description": "Publish frame to mqtt",
        },
        "detection_labels": {
          "type": "array",
          "items": {"type": "string"},
          "description": (
            "List of detection labels to filter (e.g., [\"person\", \"car\"]). "
            "If empty, all labels are published."
          ),
        },
      },
    },
  },
}


def gstreamer_pipeline(rtsp_url: str) -> str:
  return (
    f"rtspsrc location={rtsp_url} add-reference-timestamp-meta=true latency=200 "
    f"! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR "
    f"! gvapython class=PostDecodeTimestampCapture function=processFrame "
    f"module={SSCAPE_ADAPTER} name=timesync "
    f"! gvadetect model={MODEL_XML} model-proc={MODEL_PROC} "
    f"! gvametaconvert add-tensor-data=true name=metaconvert "
    f"! gvapython class=PostInferenceDataPublish function=processFrame "
    f"module={SSCAPE_ADAPTER} name=datapublisher "
    f"! gvametapublish name=destination ! appsink sync=true"
  )


def pipeline_entry(camera_id: str, rtsp_url: str) -> dict:
  return {
    "name": camera_id,
    "source": "gstreamer",
    "pipeline": gstreamer_pipeline(rtsp_url),
    "auto_start": True,
    "parameters": PIPELINE_PARAMETERS,
    "payload": {
      "parameters": {
        "ntp_config": {"ntpServer": "ntpserv"},
        "frame_ntp_config": {"useFrameNtpTimestamp": False},
        "camera_config": {
          "cameraid": camera_id,
          "metadatagenpolicy": "detectionPolicy",
          "detection_labels": ["person"],
        },
      },
    },
  }


def rtsp_no_proxy_hosts(streams: list[str]) -> list[str]:
  hosts: list[str] = []
  seen: set[str] = set()
  for stream in streams:
    host = urlparse(stream).hostname
    if host and _VALID_HOSTNAME_RE.match(host) and host not in seen:
      seen.add(host)
      hosts.append(host)
  return hosts


def generate_pipeline_config(
  deploy_dir: Path,
  camera_ids: list[str],
  streams: list[str],
) -> list[str]:
  validate_camera_streams(camera_ids, streams)

  config = {
    "config": {
      "logging": {"C_LOG_LEVEL": "INFO", "PY_LOG_LEVEL": "INFO"},
      "pipelines": [
        pipeline_entry(camera_id, stream)
        for camera_id, stream in zip(camera_ids, streams)
      ],
    },
  }

  output_path = deploy_dir / "dlstreamer-pipeline-server" / "pipeline-config.json"
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
  return rtsp_no_proxy_hosts(streams)


def resolve_camera_streams(
  deploy_dir: Path,
  inputs_file: Path | None,
  from_deploy_inputs: bool,
  camera_ids: list[str] | None,
  streams: list[str] | None,
) -> tuple[list[str], list[str]]:
  if camera_ids is not None and streams is not None:
    return camera_ids, streams
  if inputs_file is not None:
    payload = json.loads(inputs_file.read_text(encoding="utf-8"))
    return payload["camera_ids"], payload["streams"]
  if from_deploy_inputs:
    payload = load_inputs(deploy_dir)
    return payload["camera_ids"], payload["streams"]
  raise ValueError("provide --camera-ids and --streams, --inputs-file, or --from-deploy-inputs")


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Generate pipeline-config.json for deployment cameras",
  )
  parser.add_argument("--deploy-dir", required=True, type=Path)
  parser.add_argument("--inputs-file", type=Path, help="deploy-inputs.json from Step 1")
  parser.add_argument("--from-deploy-inputs", action="store_true", help="Read deploy-inputs.json in deploy-dir")
  parser.add_argument("--camera-ids", nargs="+", metavar="CAMERA_ID")
  parser.add_argument("--streams", nargs="+", metavar="RTSP_URL")
  args = parser.parse_args()

  camera_ids, streams = resolve_camera_streams(
    args.deploy_dir,
    args.inputs_file,
    args.from_deploy_inputs,
    args.camera_ids,
    args.streams,
  )

  hosts = generate_pipeline_config(args.deploy_dir, camera_ids, streams)
  if hosts:
    print("no_proxy_hosts=" + ",".join(hosts))


if __name__ == "__main__":
  main()
