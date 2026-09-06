# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Analytics event publisher.

Serialises analytics results from ``scene.events`` / ``scene.analytics_state``
and publishes them directly to MQTT via an injected ``publish_fn`` callable.

This module owns the event publication path — SceneController is no longer
responsible for publishing analytics events.

Public API
----------
publish_events(scene, ts_str, publish_fn)
    Serialise and publish all pending analytics events for *scene*, then clear
    the transient event queues.
"""

import orjson

from scene_common import log
from scene_common.geometry import Region, Tripwire
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_epoch_time

from analytics.event_serializer import (
  build_objects_dict,
  build_objects_list,
)


def publish_events(scene, ts_str, publish_fn):
  """Serialise and publish all pending analytics events for *scene*.

  Reads ``scene.events`` and ``scene.analytics_state``, builds MQTT payloads,
  calls ``publish_fn`` for each event, then clears the transient queues.

  Args:
    scene:       Scene instance with ``events``, ``analytics_state``, ``uid``
                 and ``name`` attributes.
    ts_str:      ISO-8601 timestamp string for the current frame.
    publish_fn:  Callable ``(topic: str, payload: bytes) -> None`` — typically
                 ``pubsub.publish``.
  """
  for event_type in scene.events:
    for key, region in scene.events[event_type]:
      etype = None
      metadata = None

      if isinstance(region, Tripwire):
        etype = 'tripwire'
        metadata = region.serialize()
        region_state = scene.analytics_state.tripwire(key)

      elif isinstance(region, Region):
        etype = 'region'
        metadata = region.serialize()
        metadata['fromSensor'] = (region.singleton_type != None)
        region_state = scene.analytics_state.region(key)

      event_data = {
        'timestamp': ts_str,
        'scene_id': scene.uid,
        'scene_name': scene.name,
        etype + '_id': region.uuid,
        etype + '_name': region.name,
      }
      detections_dict, num_objects = _build_all_region_objs_list(region_state, event_data)
      _build_entered_objs_list(region_state, event_data, detections_dict)
      _build_exited_objs_list(region_state, event_data)

      log.debug("EVENT DATA", event_data)
      if hasattr(region, 'value'):
        event_data['value'] = region.value
      event_data['metadata'] = metadata
      if not isinstance(region, Tripwire) or num_objects > 0:
        event_topic = PubSub.formatTopic(PubSub.EVENT,
                                         region_type=etype, event_type=event_type,
                                         scene_id=scene.uid, region_id=region.uuid)
        publish_fn(event_topic, orjson.dumps(event_data, option=orjson.OPT_SERIALIZE_NUMPY))

  _clear_sensor_values_on_exit(scene)

  # Clear per-frame region/tripwire queues after publishing.
  scene.events.pop('objects', None)
  scene.events.pop('count', None)
  return


def _build_all_region_objs_list(region_state, event_data):
  counts = {}
  num_objects = 0
  all_objects = []
  for otype, objects in region_state.objects.items():
    counts[otype] = len(objects)
    num_objects += counts[otype]
    all_objects += objects
  event_data['counts'] = counts
  current_time = get_epoch_time(event_data['timestamp'])
  detections_dict = build_objects_dict(
    all_objects, include_sensors=True,
    include_region_dwell=True, current_time=current_time)
  event_data['objects'] = list(detections_dict.values())
  return detections_dict, num_objects


def _build_entered_objs_list(region_state, event_data, detections_dict):
  entered = getattr(region_state, 'entered', {})
  event_data['entered'] = []
  missing_objs = []
  for entered_list in entered.values():
    for item in entered_list:
      # For sensor value events, objects may not be in detections_dict
      if item.gid in detections_dict:
        event_data['entered'].append(detections_dict[item.gid])
      else:
        missing_objs.append(item)

  # Build any objects not in detections_dict (e.g., from sensor events)
  if missing_objs:
    current_time = get_epoch_time(event_data['timestamp'])
    entered_objs = build_objects_list(
      missing_objs, include_sensors=True,
      include_region_dwell=True, current_time=current_time)
    event_data['entered'].extend(entered_objs)


def _build_exited_objs_list(region_state, event_data):
  exited = getattr(region_state, 'exited', {})
  event_data['exited'] = []
  exited_dict = {}
  for exited_list in exited.values():
    exited_objs = []
    for exited_obj, dwell in exited_list:
      exited_dict[exited_obj.gid] = dwell
      exited_objs.append(exited_obj)
    current_time = get_epoch_time(event_data['timestamp'])
    serialized = build_objects_list(
      exited_objs, include_sensors=True,
      include_region_dwell=True, current_time=current_time)
    exited_data = [{'object': s, 'dwell': exited_dict[s['id']]} for s in serialized]
    event_data['exited'].extend(exited_data)
  return


def _clear_sensor_values_on_exit(scene):
  """Clear region entered/exited arrays and sensor state after events have been published."""
  cleared_keys = set()
  for event_type in scene.events:
    for key, region in scene.events[event_type]:
      if isinstance(region, Tripwire):
        continue
      rstate = scene.analytics_state.region(key)
      # Clear env_sensor_state for exited objects exactly once per key.
      # publish_events may iterate the same key multiple times (once per event
      # type), so we deduplicate to avoid clearing already-empty state.
      if key not in cleared_keys and region.singleton_type == "environmental":
        cleared_keys.add(key)
        for exited_list in rstate.exited.values():
          for exited_obj, _ in exited_list:
            with exited_obj.chain_data._lock:
              exited_obj.chain_data.env_sensor_state.pop(key, None)
      rstate.clear_frame_state()
  return
