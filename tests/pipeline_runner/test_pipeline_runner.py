# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the PipelineRunner class itself (not model-specific behavior).

These tests validate PipelineRunner's own argument/config handling and are
independent of which detection model chain is configured. They never call
start() and never touch Docker.
"""

import json

import pytest

from pipeline_runner import PipelineRunner


@pytest.mark.test_name("NEX-T29223")
def test_collect_raises_without_stopping_condition(tmp_path, sample_data, result_recorder):
  """collect() must raise ValueError when called with neither timeout nor min_detections.

  Negative test: calling collect() without any stopping condition is a
  programming error and must be caught at call time, not silently hang.
  """
  settings = {
    "name": "test-no-stop",
    "sensor_id": "test-no-stop",
    "command": "file://qcam1.ts",
    "cv_subsystem": "AUTO",
    "camerachain": "retail=CPU",
    "modelconfig": "model_config.json",
    "intrinsics_fx": "905", "intrinsics_fy": "905",
    "intrinsics_cx": "640", "intrinsics_cy": "360",
    "distortion_k1": "0", "distortion_k2": "0",
    "distortion_p1": "0", "distortion_p2": "0",
    "distortion_k3": "0",
  }
  path = tmp_path / "no_stop.json"
  path.write_text(json.dumps(settings))

  runner = PipelineRunner(str(path))
  with pytest.raises(ValueError, match="timeout.*min_detections"):
    runner.collect()  # neither timeout nor min_detections provided
  result_recorder.success()
