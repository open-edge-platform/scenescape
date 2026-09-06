# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for vehicle-detection pipeline scenarios.

Models under test
-----------------
  pvbcross16  - person/vehicle/bike detector (first stage)
  vehattr     - vehicle-attributes classifier (chained after pvbcross16)

Source video: car-detection.ts

Each scenario spins up a full Docker Compose stack via ``PipelineRunner``,
subscribes to the MQTT detection topic, collects at least
``MIN_DETECTIONS`` messages, validates every message against the Scenescape
detector JSON schema, and tears the stack down - even on failure.

Hardware-specific scenarios are skipped automatically when the corresponding
``GPU_DEVICE_COUNT`` / ``NPU_DEVICE_COUNT`` environment variables are not set.
"""

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "tools" / "pipeline_runner"))

from pipeline_runner import PipelineRunner  # noqa: E402
from tests.pipeline_runner.scenarios import VEHICLE_SCENARIOS, PipelineScenario

TEST_NAME = "NEX-T21524"

MIN_DETECTIONS = 200
MIN_CATEGORY_DETECTIONS = 3
COLLECT_TIMEOUT = 120  # seconds - generous to allow model  warm-up


def _count_by_aliases(category_counts: dict[str, int], *aliases: str) -> int:
  """Return total object count across equivalent category labels."""
  return sum(category_counts.get(alias, 0) for alias in aliases)


def _apply_marks(scenario: PipelineScenario):
  """Convert scenario mark names to live pytest marks for parametrize."""
  marks = [getattr(pytest.mark, m) for m in scenario.marks]
  return pytest.param(scenario, marks=marks, id=scenario.id)

class TestVehiclePipelines:
  """Integration tests for vehicle-detection model chains on car-detection.ts."""

  @pytest.mark.parametrize(
    "camera_settings_path",
    [_apply_marks(s) for s in VEHICLE_SCENARIOS],
    indirect=True,
  )
  def test_detections_received_and_valid(self, camera_settings_path, schema_validator, sample_data):
    """Pipeline produces detections that pass the Scenescape detector schema.

    Positive test: for each scenario launch the pipeline, collect
    MIN_DETECTIONS messages within COLLECT_TIMEOUT seconds, and assert every
    message validates against the detector schema.
    """
    with PipelineRunner(camera_settings_path) as runner:
      detections = runner.collect(
        timeout=COLLECT_TIMEOUT,
        min_detections=MIN_DETECTIONS,
      )

    assert len(detections) >= MIN_DETECTIONS, (
      f"Expected >= {MIN_DETECTIONS} detections, got {len(detections)}"
    )

    for i, detection in enumerate(detections):
      assert schema_validator.validateMessage("detector", detection), (
        f"Detection {i} failed schema validation:\n{detection}"
      )

    category_counts = {}
    for detection in detections:
      for cat, objs in detection.get("objects", {}).items():
        if objs:
          category_counts[cat] = category_counts.get(cat, 0) + len(objs)

    print(f"Category counts: {category_counts}")

    person_count = _count_by_aliases(category_counts, "person", "1")
    vehicle_count = _count_by_aliases(category_counts, "vehicle", "2")

    assert person_count >= MIN_CATEGORY_DETECTIONS, (
      f"Expected >= {MIN_CATEGORY_DETECTIONS} person detections, "
      f"got {person_count}"
    )
    assert vehicle_count >= MIN_CATEGORY_DETECTIONS, (
      f"Expected >= {MIN_CATEGORY_DETECTIONS} vehicle detections, "
      f"got {vehicle_count}"
    )


  def test_invalid_sensor_id_raises(self, tmp_path, sample_data):
    """PipelineRunner raises when the camera settings file is missing sensor_id.

    Negative test: a settings file without the required ``sensor_id`` key
    must raise a KeyError during construction so misconfigured files are
    caught early, before any Docker stack is started.
    """
    import json
    settings = {
      "name": "car-no-id",
      # 'sensor_id' intentionally omitted
      "command": "file://car-detection.ts",
      "cv_subsystem": "AUTO",
      "camerachain": "pvbcross16=CPU",
      "modelconfig": "model_config.json",
      "intrinsics_fx": "905", "intrinsics_fy": "905",
      "intrinsics_cx": "640", "intrinsics_cy": "360",
      "distortion_k1": "0", "distortion_k2": "0",
      "distortion_p1": "0", "distortion_p2": "0",
      "distortion_k3": "0",
    }
    path = tmp_path / "missing_sensor_id.json"
    path.write_text(json.dumps(settings))

    with pytest.raises(KeyError):
      PipelineRunner(str(path))  # should fail in _get_camera_id()

  def test_collect_raises_without_stopping_condition(self, tmp_path, sample_data):
    """collect() must raise ValueError when called with neither timeout nor min_detections.

    Negative test: calling collect() without any stopping condition is a
    programming error and must be caught at call time.
    """
    import json
    settings = {
      "name": "car-no-stop",
      "sensor_id": "car-no-stop",
      "command": "file://car-detection.ts",
      "cv_subsystem": "AUTO",
      "camerachain": "pvbcross16=CPU",
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
