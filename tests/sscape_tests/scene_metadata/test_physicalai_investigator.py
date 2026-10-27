# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Investigator prompts against PhysicalAI Lab_000 ground truth."""

from collections import defaultdict
import json
import os
from pathlib import Path

import pytest

from scene_metadata.db import Database
from scene_metadata.physicalai_loader import (
  REGION_ID, SCENE_ID, TRIPWIRE_ID, TRIPWIRE_X, REGION_Y, load_directory,
)
from scene_metadata.store import EventStore

pytestmark = pytest.mark.test_name('SC-SceneMetadata-PhysicalAI')

DATA = Path(os.environ.get(
  'PHYSICALAI_LAB_DIR',
  Path(__file__).resolve().parents[3] / 'tools' / 'reid_evaluation' / 'output' / 'physicalai-lab-data',
))
DEPLOYMENT = 'physicalai-lab-000'

pytestmark_data = pytest.mark.skipif(
  not os.environ.get('SCENE_METADATA_DATABASE_URL') or not (DATA / 'ground_truth.json').is_file(),
  reason='Timescale and PhysicalAI Lab_000 files are required',
)


def _ground_truth_expectations(path: Path) -> dict:
  """Independent counts from the dataset labels, not from the loader."""
  ground_truth = json.loads((path / 'ground_truth.json').read_text(encoding='utf-8'))
  calibration = json.loads((path / 'calibration.json').read_text(encoding='utf-8'))
  cameras = sorted(
    sensor['id'] for sensor in calibration['sensors'] if sensor.get('type') == 'camera')
  seen = defaultdict(set)
  region_enters = defaultdict(int)
  crossings = defaultdict(int)
  in_region = defaultdict(bool)
  prev_x = {}
  frames = defaultdict(list)
  for frame in range(len(ground_truth)):
    for obj in ground_truth[str(frame)]:
      if obj.get('object type') != 'Person':
        continue
      identity = f"person-{obj['object id']}"
      frames[identity].append(frame)
      seen[identity].update(obj.get('2d bounding box visible') or {})
      _x, y, _z = obj['3d location']
      inside = y > REGION_Y
      if inside and not in_region[identity]:
        region_enters[identity] += 1
      in_region[identity] = inside
      if identity in prev_x and (prev_x[identity] < TRIPWIRE_X) != (_x < TRIPWIRE_X):
        crossings[identity] += 1
      prev_x[identity] = _x
  return {
    'cameras': cameras,
    'seen': {key: set(value) for key, value in seen.items()},
    'region_enters': dict(region_enters),
    'crossings': dict(crossings),
    'first': {key: min(value) for key, value in frames.items()},
    'last': {key: max(value) for key, value in frames.items()},
  }


@pytestmark_data
def test_investigator_prompts_match_ground_truth():
  """Ask the query API the questions an investigator would ask."""
  os.environ['SCENE_METADATA_DEPLOYMENT_ID'] = DEPLOYMENT
  expected = _ground_truth_expectations(DATA)
  db = Database()
  db.open()
  store = EventStore(db)
  store.insert_events(load_directory(DATA, DEPLOYMENT))

  from scene_metadata.query_app import create_app
  from fastapi.testclient import TestClient
  client = TestClient(create_app(db))

  cameras = client.post('/v1/events/query', json={
    'scene_id': SCENE_ID,
    'event_types': ['config_camera'],
    'limit': 50,
  }).json()
  camera_ids = sorted(row['camera_id'] for row in cameras['events'])
  assert camera_ids == expected['cameras']

  for identity, first in expected['first'].items():
    timeline = client.get(f'/v1/identities/{identity}/timeline', params={'limit': 2000}).json()
    started = [row for row in timeline['events'] if row['event_type'] == 'track_started']
    lost = [row for row in timeline['events'] if row['event_type'] == 'track_lost']
    assert started[0]['payload']['frame'] == first
    assert lost[0]['payload']['frame'] == expected['last'][identity]
    visible = {
      row['camera_id'] for row in timeline['events'] if row['event_type'] == 'camera_visible'
    }
    assert visible == expected['seen'][identity]

  activity = client.get(f'/v1/regions/{REGION_ID}/activity', params={'limit': 2000}).json()
  enters = defaultdict(int)
  for row in activity['events']:
    if row['event_type'] == 'region_enter':
      enters[row['identity_id']] += 1
  assert dict(enters) == expected['region_enters']

  crosses = client.get(
    f'/v1/tripwires/{TRIPWIRE_ID}/crossings', params={'limit': 2000}).json()
  counts = defaultdict(int)
  for row in crosses['events']:
    counts[row['identity_id']] += 1
  assert dict(counts) == expected['crossings']
  db.close()
