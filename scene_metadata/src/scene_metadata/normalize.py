# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Convert MQTT payloads into EventEnvelope lists."""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Optional

from scene_metadata.envelope import EventEnvelope
from scene_metadata.topics import AnalyticsEventTopic, SceneTopic


def _parse_time(value: Any) -> datetime:
  if isinstance(value, datetime):
    if value.tzinfo is None:
      return value.replace(tzinfo=timezone.utc)
    return value
  if isinstance(value, str):
    text = value.replace('Z', '+00:00')
    return datetime.fromisoformat(text)
  if isinstance(value, (int, float)):
    return datetime.fromtimestamp(float(value), tz=timezone.utc)
  return datetime.now(tz=timezone.utc)


def _message_id(topic: str, payload: dict[str, Any]) -> str:
  digest = hashlib.sha256()
  digest.update(topic.encode('utf-8'))
  digest.update(json.dumps(payload, sort_keys=True, default=str).encode('utf-8'))
  return digest.hexdigest()


def _object_identity(obj: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
  track_id = obj.get('id')
  identity_id = obj.get('gid') or obj.get('global_id') or track_id
  if track_id == identity_id:
    track_id = None
  return track_id, identity_id


def track_lifecycle_events(
  *,
  topic: SceneTopic,
  payload: dict[str, Any],
  previous_ids: set[str],
  deployment_id: str,
) -> tuple[list[EventEnvelope], set[str]]:
  """Derive track_started / track_lost from a scene snapshot."""
  objects = payload.get('objects') or []
  current_ids = {
    obj['id'] for obj in objects if isinstance(obj, dict) and obj.get('id')
  }
  started = current_ids - previous_ids
  lost = previous_ids - current_ids
  when = _parse_time(payload.get('timestamp') or payload.get('when'))
  source_topic = f'scenescape/data/scene/{topic.scene_id}/{topic.category}'
  message_id = _message_id(source_topic, payload)
  events: list[EventEnvelope] = []

  for active_id in sorted(started):
    obj = next((o for o in objects if o.get('id') == active_id), {})
    local_track_id, identity_id = _object_identity(obj if isinstance(obj, dict) else {})
    if local_track_id is None and identity_id is None:
      local_track_id = active_id
    events.append(EventEnvelope(
      occurred_at=when,
      event_type='track_started',
      source_topic=source_topic,
      deployment_id=deployment_id,
      scene_id=topic.scene_id,
      track_id=local_track_id or active_id,
      identity_id=identity_id or active_id,
      source_message_id=f'{message_id}:start:{active_id}',
      payload={'category': topic.category, 'object': obj},
    ))

  for active_id in sorted(lost):
    events.append(EventEnvelope(
      occurred_at=when,
      event_type='track_lost',
      source_topic=source_topic,
      deployment_id=deployment_id,
      scene_id=topic.scene_id,
      track_id=active_id,
      identity_id=active_id,
      source_message_id=f'{message_id}:lost:{active_id}',
      payload={'category': topic.category},
    ))

  return events, current_ids


def analytics_event_envelopes(
  *,
  topic: AnalyticsEventTopic,
  payload: dict[str, Any],
  deployment_id: str,
) -> list[EventEnvelope]:
  """Normalize region/tripwire MQTT analytics events (full fidelity)."""
  when = _parse_time(payload.get('timestamp'))
  source_topic = (
    f'scenescape/event/{topic.region_type}/{topic.scene_id}/'
    f'{topic.resource_id}/{topic.event_type}'
  )
  message_id = _message_id(source_topic, payload)
  scene_id = payload.get('scene_id') or topic.scene_id
  events: list[EventEnvelope] = []

  if topic.region_type == 'region':
    events.extend(_region_events(
      topic=topic,
      payload=payload,
      when=when,
      scene_id=scene_id,
      source_topic=source_topic,
      message_id=message_id,
      deployment_id=deployment_id,
    ))
  elif topic.region_type == 'tripwire':
    events.extend(_tripwire_events(
      topic=topic,
      payload=payload,
      when=when,
      scene_id=scene_id,
      source_topic=source_topic,
      message_id=message_id,
      deployment_id=deployment_id,
    ))
  return events


def _region_events(
  *,
  topic: AnalyticsEventTopic,
  payload: dict[str, Any],
  when: datetime,
  scene_id: str,
  source_topic: str,
  message_id: str,
  deployment_id: str,
) -> Iterable[EventEnvelope]:
  region_id = payload.get('region_id') or topic.resource_id
  base = {
    'deployment_id': deployment_id,
    'scene_id': scene_id,
    'region_id': region_id,
    'source_topic': source_topic,
    'payload': payload,
  }

  if topic.event_type == 'count':
    for idx, obj in enumerate(payload.get('entered') or []):
      if not isinstance(obj, dict):
        continue
      track_id, identity_id = _object_identity(obj)
      yield EventEnvelope(
        occurred_at=when,
        event_type='region_enter',
        source_message_id=f'{message_id}:enter:{idx}:{identity_id or track_id}',
        track_id=track_id,
        identity_id=identity_id,
        **base,
      )
    for idx, obj in enumerate(payload.get('exited') or []):
      if not isinstance(obj, dict):
        continue
      track_id, identity_id = _object_identity(obj)
      yield EventEnvelope(
        occurred_at=when,
        event_type='region_exit',
        source_message_id=f'{message_id}:exit:{idx}:{identity_id or track_id}',
        track_id=track_id,
        identity_id=identity_id,
        **base,
      )
    yield EventEnvelope(
      occurred_at=when,
      event_type='region_count',
      source_message_id=f'{message_id}:count',
      **base,
    )
  elif topic.event_type == 'objects':
    yield EventEnvelope(
      occurred_at=when,
      event_type='region_objects',
      source_message_id=message_id,
      **base,
    )


def _tripwire_events(
  *,
  topic: AnalyticsEventTopic,
  payload: dict[str, Any],
  when: datetime,
  scene_id: str,
  source_topic: str,
  message_id: str,
  deployment_id: str,
) -> Iterable[EventEnvelope]:
  tripwire_id = payload.get('tripwire_id') or topic.resource_id
  objects = payload.get('objects') or []
  if not isinstance(objects, list):
    objects = [objects]
  for idx, obj in enumerate(objects):
    if not isinstance(obj, dict):
      continue
    track_id, identity_id = _object_identity(obj)
    yield EventEnvelope(
      occurred_at=when,
      event_type='tripwire_cross',
      deployment_id=deployment_id,
      scene_id=scene_id,
      tripwire_id=tripwire_id,
      track_id=track_id,
      identity_id=identity_id,
      source_topic=source_topic,
      source_message_id=f'{message_id}:cross:{idx}:{identity_id or track_id}',
      payload={'object': obj, 'raw': payload},
    )
