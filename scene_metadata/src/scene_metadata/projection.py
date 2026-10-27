# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""SQL graph edge projection from canonical events."""

from datetime import datetime
from typing import Any, Iterable

from psycopg import Connection
from psycopg.types.json import Json

from scene_metadata.envelope import EventEnvelope


def project_edges(conn: Connection, event: EventEnvelope) -> None:
  """Insert graph edges implied by one stored event."""
  edges = list(_edges_for_event(event))
  if not edges:
    return
  sql = """
    INSERT INTO scenescape_graph_edges (
      deployment_id, relation, src_kind, src_id, dst_kind, dst_id,
      scene_id, valid_from, valid_to, payload
    ) VALUES (
      %(deployment_id)s, %(relation)s, %(src_kind)s, %(src_id)s,
      %(dst_kind)s, %(dst_id)s, %(scene_id)s, %(valid_from)s, %(valid_to)s,
      %(payload)s::jsonb
    )
  """
  for edge in edges:
    conn.execute(sql, edge)


def _entity(event: EventEnvelope) -> tuple[str, str] | None:
  if event.identity_id:
    return 'identity', event.identity_id
  if event.track_id:
    return 'track', event.track_id
  return None


def _edges_for_event(event: EventEnvelope) -> Iterable[dict[str, Any]]:
  valid_from = event.occurred_at
  base = {
    'deployment_id': event.deployment_id,
    'scene_id': event.scene_id,
    'valid_from': valid_from,
    'valid_to': None,
    'payload': Json({}),
  }
  entity = _entity(event)
  if entity is None:
    return

  src_kind, src_id = entity
  if event.event_type == 'track_started' and event.scene_id:
    yield {
      **base,
      'relation': 'SEEN_IN',
      'src_kind': src_kind,
      'src_id': src_id,
      'dst_kind': 'scene',
      'dst_id': event.scene_id,
    }
  if event.event_type == 'region_enter' and event.region_id:
    yield {
      **base,
      'relation': 'ENTERED',
      'src_kind': src_kind,
      'src_id': src_id,
      'dst_kind': 'region',
      'dst_id': event.region_id,
    }
  if event.event_type == 'region_exit' and event.region_id:
    yield {
      **base,
      'relation': 'EXITED',
      'src_kind': src_kind,
      'src_id': src_id,
      'dst_kind': 'region',
      'dst_id': event.region_id,
      'valid_to': valid_from,
    }
  if event.event_type == 'tripwire_cross' and event.tripwire_id:
    yield {
      **base,
      'relation': 'CROSSED',
      'src_kind': src_kind,
      'src_id': src_id,
      'dst_kind': 'tripwire',
      'dst_id': event.tripwire_id,
      'payload': Json({'event_type': event.event_type}),
    }
  yield from _attribute_edges(event, base, src_kind, src_id)


def _attribute_edges(event, base, src_kind: str, src_id: str):
  """Project every metadata key. New attribute names need no edge schema change."""
  if event.event_type != 'attribute_observed':
    return
  metadata = (event.payload or {}).get('metadata')
  if not isinstance(metadata, dict):
    return
  for name, value in metadata.items():
    if name == 'reid' or not isinstance(value, dict) or not isinstance(value.get('label'), str):
      continue
    label = value['label']
    if not label:
      continue
    yield {
      **base,
      'relation': 'HAS_ATTRIBUTE',
      'src_kind': src_kind,
      'src_id': src_id,
      'dst_kind': 'attribute',
      'dst_id': f'{name}={label}',
      'payload': Json({
        'name': name,
        'label': label,
        'model_name': value.get('model_name'),
        'confidence': value.get('confidence'),
      }),
    }
