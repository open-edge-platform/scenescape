# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Investigator queries that join ReID links with region and tripwire events."""

from collections import defaultdict
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scene_metadata.db import Database
from scene_metadata.physicalai_loader import (
  REGION_ID, REGION_Y, SCENE_ID, TRIPWIRE_ID, TRIPWIRE_X, load_directory,
)
from scene_metadata.query_app import create_app
from scene_metadata.store import EventStore

pytestmark = pytest.mark.test_name('SC-SceneMetadata-PhysicalAI-ReID')

DATA = Path(os.environ.get(
  'PHYSICALAI_LAB_DIR',
  Path(__file__).resolve().parents[3] / 'tools' / 'reid_evaluation' / 'output' / 'physicalai-lab-data',
))
DEPLOYMENT = 'physicalai-lab-reid'

pytestmark_data = pytest.mark.skipif(
  not os.environ.get('SCENE_METADATA_DATABASE_URL') or not (DATA / 'ground_truth.json').is_file(),
  reason='Timescale and PhysicalAI Lab_000 files are required',
)


def _expectations(path: Path) -> dict:
  """ReID and spatial answers computed directly from dataset labels."""
  ground_truth = json.loads((path / 'ground_truth.json').read_text(encoding='utf-8'))
  tracks = defaultdict(list)
  for frame in range(len(ground_truth)):
    for obj in ground_truth[str(frame)]:
      if obj.get('object type') != 'Person':
        continue
      tracks[f"person-{obj['object id']}"].append((frame, obj))

  expected = {}
  for identity, samples in tracks.items():
    seen = set()
    links = []
    anchor = None
    in_region = False
    first_enter = None
    prev_x = None
    first_cross = None
    for frame, obj in samples:
      visible = set(obj.get('2d bounding box visible') or {})
      if anchor is None and visible:
        anchor = min(visible)
      for camera_id in sorted(visible - seen):
        links.append({'frame': frame, 'camera_id': camera_id, 'anchor_camera': anchor})
      seen |= visible
      _x, y, _z = obj['3d location']
      inside = y > REGION_Y
      if inside and not in_region and first_enter is None:
        first_enter = frame
      in_region = inside
      if prev_x is not None and (prev_x < TRIPWIRE_X) != (_x < TRIPWIRE_X) and first_cross is None:
        first_cross = {
          'frame': frame,
          'cameras_visible': sorted(visible),
          'reid_cameras': sorted(seen),
        }
      prev_x = _x
    linked_before_enter = sorted(
      link['camera_id'] for link in links if first_enter is None or link['frame'] < first_enter)
    expected[identity] = {
      'anchor': anchor,
      'links': links,
      'linked_before_enter': linked_before_enter,
      'first_cross': first_cross,
    }
  return expected


@pytestmark_data
def test_reid_region_and_tripwire_queries():
  """Global ReID id, north-region entry, and the first tripwire crossing."""
  os.environ['SCENE_METADATA_DEPLOYMENT_ID'] = DEPLOYMENT
  expected = _expectations(DATA)
  db = Database()
  db.open()
  EventStore(db).insert_events(load_directory(DATA, DEPLOYMENT))
  client = TestClient(create_app(db))

  for identity, want in expected.items():
    timeline = client.get(
      f'/v1/identities/{identity}/timeline', params={'limit': 2000}).json()
    links = [
      {
        'frame': row['payload']['frame'],
        'camera_id': row['camera_id'],
        'anchor_camera': row['payload']['anchor_camera'],
      }
      for row in timeline['events'] if row['event_type'] == 'reid_link'
    ]
    assert links == want['links']
    assert {row['payload']['score'] for row in timeline['events'] if row['event_type'] == 'reid_link'} == {1.0}
    assert all(row['payload']['global_id'] == identity for row in timeline['events'] if row['event_type'] == 'reid_link')

    activity = client.get(
      f'/v1/regions/{REGION_ID}/activity', params={'limit': 2000}).json()
    enter_frames = [
      row['payload']['frame'] for row in activity['events']
      if row['event_type'] == 'region_enter' and row['identity_id'] == identity
    ]
    first_enter = min(enter_frames) if enter_frames else None
    linked_before = sorted(
      link['camera_id'] for link in links if first_enter is None or link['frame'] < first_enter)
    assert linked_before == want['linked_before_enter']

    crossings = client.post('/v1/events/query', json={
      'identity_id': identity,
      'event_types': ['reid_at_crossing'],
      'tripwire_id': TRIPWIRE_ID,
      'limit': 50,
    }).json()['events']
    assert crossings[0]['payload']['cameras_visible'] == want['first_cross']['cameras_visible']
    assert crossings[0]['payload']['reid_cameras'] == want['first_cross']['reid_cameras']
    assert crossings[0]['payload']['global_id'] == identity

  db.close()
