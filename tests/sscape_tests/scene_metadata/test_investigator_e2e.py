# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""End-to-end investigator path: ingest normalization → store → HTTP API."""

import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from scene_metadata.db import Database
from scene_metadata.envelope import EventEnvelope
from scene_metadata.ingest import MqttIngest
from scene_metadata.normalize import analytics_event_envelopes, track_lifecycle_events
from scene_metadata.query_app import create_app
from scene_metadata.store import EventStore
from scene_metadata.topics import AnalyticsEventTopic, SceneTopic

pytestmark = pytest.mark.test_name('SC-SceneMetadata-E2E')

pytestmark_integration = pytest.mark.skipif(
  not os.environ.get('SCENE_METADATA_DATABASE_URL'),
  reason='SCENE_METADATA_DATABASE_URL required',
)


@pytestmark_integration
def test_investigator_fused_timeline_http():
  deployment = f'e2e-dep-{uuid.uuid4().hex[:8]}'
  os.environ['SCENE_METADATA_DEPLOYMENT_ID'] = deployment
  db = Database()
  db.open()
  store = EventStore(db)

  scene = SceneTopic(scene_id='scene-e2e', category='person')
  track_payload = {
    'timestamp': '2026-01-15T10:00:00Z',
    'objects': [{'id': 'inv-uuid-1', 'type': 'person'}],
  }
  track_events, active = track_lifecycle_events(
    topic=scene, payload=track_payload, previous_ids=set(), deployment_id=deployment)
  assert store.insert_events(track_events) == 1

  region_topic = AnalyticsEventTopic(
    region_type='region', scene_id='scene-e2e', resource_id='roi-1', event_type='count')
  region_payload = {
    'timestamp': '2026-01-15T10:00:05Z',
    'scene_id': 'scene-e2e',
    'region_id': 'roi-1',
    'entered': [{'id': 'inv-uuid-1', 'category': 'person'}],
    'exited': [],
    'counts': {'person': 1},
  }
  region_events = analytics_event_envelopes(
    topic=region_topic, payload=region_payload, deployment_id=deployment)
  assert store.insert_events(region_events) >= 2

  tw_topic = AnalyticsEventTopic(
    region_type='tripwire', scene_id='scene-e2e', resource_id='tw-1', event_type='objects')
  tw_payload = {
    'timestamp': '2026-01-15T10:00:10Z',
    'objects': [{'id': 'inv-uuid-1', 'type': 'person'}],
  }
  tw_events = analytics_event_envelopes(
    topic=tw_topic, payload=tw_payload, deployment_id=deployment)
  assert store.insert_events(tw_events) == 1

  client = TestClient(create_app(db))
  timeline = client.get('/v1/identities/inv-uuid-1/timeline').json()
  types = [row['event_type'] for row in timeline['events']]
  assert 'track_started' in types
  assert 'region_enter' in types
  assert 'tripwire_cross' in types

  graph_regions = client.get('/v1/graph/identities/inv-uuid-1/regions').json()
  assert any(edge['relation'] == 'ENTERED' for edge in graph_regions['edges'])

  graph_tw = client.get('/v1/graph/identities/inv-uuid-1/tripwires').json()
  assert any(edge['relation'] == 'CROSSED' for edge in graph_tw['edges'])

  db.close()


@pytestmark_integration
def test_mqtt_ingest_normalizer_path():
  deployment = 'e2e-mqtt'
  db = Database()
  db.open()
  store = EventStore(db)
  ingest = MqttIngest(store, deployment)
  topic = 'scenescape/event/tripwire/scene-e2e/tw-9/objects'
  payload = {
    'timestamp': '2026-01-15T11:00:00Z',
    'objects': [{'id': 'gid-55', 'type': 'person'}],
  }
  events = ingest._normalize(topic, payload)
  assert len(events) == 1
  assert events[0].event_type == 'tripwire_cross'
  db.close()
