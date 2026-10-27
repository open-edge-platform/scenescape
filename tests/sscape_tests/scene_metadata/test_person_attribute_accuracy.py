# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Model scores, not dataset facts, are what the attribute API must return."""

import json
import os
from pathlib import Path
import uuid

import pytest
from fastapi.testclient import TestClient

from scene_metadata.person_attributes import (
  MODEL_NAME,
  assert_same_metadata,
  metadata_from_scores,
  model_xml,
  recognize_frames,
  sample_frames,
)
from scene_metadata.person_attribute_check import (
  SCENE_ID,
  assert_model_roundtrip,
  replace_observations,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
LOADER = REPO_ROOT / 'scene_metadata' / 'src' / 'scene_metadata' / 'physicalai_loader.py'
QUERY_SOURCES = (
  'attributes.py',
  'store.py',
  'query_app.py',
  'mcp_server.py',
  'projection.py',
)

pytestmark_db = pytest.mark.skipif(
  not os.environ.get('SCENE_METADATA_DATABASE_URL'),
  reason='SCENE_METADATA_DATABASE_URL required',
)


def test_scores_above_one_half_are_present():
  """The model README treats a head as present only when the score is above 0.5."""
  scores = [0.5, 0.5000001, 0.0, 1.0, 0.49, 0.51, 0.2]
  meta = metadata_from_scores(scores)
  assert meta['is_male'] == {
    'label': 'false', 'model_name': MODEL_NAME, 'confidence': 0.5}
  assert meta['has_bag']['label'] == 'true'
  assert meta['has_hat']['label'] == 'false'
  assert meta['has_longsleeves']['confidence'] == 1.0
  assert meta['has_longpants']['label'] == 'false'
  assert meta['has_longhair']['label'] == 'true'
  assert meta['has_coat_jacket']['label'] == 'false'
  assert set(meta) == {
    'is_male', 'has_bag', 'has_hat', 'has_longsleeves',
    'has_longpants', 'has_longhair', 'has_coat_jacket',
  }


def test_score_count_must_match_the_model_heads():
  with pytest.raises(ValueError):
    metadata_from_scores([0.2, 0.8])


def test_json_round_trip_keeps_model_confidence():
  expected = metadata_from_scores([0.2508544921875, 0.517822265625, 0.0, 0.77, 0.88, 0.1, 0.9])
  assert_same_metadata(expected, json.loads(json.dumps(expected)), 'json')


def test_changed_confidence_is_not_the_model_output():
  expected = metadata_from_scores([0.2, 0.8, 0.1, 0.1, 0.1, 0.1, 0.1])
  actual = json.loads(json.dumps(expected))
  actual['is_male']['confidence'] = 1.0
  with pytest.raises(AssertionError, match='confidence'):
    assert_same_metadata(expected, actual, 'mcp')


def test_loader_does_not_invent_dataset_attributes():
  """Lab_000 geometry is not an appearance attribute."""
  source = LOADER.read_text(encoding='utf-8')
  assert 'attribute_observed' not in source
  assert 'north_entries' not in source
  assert 'physicalai-ground-truth' not in source


def test_query_modules_do_not_name_model_heads():
  root = REPO_ROOT / 'scene_metadata' / 'src' / 'scene_metadata'
  source = '\n'.join((root / name).read_text(encoding='utf-8') for name in QUERY_SOURCES)
  assert 'is_male' not in source
  assert 'has_bag' not in source
  assert 'has_longhair' not in source


def _xml_or_skip() -> Path:
  pytest.importorskip('openvino')
  pytest.importorskip('numpy')
  xml = model_xml()
  if xml is None:
    pytest.skip('set PERSON_ATTR_MODEL_DIR or run person_attribute_check to download the IR')
  return xml


@pytestmark_db
def test_stored_events_and_graph_match_the_model():
  """HTTP checks the same reads the MCP tools call. Expectations come from recognize."""
  from scene_metadata.db import Database
  from scene_metadata.query_app import create_app

  xml = _xml_or_skip()
  expected = recognize_frames(sample_frames(), xml)
  deployment = f'attr-model-{uuid.uuid4().hex[:8]}'
  os.environ['SCENE_METADATA_DEPLOYMENT_ID'] = deployment
  db = Database()
  db.open()
  replace_observations(db, deployment, expected)
  client = TestClient(create_app(db))

  def fetch_rows(identity, event_type):
    response = client.post('/v1/events/query', json={
      'scene_id': SCENE_ID,
      'identity_id': identity,
      'event_types': [event_type],
      'limit': 20,
    })
    assert response.status_code == 200
    return response.json()['events']

  def fetch_ids(attributes, event_types):
    response = client.post('/v1/events/query', json={
      'scene_id': SCENE_ID,
      'attributes': attributes,
      'event_types': event_types,
      'limit': 20,
    })
    assert response.status_code == 200
    return sorted({row['identity_id'] for row in response.json()['events']})

  def fetch_graph(identity):
    response = client.get(f'/v1/graph/identities/{identity}/attributes')
    assert response.status_code == 200
    return response.json()['attributes']

  lines = assert_model_roundtrip(fetch_rows, fetch_ids, fetch_graph, expected)
  assert lines
  assert any(line.startswith('graph ') for line in lines)
  db.close()
