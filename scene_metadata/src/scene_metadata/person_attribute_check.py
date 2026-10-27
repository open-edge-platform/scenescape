# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compare person-attribute model output with the log, the graph, and MCP.

Lab_000 has no appearance labels, so this check does not use that dataset.
It downloads person-attributes-recognition-crossroad-0238 when needed, scores
two fixed frames, stores that metadata, and requires MCP to return the same
label, model name, and confidence. The weights are not part of the git tree.

On a machine with internet, Timescale, numpy, and OpenVINO:

  pip install 'openvino==2025.3.0' numpy
  export SCENE_METADATA_DATABASE_URL=postgresql://scenescape:scenescape@127.0.0.1:5432/scene_metadata
  PYTHONPATH=scene_common/src:scene_metadata/src python3 -m scene_metadata.person_attribute_check
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import threading
import time

_SCENE_COMMON_SRC = Path(__file__).resolve().parents[3] / 'scene_common' / 'src'
if (_SCENE_COMMON_SRC / 'scene_common' / 'log.py').is_file():
  _location = str(_SCENE_COMMON_SRC)
  if _location not in sys.path:
    sys.path.insert(0, _location)

from scene_metadata.db import Database
from scene_metadata.envelope import EventEnvelope
from scene_metadata.person_attributes import (
  ATTRIBUTE_NAMES,
  MODEL_NAME,
  assert_same_metadata,
  ensure_model,
  recognize_frames,
  sample_frames,
)
from scene_metadata.query_app import create_app
from scene_metadata.store import EventStore

SCENE_ID = 'person-attributes'
EPOCH = datetime(2026, 6, 1, tzinfo=timezone.utc)
DEFAULT_DEPLOYMENT = 'person-attributes-check'


def observation_events(
  identity: str,
  metadata: dict,
  deployment_id: str,
  when: datetime,
) -> list[EventEnvelope]:
  """Store the model object on the attribute event and the track start."""
  shared = {
    'occurred_at': when,
    'deployment_id': deployment_id,
    'scene_id': SCENE_ID,
    'identity_id': identity,
    'track_id': identity,
  }
  return [
    EventEnvelope(
      event_type='attribute_observed',
      source_topic=f'personattr/attribute/{identity}',
      source_message_id=f'attr-{identity}',
      payload={'metadata': metadata},
      **shared,
    ),
    EventEnvelope(
      event_type='track_started',
      source_topic=f'personattr/track/{identity}',
      source_message_id=f'track-start-{identity}',
      payload={'metadata': metadata},
      **shared,
    ),
  ]


def replace_observations(db: Database, deployment_id: str, by_identity: dict) -> int:
  """Replace one deployment with the current model metadata."""
  store = EventStore(db)
  with db.connection() as conn:
    conn.execute(
      'DELETE FROM scenescape_graph_edges WHERE deployment_id = %s', (deployment_id,))
    conn.execute(
      'DELETE FROM scenescape_events WHERE deployment_id = %s', (deployment_id,))
    conn.commit()
  events = []
  for index, identity in enumerate(sorted(by_identity)):
    events.extend(observation_events(
      identity,
      by_identity[identity],
      deployment_id,
      EPOCH + timedelta(seconds=index),
    ))
  inserted = store.insert_events(events)
  if inserted != len(events):
    raise AssertionError(f'inserted {inserted} events, expected {len(events)}')
  return inserted


def graph_metadata(rows: list[dict]) -> dict[str, dict]:
  """Drop graph-only fields so the remainder is the model object."""
  return {
    row['name']: {
      'label': row.get('label'),
      'model_name': row.get('model_name'),
      'confidence': row.get('confidence'),
    }
    for row in rows
  }


def _event_metadata(row: dict) -> dict:
  return (row.get('payload') or {}).get('metadata') or {}


def _brief(metadata: dict) -> str:
  """One line of label and confidence taken from the dict being reported."""
  body = ' '.join(
    f"{name}={item['label']}:{item['confidence']:.8g}" for name, item in metadata.items())
  model = next(iter(metadata.values())).get('model_name')
  return f'{body} model={model}'


def _labels_that_split(expected: dict) -> tuple[str, dict[str, list[str]]]:
  for name in ATTRIBUTE_NAMES:
    groups: dict[str, list[str]] = {}
    for identity in sorted(expected):
      groups.setdefault(expected[identity][name]['label'], []).append(identity)
    if len(groups) > 1:
      return name, {label: owners for label, owners in groups.items()}
  raise AssertionError(f'{MODEL_NAME} gave both frames the same label on every head')


def _unanimous(expected: dict) -> tuple[str, str] | None:
  for name in ATTRIBUTE_NAMES:
    labels = {item[name]['label'] for item in expected.values()}
    if len(labels) == 1:
      return name, next(iter(labels))
  return None


def _unique_pair(expected: dict) -> tuple[dict[str, str], list[str]] | None:
  left, right = ATTRIBUTE_NAMES[0], ATTRIBUTE_NAMES[1]
  for identity, metadata in expected.items():
    chosen = {left: metadata[left]['label'], right: metadata[right]['label']}
    owners = sorted(
      other for other, other_meta in expected.items()
      if other_meta[left]['label'] == chosen[left] and other_meta[right]['label'] == chosen[right]
    )
    if owners == [identity]:
      return chosen, owners
  return None


def _filter_lines(fetch_ids, expected: dict) -> list[str]:
  lines = []
  name, groups = _labels_that_split(expected)
  for label, owners in groups.items():
    got = fetch_ids({name: label}, ['attribute_observed'])
    if got != owners:
      raise AssertionError(f'{name}={label}: got {got}, want {owners}')
    lines.append(f'{name}={label} -> {got}')
  shared = _unanimous(expected)
  if shared is not None:
    attr, label = shared
    opposite = 'false' if label == 'true' else 'true'
    got = fetch_ids({attr: opposite}, ['attribute_observed'])
    if got:
      raise AssertionError(f'{attr}={opposite} returned {got}')
    lines.append(f'{attr}={opposite} -> []')
  pair = _unique_pair(expected)
  if pair is not None:
    chosen, owners = pair
    got = fetch_ids(chosen, ['attribute_observed'])
    if got != owners:
      raise AssertionError(f'{chosen}: got {got}, want {owners}')
    lines.append(f'{chosen} -> {got}')
  return lines


def assert_model_roundtrip(fetch_rows, fetch_ids, fetch_graph, expected: dict) -> list[str]:
  """MCP and HTTP reads must echo the model metadata that was stored."""
  lines = []
  for identity, metadata in sorted(expected.items()):
    for event_type in ('attribute_observed', 'track_started'):
      rows = fetch_rows(identity, event_type)
      if len(rows) != 1:
        raise AssertionError(f'{identity} {event_type}: expected 1 row, got {len(rows)}')
      returned = _event_metadata(rows[0])
      assert_same_metadata(metadata, returned, f'{identity} {event_type}')
      lines.append(f'{event_type} {identity} {_brief(returned)}')
    projected = graph_metadata(fetch_graph(identity))
    assert_same_metadata(metadata, projected, f'{identity} graph')
    lines.append(f'graph {identity} {_brief(projected)}')
  lines.extend(_filter_lines(fetch_ids, expected))
  return lines


def _wait_for_server(server, timeout: float) -> None:
  deadline = time.time() + timeout
  while not getattr(server, 'started', False):
    if time.time() > deadline:
      raise RuntimeError('scene metadata HTTP server did not start')
    time.sleep(0.05)


def serve_and_check(db: Database, deployment_id: str, expected: dict, port: int) -> list[str]:
  """Start the HTTP API and call the MCP tool functions against it."""
  import uvicorn

  from scene_metadata.mcp_server import identity_attributes, query_events

  os.environ['SCENE_METADATA_DEPLOYMENT_ID'] = deployment_id
  os.environ['SCENE_METADATA_API_URL'] = f'http://127.0.0.1:{port}'
  config = uvicorn.Config(create_app(db), host='127.0.0.1', port=port, log_level='warning')
  server = uvicorn.Server(config)
  thread = threading.Thread(target=server.run, name='person-attribute-check', daemon=True)
  thread.start()
  try:
    _wait_for_server(server, 20)

    def fetch_rows(identity, event_type):
      payload = json.loads(query_events(
        scene_id=SCENE_ID,
        identity_id=identity,
        event_types=[event_type],
        limit=20,
      ))
      return payload['events']

    def fetch_ids(attributes, event_types):
      payload = json.loads(query_events(
        scene_id=SCENE_ID,
        attributes=attributes,
        event_types=event_types,
        limit=20,
      ))
      return sorted({row['identity_id'] for row in payload['events']})

    def fetch_graph(identity):
      payload = json.loads(identity_attributes(identity))
      return payload['attributes']

    return assert_model_roundtrip(fetch_rows, fetch_ids, fetch_graph, expected)
  finally:
    server.should_exit = True
    thread.join(timeout=5)


def main(argv: list[str] | None = None) -> int:
  """Score two frames and require MCP to return those labels and confidences."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--model-dir', type=Path, default=None)
  parser.add_argument('--deployment-id', default=DEFAULT_DEPLOYMENT)
  parser.add_argument('--port', type=int, default=8765)
  args = parser.parse_args(argv)
  if args.model_dir is not None:
    os.environ['PERSON_ATTR_MODEL_DIR'] = str(args.model_dir)
  xml_path = ensure_model()
  print(f'Model: {xml_path}')
  print(f'{MODEL_NAME} weights are downloaded on demand and are not in git.')
  expected = recognize_frames(sample_frames(), xml_path)
  for identity, metadata in sorted(expected.items()):
    print(f'model {identity} {_brief(metadata)}')
  db = Database()
  db.open()
  try:
    inserted = replace_observations(db, args.deployment_id, expected)
    print(f'Inserted {inserted} events into deployment {args.deployment_id}')
    for line in serve_and_check(db, args.deployment_id, expected, args.port):
      print(line)
  finally:
    db.close()
  print('MCP returned the labels and confidences produced by the model.')
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
