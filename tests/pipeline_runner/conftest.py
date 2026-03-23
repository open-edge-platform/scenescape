# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Pytest configuration and shared fixtures for pipeline_runner tests.

Device availability is read from environment variables:

  GPU_DEVICE_COUNT   number of GPU devices available (default: 0)
  NPU_DEVICE_COUNT   number of NPU devices available (default: 0)

Tests decorated with ``requires_gpu``, ``requires_gpu2``, or ``requires_npu``
are automatically skipped when the corresponding count is insufficient.
"""

import json
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]

# Ensure PipelineRunner and scene_common are importable when running on the host.
# Insert the correct paths first, then evict any stale sys.modules entries for
# scene_common that may have been cached by tests/conftest.py before this file
# was loaded (the installed scene_common stub lacks 'schema', 'log', etc.).
sys.path.insert(0, str(_REPO_ROOT / "tools" / "pipeline_runner"))
sys.path.insert(0, str(_REPO_ROOT / "scene_common" / "src"))
for _mod in [k for k in sys.modules if k == "scene_common" or k.startswith("scene_common.")]:
  del sys.modules[_mod]

from pipeline_runner import PipelineRunner  # noqa: E402 - needs path setup above

_GPU_COUNT = int(os.environ.get("GPU_DEVICE_COUNT", "0"))
_NPU_COUNT = int(os.environ.get("NPU_DEVICE_COUNT", "0"))


def pytest_configure(config):
  """Register custom device-requirement marks."""
  config.addinivalue_line(
    "markers",
    "requires_gpu: test requires at least one GPU (set GPU_DEVICE_COUNT >= 1)",
  )
  config.addinivalue_line(
    "markers",
    "requires_gpu2: test requires at least two GPUs (set GPU_DEVICE_COUNT >= 2)",
  )
  config.addinivalue_line(
    "markers",
    "requires_npu: test requires at least one NPU (set NPU_DEVICE_COUNT >= 1)",
  )


def pytest_collection_modifyitems(config, items):
  """Skip device-specific tests when the hardware is unavailable."""
  skip_gpu = pytest.mark.skip(
    reason="GPU not available - set GPU_DEVICE_COUNT=<n> to enable"
  )
  skip_gpu2 = pytest.mark.skip(
    reason="Two GPUs required - set GPU_DEVICE_COUNT=2 to enable"
  )
  skip_npu = pytest.mark.skip(
    reason="NPU not available - set NPU_DEVICE_COUNT=<n> to enable"
  )

  for item in items:
    if item.get_closest_marker("requires_gpu") and _GPU_COUNT < 1:
      item.add_marker(skip_gpu)
    if item.get_closest_marker("requires_gpu2") and _GPU_COUNT < 2:
      item.add_marker(skip_gpu2)
    if item.get_closest_marker("requires_npu") and _NPU_COUNT < 1:
      item.add_marker(skip_npu)



_INTRINSICS = {
  "intrinsics_fx": "905",
  "intrinsics_fy": "905",
  "intrinsics_cx": "640",
  "intrinsics_cy": "360",
  "distortion_k1": "0",
  "distortion_k2": "0",
  "distortion_p1": "0",
  "distortion_p2": "0",
  "distortion_k3": "0",
}


def make_camera_settings(sensor_id: str, camerachain: str, source_file: str) -> dict:
  """Return a minimal camera settings dict ready to be written as JSON."""
  return {
    "name": sensor_id,
    "sensor_id": sensor_id,
    "command": f"file://{source_file}",
    "cv_subsystem": "AUTO",
    "camerachain": camerachain,
    "modelconfig": "model_config.json",
    **_INTRINSICS,
  }


@pytest.fixture
def camera_settings_path(request):
  """Write a camera settings JSON for the parameterized scenario and return its path.

  The file is written under the repo root so that PipelineRunner can map it
  into the Docker container as /workspace/<relative-path>.  It is removed
  after the test regardless of pass/fail.

  Tests that use this fixture must be parametrised with a ``PipelineScenario``
  instance via ``request.param``.
  """
  scenario = request.param
  settings = make_camera_settings(
    sensor_id=scenario.id,
    camerachain=scenario.camerachain,
    source_file=scenario.source_file,
  )
  # Must be inside the repo root so PipelineRunner can make it relative to it.
  config_dir = _REPO_ROOT / "tools" / "pipeline_runner" / ".test_configs"
  config_dir.mkdir(exist_ok=True)
  path = config_dir / f"camera_settings_{scenario.id}.json"
  path.write_text(json.dumps(settings, indent=2))
  try:
    yield str(path)
  finally:
    path.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def schema_validator():
  """Return a SchemaValidation instance for the detector schema."""
  from scene_common.schema import SchemaValidation
  schema_path = str(_REPO_ROOT / "controller" / "src" / "schema" / "metadata.schema.json")
  return SchemaValidation(schema_path, is_multi_message=True)
