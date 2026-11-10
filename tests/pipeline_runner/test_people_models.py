# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for people-detection pipeline scenarios.

Models under test
-----------------
  retail      - person detector (first stage)
  agegender   - age+gender classifier (chained after retail)
  personattr  - person-attributes classifier (chained after retail)
  reid        - person re-identification (chained after retail)

Source video: qcam1.ts

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
from tests.pipeline_runner.scenarios import PEOPLE_SCENARIOS, PipelineScenario

MIN_DETECTIONS = 30
MIN_CATEGORY_DETECTIONS = 3
COLLECT_TIMEOUT = 120  # seconds - generous to allow model  warm-up

def _apply_marks(scenario: PipelineScenario):
  """Convert scenario mark names to live pytest marks for parametrize."""
  marks = [getattr(pytest.mark, m) for m in scenario.marks]
  return pytest.param(scenario, marks=marks, id=scenario.id)

class TestPeoplePipelines:
  """Integration tests for people-detection model chains on qcam1.ts."""

  @pytest.mark.parametrize(
    "camera_settings_path",
    [_apply_marks(s) for s in PEOPLE_SCENARIOS],
    indirect=True,
  )
  @pytest.mark.test_name("NEX-T20170")
  def test_detections_received_and_valid(self, camera_settings_path, schema_validator,
                                          sample_data, result_recorder):
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

      assert category_counts.get("person", 0) >= MIN_CATEGORY_DETECTIONS, (
        f"Expected >= {MIN_CATEGORY_DETECTIONS} person detections, "
        f"got {category_counts.get('person', 0)}"
      )
      result_recorder.success()
