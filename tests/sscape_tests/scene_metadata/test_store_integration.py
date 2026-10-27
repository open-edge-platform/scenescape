# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import uuid

import pytest

from scene_metadata.db import Database
from scene_metadata.envelope import EventEnvelope
from scene_metadata.store import EventStore

pytestmark = pytest.mark.test_name('SC-SceneMetadata-Store')

pytestmark_integration = pytest.mark.skipif(
  not os.environ.get('SCENE_METADATA_DATABASE_URL'),
  reason='Set SCENE_METADATA_DATABASE_URL for Timescale integration test',
)


@pytestmark_integration
def test_insert_and_query_timeline():
  db = Database()
  db.open()
  store = EventStore(db)
  event = EventEnvelope(
    occurred_at=__import__('datetime').datetime(2026, 1, 1, tzinfo=__import__('datetime').timezone.utc),
    event_type='region_enter',
    source_topic='scenescape/event/region/s1/r1/count',
    deployment_id='test-dep',
    scene_id='s1',
    region_id='r1',
    identity_id='gid-1',
    source_message_id=f'integration-test-{uuid.uuid4()}',
    payload={'entered': [{'id': 'gid-1'}]},
  )
  assert store.insert_events([event]) == 1
  rows = store.identity_timeline(deployment_id='test-dep', identity_id='gid-1')
  assert len(rows) >= 1
  assert rows[0]['event_type'] == 'region_enter'
  db.close()
