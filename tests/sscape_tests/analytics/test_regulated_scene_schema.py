# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for analytics/schema/regulated-scene.schema.json."""

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = (
  Path(__file__).resolve().parents[3]
  / "analytics"
  / "schema"
  / "regulated-scene.schema.json"
)


@pytest.fixture(scope="module")
def validator():
  schema = json.loads(SCHEMA_PATH.read_text())
  return jsonschema.Draft202012Validator(schema)


def _camera(**overrides):
  camera = {
    'id': 'cam1',
    'translation': [0.0, 0.0, 3.0],
    'rotation': [1.0, 0.0, 0.0, 0.0],
    'scale': [1.0, 1.0, 1.0],
    'pose_locked': False,
    'pose_provenance': {'class': 'calibration', 'origin': 'manager.rest'},
    'dynamic_pose': False,
  }
  camera.update(overrides)
  return camera


def _payload(cameras=None):
  return {
    'id': 'scene-1',
    'name': 'Retail',
    'timestamp': '2026-01-20T10:05:01.590Z',
    'scene_rate': 30.0,
    'rate': {'cam1': 10.0},
    'objects': [],
    'cameras': cameras if cameras is not None else [_camera()],
  }


def test_schema_accepts_calibration_and_live_cameras(validator):
  validator.validate(_payload(cameras=[
    _camera(),
    _camera(
      id='handheld',
      pose_provenance={'class': 'live', 'origin': 'detector.extrinsics'},
      dynamic_pose=True,
      translation=[1.0, 2.0, 3.0],
    ),
  ]))


def test_schema_requires_pose_provenance(validator):
  camera = _camera()
  del camera['pose_provenance']
  with pytest.raises(jsonschema.ValidationError, match='pose_provenance'):
    validator.validate(_payload(cameras=[camera]))


@pytest.mark.parametrize('pose_class', ['configured', 'observation', ''])
def test_schema_rejects_unknown_provenance_class(validator, pose_class):
  with pytest.raises(jsonschema.ValidationError):
    validator.validate(_payload(cameras=[_camera(
      pose_provenance={'class': pose_class, 'origin': 'manager.rest'},
    )]))


def test_schema_rejects_missing_origin(validator):
  with pytest.raises(jsonschema.ValidationError):
    validator.validate(_payload(cameras=[_camera(
      pose_provenance={'class': 'live'},
    )]))


def test_schema_accepts_analytics_camera_state(validator):
  from analytics.service import AnalyticsService
  from scene_common.scene_model import SceneModel

  scene = SceneModel('Retail', None)
  scene.updateCameras([{
    'uid': 'cam1', 'resolution': [640, 480],
    'intrinsics': {'fx': 500, 'fy': 500, 'cx': 320, 'cy': 240},
    'translation': [0, 0, 3], 'rotation': [180, 0, 0], 'scale': [1, 1, 1],
    'pose_provenance': {'class': 'calibration', 'origin': 'manager.rest'},
  }])
  validator.validate(_payload(cameras=[
    AnalyticsService._camera_state(scene.cameras['cam1']),
  ]))
