# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from scene_metadata.normalize import analytics_event_envelopes, track_lifecycle_events
from scene_metadata.topics import AnalyticsEventTopic, SceneTopic

pytestmark = pytest.mark.test_name('SC-SceneMetadata-Normalize')


def test_track_lifecycle_started_and_lost():
  topic = SceneTopic(scene_id='scene-a', category='person')
  payload = {
    'timestamp': '2026-01-15T12:00:00Z',
    'objects': [{'id': 'gid-1', 'type': 'person'}],
  }
  events, current = track_lifecycle_events(
    topic=topic, payload=payload, previous_ids=set(), deployment_id='dep')
  assert current == {'gid-1'}
  assert len(events) == 1
  assert events[0].event_type == 'track_started'
  assert events[0].identity_id == 'gid-1'

  payload2 = {'timestamp': '2026-01-15T12:00:01Z', 'objects': []}
  events2, current2 = track_lifecycle_events(
    topic=topic, payload=payload2, previous_ids=current, deployment_id='dep')
  assert current2 == set()
  assert len(events2) == 1
  assert events2[0].event_type == 'track_lost'


def test_region_count_enter_exit_events():
  topic = AnalyticsEventTopic(
    region_type='region', scene_id='s1', resource_id='r1', event_type='count')
  payload = {
    'timestamp': '2026-01-15T12:00:00Z',
    'scene_id': 's1',
    'region_id': 'r1',
    'entered': [{'id': 'person-9', 'category': 'person'}],
    'exited': [],
    'counts': {'person': 1},
  }
  events = analytics_event_envelopes(topic=topic, payload=payload, deployment_id='dep')
  types = {event.event_type for event in events}
  assert 'region_enter' in types
  assert 'region_count' in types
  enter = next(e for e in events if e.event_type == 'region_enter')
  assert enter.identity_id == 'person-9'
  assert enter.region_id == 'r1'


def test_tripwire_cross_event():
  topic = AnalyticsEventTopic(
    region_type='tripwire', scene_id='s1', resource_id='tw1', event_type='objects')
  payload = {
    'timestamp': '2026-01-15T12:00:00Z',
    'objects': [{'id': 'gid-2', 'type': 'person'}],
  }
  events = analytics_event_envelopes(topic=topic, payload=payload, deployment_id='dep')
  assert len(events) == 1
  assert events[0].event_type == 'tripwire_cross'
  assert events[0].tripwire_id == 'tw1'
