# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for tracker/schema/scene-data.schema.json."""

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = (
  Path(__file__).resolve().parents[3]
  / "tracker"
  / "schema"
  / "scene-data.schema.json"
)


@pytest.fixture(scope="module")
def scene_data_schema():
  return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def validator(scene_data_schema):
  return jsonschema.Draft202012Validator(scene_data_schema)


def test_schema_accepts_minimal_tracker_envelope(validator):
  payload = {
    "id": "3bc091c7-e449-46a0-9540-29c499bca18c",
    "name": "Retail",
    "timestamp": "2026-01-20T10:05:01.590Z",
    "objects": [
      {
        "id": "8cce2bc7-51fc-4a6e-8c5d-a73ac72d3eb2",
        "category": "person",
        "translation": [-0.33, 2.48, 0.0],
        "velocity": [-0.04, 0.2, 0.0],
        "size": [0.5, 0.5, 1.85],
        "rotation": [0, 0, 0, 1],
      }
    ],
  }
  validator.validate(payload)


def test_schema_accepts_controller_proper_data_scene_fields(validator):
  """Controller publishes metrics/debug fields Analytics must not reject."""
  payload = {
    "id": "3bc091c7-e449-46a0-9540-29c499bca18c",
    "name": "Retail",
    "timestamp": "2026-01-20T10:05:01.590Z",
    "unique_detection_count": 1,
    "rate": 30.0,
    "debug_hmo_start_time": 1710000000.0,
    "debug_hmo_processing_time": 0.012,
    "objects": [
      {
        "id": "8cce2bc7-51fc-4a6e-8c5d-a73ac72d3eb2",
        "type": "person",
        "translation": [1.0, 2.0, 0.0],
        "velocity": [0.0, 0.0, 0.0],
        "size": [0.5, 0.5, 1.8],
        "rotation": [0, 0, 0, 1],
        "confidence": None,
        "visibility": ["camera1"],
      }
    ],
  }
  validator.validate(payload)


def test_schema_accepts_detection_passthrough_extra_fields(validator):
  """Detection metadata may extend the envelope without schema churn."""
  payload = {
    "id": "scene-1",
    "name": "Retail",
    "timestamp": "2026-01-20T10:05:01.590Z",
    "detector_custom_metric": 42,
    "objects": [
      {
        "id": "track-1",
        "category": "person",
        "translation": [0.0, 0.0, 0.0],
        "velocity": [0.0, 0.0, 0.0],
        "size": [0.5, 0.5, 1.8],
        "rotation": [0, 0, 0, 1],
        "custom_detector_field": {"foo": "bar"},
      }
    ],
  }
  validator.validate(payload)


def test_schema_rejects_missing_required_top_level_fields(validator):
  payload = {
    "id": "scene-1",
    "name": "Retail",
    "objects": [],
  }
  errors = list(validator.iter_errors(payload))
  assert errors
  assert any("timestamp" in e.message for e in errors)


def test_schema_rejects_object_missing_translation(validator):
  payload = {
    "id": "scene-1",
    "name": "Retail",
    "timestamp": "2026-01-20T10:05:01.590Z",
    "objects": [
      {
        "id": "track-1",
        "velocity": [0.0, 0.0, 0.0],
        "size": [0.5, 0.5, 1.8],
        "rotation": [0, 0, 0, 1],
      }
    ],
  }
  errors = list(validator.iter_errors(payload))
  assert errors
  assert any("translation" in e.message for e in errors)


def test_schema_rejects_confidence_out_of_range(validator):
  payload = {
    "id": "scene-1",
    "name": "Retail",
    "timestamp": "2026-01-20T10:05:01.590Z",
    "objects": [
      {
        "id": "track-1",
        "translation": [0.0, 0.0, 0.0],
        "velocity": [0.0, 0.0, 0.0],
        "size": [0.5, 0.5, 1.8],
        "rotation": [0, 0, 0, 1],
        "confidence": 1.5,
      }
    ],
  }
  errors = list(validator.iter_errors(payload))
  assert errors
