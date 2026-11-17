# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Camera source functional tests for the Kubernetes deployment."""

import json
import logging
import subprocess

import pytest

try:
  from utils.log import get_logger
  logger = get_logger(__name__)
except ImportError:
  logger = logging.getLogger(__name__)

# Runs inside the deployed web pod so the check covers the shipped manager image.
_PIPELINE_SOURCES_SCRIPT = """
import json, os, sys
sys.path.insert(0, os.environ["SCENESCAPE_HOME"])
from manager.ppl_generator import generate_pipeline_string_from_dict, PipelineGenerationValueError
results = {}
for command in json.loads(sys.argv[1]):
  try:
    settings = {"command": command, "camerachain": "retail", "cv_subsystem": "AUTO"}
    results[command] = {"pipeline": generate_pipeline_string_from_dict(settings)}
  except PipelineGenerationValueError as error:
    results[command] = {"error": str(error)}
print(json.dumps(results))
"""

_SUPPORTED_CAMERA_SOURCES = {
  "rtsp://camera.example:554/stream": ("rtspsrc location=rtsp://camera.example:554/stream ", True),
  "http://camera.example/mjpeg": ("souphttpsrc location=http://camera.example/mjpeg name=source ! multipartdemux ", True),
  "/dev/video0": ("v4l2src device=/dev/video0 name=source ! videoconvert ", False),
  "/dev/v4l/by-id/usb-cam-video-index0": ("v4l2src device=/dev/v4l/by-id/usb-cam-video-index0 name=source ! videoconvert ", False),
}
_UNSUPPORTED_CAMERA_SOURCES = ["ftp://camera.example/stream", "/dev/sda", "camera.ts"]


@pytest.mark.kubernetes_only
@pytest.mark.test_name("NEX-T15603")
def test_camera_sources(_k8s_manager, result_recorder):
  """Verify the deployed manager builds pipelines for RTSP, HTTP and V4L2 camera sources and rejects others."""
  sources = list(_SUPPORTED_CAMERA_SOURCES) + _UNSUPPORTED_CAMERA_SOURCES
  result = subprocess.run(
    ["kubectl", "exec", "deployment/scenescape-web-dep",
     "--namespace", "scenescape",
     "--kubeconfig", _k8s_manager.kubeconfig,
     "--", "python3", "-c", _PIPELINE_SOURCES_SCRIPT, json.dumps(sources)],
    capture_output=True, text=True, check=True,
  )
  generated = json.loads(result.stdout.strip().splitlines()[-1])

  for source, (expected_start, uses_decodebin3) in _SUPPORTED_CAMERA_SOURCES.items():
    assert "pipeline" in generated[source], f"{source} was rejected: {generated[source]}"
    pipeline = generated[source]["pipeline"]
    logger.info("Source %s -> %s", source, pipeline)
    assert pipeline.startswith(expected_start), f"Unexpected source elements for {source}: {pipeline}"
    # Raw V4L2 video cannot go through decodebin3 (fails to link to gvadetect)
    assert ("decodebin3" in pipeline) == uses_decodebin3, f"Unexpected decoder for {source}: {pipeline}"

  for source in _UNSUPPORTED_CAMERA_SOURCES:
    assert "error" in generated[source], f"{source} was accepted: {generated[source]}"
  result_recorder.success()
