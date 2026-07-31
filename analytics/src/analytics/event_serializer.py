# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Lightweight serializer for analytics event payloads.

Converts ``AnalyticsObject`` / ``TripwireEvent`` instances into plain dicts
suitable for MQTT event messages.  Uses only fields available on analytics
objects — no tracker-specific attributes (camera bounds, reid_state,
previous_ids_chain, asset_scale) and no scene-controller concerns (LLA
conversion, camera pose projection).

Public API
----------
serialize_for_event(obj, include_sensors, include_region_dwell, current_time)
    Serialise a single ``AnalyticsObject`` or ``TripwireEvent`` to a dict.

build_objects_dict(objects, include_sensors, include_region_dwell, current_time)
    ``{gid: dict}`` mapping for a collection of objects.

build_objects_list(objects, include_sensors, include_region_dwell, current_time)
    Ordered list of serialised dicts.
"""

import numpy as np

from scene_common.geometry import DEFAULTZ, Point
from scene_common.timestamp import get_epoch_time, get_iso_time

from analytics.tripwire import TripwireEvent


def serialize_for_event(obj, include_sensors=False, include_region_dwell=False, current_time=None):
  """Serialise one ``AnalyticsObject`` or ``TripwireEvent`` into an event payload dict.

  Args:
    obj:                  ``AnalyticsObject`` or ``TripwireEvent``.
    include_sensors:      Include sensor readings/events from ``chain_data``.
    include_region_dwell: Annotate region entries with elapsed dwell time.
    current_time:         Epoch float used for dwell calculation.  Defaults to
                          ``get_epoch_time()`` when *include_region_dwell* is
                          ``True`` and this is ``None``.

  Returns:
    dict with at minimum ``id``, ``type``, ``translation``, ``size``, ``velocity``.
  """
  ao = obj.object if isinstance(obj, TripwireEvent) else obj

  velocity = ao.velocity
  if velocity is None:
    velocity = Point(0, 0, 0)
  if not velocity.is3D:
    velocity = Point(velocity.x, velocity.y, DEFAULTZ)

  obj_dict = dict(ao.info or {})
  obj_dict.update({
    'id': ao.gid,
    'type': ao.category,
    'translation': ao.sceneLoc.asCartesianVector,
    'size': ao.size,
    'velocity': velocity.asCartesianVector,
  })

  if ao.rotation is not None:
    obj_dict['rotation'] = ao.rotation

  # Semantic metadata (age, gender, clothing, etc.) — exclude reid key
  if ao.metadata:
    if 'metadata' not in obj_dict:
      obj_dict['metadata'] = {}
    for key, value in ao.metadata.items():
      if key != 'reid':
        obj_dict['metadata'][key] = value

  # Reid embedding — carry through as metadata for downstream consumers
  reid = ao.reid
  if reid and 'embedding_vector' in reid:
    reid_embedding = reid['embedding_vector']
    if reid_embedding is not None:
      if 'metadata' not in obj_dict:
        obj_dict['metadata'] = {}
      reid_vec = np.asarray(reid_embedding, dtype=np.float32)
      obj_dict['metadata']['reid'] = {
        'embedding_vector': reid_vec.tolist(),
        'embedding_dimensions': int(reid_vec.reshape(-1).shape[0]),
      }
      if 'model_name' in reid:
        obj_dict['metadata']['reid']['model_name'] = reid['model_name']

  if hasattr(ao, 'visibility'):
    obj_dict['visibility'] = ao.visibility

  if hasattr(ao, 'chain_data'):
    chain_data = ao.chain_data
    if len(chain_data.publishedLocations) > 1:
      obj_dict['prev_translation'] = chain_data.publishedLocations[1].asCartesianVector

    if chain_data.regions:
      if include_region_dwell:
        if current_time is None:
          current_time = get_epoch_time()
        obj_dict['regions'] = _build_region_output(chain_data.regions, current_time)
      else:
        obj_dict['regions'] = chain_data.regions

    if include_sensors:
      sensors_output = _build_sensors_output(chain_data)
      if sensors_output:
        obj_dict['sensors'] = sensors_output

    if chain_data.persist:
      obj_dict['persistent_data'] = chain_data.persist

  if hasattr(ao, 'confidence'):
    obj_dict['confidence'] = ao.confidence
  if hasattr(ao, 'similarity'):
    obj_dict['similarity'] = ao.similarity
  if hasattr(ao, 'first_seen'):
    obj_dict['first_seen'] = get_iso_time(ao.first_seen)

  if isinstance(obj, TripwireEvent):
    obj_dict['direction'] = obj.direction

  return obj_dict


def build_objects_dict(objects, include_sensors=False, include_region_dwell=False, current_time=None):
  """Return ``{gid: dict}`` for a collection of objects."""
  result = {}
  for obj in objects:
    d = serialize_for_event(obj, include_sensors, include_region_dwell, current_time)
    result[d['id']] = d
  return result


def build_objects_list(objects, include_sensors=False, include_region_dwell=False, current_time=None):
  """Return an ordered list of serialised dicts."""
  return [
    serialize_for_event(obj, include_sensors, include_region_dwell, current_time)
    for obj in objects
  ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_region_output(regions, current_time):
  serialized = {}
  for region_name, region_data in regions.items():
    entry = dict(region_data)
    entry.pop('entered_epoch', None)
    if 'entered' in region_data:
      entered_epoch = region_data.get('entered_epoch')
      if entered_epoch is None:
        entered_epoch = get_epoch_time(region_data['entered'])
        region_data['entered_epoch'] = entered_epoch
      entry['dwell'] = current_time - entered_epoch
    serialized[region_name] = entry
  return serialized


def _build_sensors_output(chain_data):
  sensors_output = {}

  with chain_data._lock:
    env_state_copy = dict(chain_data.env_sensor_state)
    attr_events_copy = dict(chain_data.attr_sensor_events)

  # Always include environmental sensor keys so consumers know the sensor was active,
  # even when the readings list is temporarily empty.
  for sensor_id, state in env_state_copy.items():
    sensors_output[sensor_id] = {'values': state.get('readings', [])}

  for sensor_id, events in attr_events_copy.items():
    if events:
      sensors_output[sensor_id] = {'values': events}

  return sensors_output
