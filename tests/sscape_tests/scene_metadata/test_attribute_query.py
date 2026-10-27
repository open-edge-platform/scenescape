# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Attribute filters follow payload keys. They do not list model fields."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scene_metadata.attributes import AttributeFilterError, validate_attributes
from scene_metadata.db import Database
from scene_metadata.envelope import EventEnvelope
from scene_metadata.query_app import create_app
from scene_metadata.store import EventStore

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_SRC = REPO_ROOT / 'scene_metadata' / 'src' / 'scene_metadata'
RETAIL_CONFIG = REPO_ROOT / 'sample_data' / 'demo_scenes' / 'Retail' / 'retail-config.json'
MODEL_CONFIG = REPO_ROOT / 'dlstreamer-pipeline-server' / 'model_config.json'
PERSONATTR_XML = (
  'omz/person-attributes-recognition-crossroad-0238/FP32/'
  'person-attributes-recognition-crossroad-0238.xml'
)

pytestmark_integration = pytest.mark.skipif(
  not os.environ.get('SCENE_METADATA_DATABASE_URL'),
  reason='SCENE_METADATA_DATABASE_URL required',
)


def test_validate_accepts_attribute_names_the_server_does_not_list():
  assert validate_attributes({'scarf_color': 'crimson', 'is_male': 'male'}) == {
    'scarf_color': 'crimson',
    'is_male': 'male',
  }


def test_validate_rejects_empty_and_oversized_filters():
  with pytest.raises(AttributeFilterError):
    validate_attributes({'': 'male'})
  with pytest.raises(AttributeFilterError):
    validate_attributes({'   ': 'male'})
  with pytest.raises(AttributeFilterError):
    validate_attributes({'is_male': 'x' * 257})
  with pytest.raises(AttributeFilterError):
    validate_attributes({f'attr_{index}': 'yes' for index in range(17)})


QUERY_SOURCES = (
  'attributes.py',
  'store.py',
  'query_app.py',
  'mcp_server.py',
  'projection.py',
)


def test_query_server_does_not_hardcode_attribute_names():
  """Model head names stay out of the query path so the filter stays generic."""
  source = '\n'.join((SERVER_SRC / name).read_text() for name in QUERY_SOURCES)
  assert 'is_male' not in source
  assert 'has_bag' not in source
  assert 'scarf_color' not in source
  assert 'has_backpack' not in source


def test_retail_pipeline_classifies_person_attributes():
  config = json.loads(RETAIL_CONFIG.read_text())
  pipelines = config['config']['pipelines']
  assert len(pipelines) == 2
  for pipeline in pipelines:
    text = pipeline['pipeline']
    assert 'gvaclassify' in text
    assert PERSONATTR_XML in text
    assert 'inference-region=1' in text
    assert pipeline['payload']['parameters']['metadatagenpolicy'] == 'classificationPolicy'
  model_config = json.loads(MODEL_CONFIG.read_text())
  personattr = model_config['personattr']
  assert personattr['type'] == 'classify'
  assert personattr['params']['model'] == PERSONATTR_XML
  assert personattr['adapter-params']['metadatagenpolicy'] == 'classificationPolicy'


def _person_event(deployment: str, identity: str, metadata: dict, when: datetime) -> EventEnvelope:
  return EventEnvelope(
    occurred_at=when,
    event_type='track_started',
    source_topic='scenescape/data/scene/retail/person',
    deployment_id=deployment,
    scene_id='retail',
    identity_id=identity,
    track_id=identity,
    source_message_id=f'attr-{uuid.uuid4()}',
    payload={
      'category': 'person',
      'object': {
        'id': identity,
        'category': 'person',
        'metadata': metadata,
      },
    },
  )


@pytestmark_integration
def test_attribute_query_matches_personattr_and_an_unlisted_key():
  deployment = f'attr-{uuid.uuid4().hex[:8]}'
  os.environ['SCENE_METADATA_DEPLOYMENT_ID'] = deployment
  db = Database()
  db.open()
  store = EventStore(db)
  person_a = _person_event(
    deployment,
    'person-a',
    {
      'is_male': {
        'label': 'male',
        'model_name': 'person-attributes-recognition-crossroad-0238',
        'confidence': 0.93,
      },
      'has_backpack': {
        'label': 'true',
        'model_name': 'person-attributes-recognition-crossroad-0238',
        'confidence': 0.81,
      },
    },
    datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
  )
  person_b = _person_event(
    deployment,
    'person-b',
    {
      'is_male': {
        'label': 'female',
        'model_name': 'person-attributes-recognition-crossroad-0238',
        'confidence': 0.88,
      },
      'scarf_color': {'label': 'crimson', 'confidence': 0.42},
    },
    datetime(2026, 6, 1, 12, 1, tzinfo=timezone.utc),
  )
  assert store.insert_events([person_a, person_b]) == 2

  males = store.query_events(deployment_id=deployment, attributes={'is_male': 'male'})
  assert [row['identity_id'] for row in males] == ['person-a']

  scarves = store.query_events(
    deployment_id=deployment, attributes={'scarf_color': 'crimson'})
  assert [row['identity_id'] for row in scarves] == ['person-b']

  both = store.query_events(
    deployment_id=deployment,
    attributes={'is_male': 'female', 'scarf_color': 'crimson'},
  )
  assert [row['identity_id'] for row in both] == ['person-b']

  assert store.query_events(
    deployment_id=deployment, attributes={'scarf_color': 'blue'}) == []
  assert store.query_events(
    deployment_id=deployment, attributes={'has_backpack': 'false'}) == []

  client = TestClient(create_app(db))
  response = client.post('/v1/events/query', json={
    'attributes': {'has_backpack': 'true', 'is_male': 'male'},
  })
  assert response.status_code == 200
  body = response.json()
  assert body['count'] == 1
  assert body['events'][0]['identity_id'] == 'person-a'

  rejected = client.post('/v1/events/query', json={'attributes': {'': 'male'}})
  assert rejected.status_code == 422
  db.close()
