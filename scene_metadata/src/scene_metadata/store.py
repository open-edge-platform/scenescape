# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Persist events and run graph projection."""

from typing import Any, Optional

from psycopg.types.json import Json

from scene_metadata.attributes import attribute_clauses, validate_attributes
from scene_metadata.db import Database
from scene_metadata.envelope import EventEnvelope
from scene_metadata.projection import project_edges


class EventStore:
  """Write path for scenescape_events."""

  def __init__(self, database: Database):
    self._db = database

  def insert_events(self, events: list[EventEnvelope]) -> int:
    if not events:
      return 0
    inserted = 0
    with self._db.connection() as conn:
      for event in events:
        if not self._insert_one(conn, event):
          continue
        project_edges(conn, event)
        inserted += 1
      conn.commit()
    return inserted

  def _insert_one(self, conn, event: EventEnvelope) -> bool:
    row = event.as_row()
    row['payload'] = Json(row.get('payload') or {})
    cur = conn.execute(
      """
      INSERT INTO scenescape_events (
        event_id, occurred_at, deployment_id, event_type, scene_id, region_id,
        tripwire_id, track_id, identity_id, camera_id, source_topic,
        source_message_id, payload
      ) VALUES (
        %(event_id)s, %(occurred_at)s, %(deployment_id)s, %(event_type)s,
        %(scene_id)s, %(region_id)s, %(tripwire_id)s, %(track_id)s,
        %(identity_id)s, %(camera_id)s, %(source_topic)s, %(source_message_id)s,
        %(payload)s::jsonb
      )
      ON CONFLICT (occurred_at, deployment_id, source_topic, source_message_id) DO NOTHING
      RETURNING event_id
      """,
      row,
    )
    return cur.fetchone() is not None

  def query_events(
    self,
    *,
    deployment_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    scene_id: Optional[str] = None,
    identity_id: Optional[str] = None,
    region_id: Optional[str] = None,
    tripwire_id: Optional[str] = None,
    event_types: Optional[list[str]] = None,
    attributes: Optional[dict[str, str]] = None,
    limit: int = 200,
  ) -> list[dict[str, Any]]:
    """Return events. ``attributes`` matches any payload key to a label.

    Keys are not an allowlist. classificationPolicy objects (``label`` /
    ``model_name`` / ``confidence``) and scalar values both match.
    """
    clauses = ['deployment_id = %(deployment_id)s']
    params: dict[str, Any] = {'deployment_id': deployment_id, 'limit': limit}
    if start:
      clauses.append('occurred_at >= %(start)s::timestamptz')
      params['start'] = start
    if end:
      clauses.append('occurred_at <= %(end)s::timestamptz')
      params['end'] = end
    if scene_id:
      clauses.append('scene_id = %(scene_id)s')
      params['scene_id'] = scene_id
    if identity_id:
      clauses.append('identity_id = %(identity_id)s')
      params['identity_id'] = identity_id
    if region_id:
      clauses.append('region_id = %(region_id)s')
      params['region_id'] = region_id
    if tripwire_id:
      clauses.append('tripwire_id = %(tripwire_id)s')
      params['tripwire_id'] = tripwire_id
    if event_types:
      clauses.append('event_type = ANY(%(event_types)s)')
      params['event_types'] = event_types
    clauses.extend(attribute_clauses(validate_attributes(attributes), params))

    sql = f"""
      SELECT event_id, occurred_at, ingested_at, event_type, scene_id, region_id,
             tripwire_id, track_id, identity_id, camera_id, source_topic, payload
      FROM scenescape_events
      WHERE {' AND '.join(clauses)}
      ORDER BY occurred_at ASC, source_message_id ASC
      LIMIT %(limit)s
    """
    with self._db.connection() as conn:
      return list(conn.execute(sql, params))

  def identity_timeline(
    self,
    *,
    deployment_id: str,
    identity_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 500,
  ) -> list[dict[str, Any]]:
    """Merge events keyed by global identity or track id (investigator timeline)."""
    clauses = ['deployment_id = %(deployment_id)s']
    params: dict[str, Any] = {
      'deployment_id': deployment_id,
      'identity_id': identity_id,
      'limit': limit,
    }
    clauses.append('(identity_id = %(identity_id)s OR track_id = %(identity_id)s)')
    if start:
      clauses.append('occurred_at >= %(start)s::timestamptz')
      params['start'] = start
    if end:
      clauses.append('occurred_at <= %(end)s::timestamptz')
      params['end'] = end
    sql = f"""
      SELECT event_id, occurred_at, ingested_at, event_type, scene_id, region_id,
             tripwire_id, track_id, identity_id, camera_id, source_topic, payload
      FROM scenescape_events
      WHERE {' AND '.join(clauses)}
      ORDER BY occurred_at ASC, source_message_id ASC
      LIMIT %(limit)s
    """
    with self._db.connection() as conn:
      return list(conn.execute(sql, params))

  def ingest_stats(self, deployment_id: str) -> dict[str, Any]:
    with self._db.connection() as conn:
      row = conn.execute(
        """
        SELECT
          COUNT(*) AS total_events,
          MAX(ingested_at) AS last_ingested_at,
          MAX(occurred_at) AS last_occurred_at,
          AVG(EXTRACT(EPOCH FROM (ingested_at - occurred_at))) AS avg_lag_seconds
        FROM scenescape_events
        WHERE deployment_id = %s
        """,
        (deployment_id,),
      ).fetchone()
    return row or {}
