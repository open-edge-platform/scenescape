# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log
from scene_common.geometry import getRegionEvents
from scene_common.timestamp import get_epoch_time, get_iso_time

from analytics.state import DEBOUNCE_DELAY


def update_region_events(
    detection_type,
    regions,
    now,
    now_str,
    cur_objects,
    events,
    state_store,
    is_intersecting_fn=None,
):
  """Compute region enter/exit events and update per-object chain_data state.

  This function handles both geometry regions and singleton sensor regions
  (distinguished by region.singleton_type being non-None).

  Args:
    detection_type:    Detection category string (e.g. 'person').
    regions:           Dict of {key: Region} — may be scene.regions or
                       scene.sensors.
    now:               Current epoch timestamp (float).
    now_str:           ISO-8601 string of now.
    cur_objects:       List of AnalyticsObject for this frame.  The caller
                       is responsible for pre-filtering by reliability if
                       needed (e.g. frameCount gate when using a tracker).
    events:            Mutable dict; region and count events are appended.
    state_store:       AnalyticsStateStore that owns per-region analytics state.
    is_intersecting_fn: Optional callable(obj, region) -> bool for 3-D mesh
                       intersection fallback in addition to point-in-region.

  Returns:
    Set of region keys that were updated this frame.
  """
  updated = set()

  reliable_objects = cur_objects

  object_locations = [obj.sceneLoc for obj in reliable_objects]
  objects_within_region = getRegionEvents(regions, object_locations)

  for key, region in regions.items():
    matched_indices = set(objects_within_region.get(key, []))
    if is_intersecting_fn is not None:
      for obj_idx, obj in enumerate(reliable_objects):
        if obj_idx not in matched_indices and is_intersecting_fn(obj, region):
          matched_indices.add(obj_idx)

    objects = [reliable_objects[i] for i in sorted(matched_indices)]
    rstate = state_store.region(key)
    regionObjects = rstate.objects.get(detection_type, [])

    cur = set(x.gid for x in objects)
    prev = set(x.gid for x in regionObjects)
    new = cur - prev
    old = prev - cur
    newObjects = [x for x in objects if x.gid in new]

    # Entry initialization for new objects
    for obj in newObjects:
      if key not in obj.chain_data.regions:
        obj.chain_data.regions[key] = {'entered': now_str}
        updated.add(key)

    # For all singleton sensors, handle entry tracking
    if region.singleton_type is not None:
      for obj in newObjects:
        obj.chain_data.active_sensors.add(key)

        if region.singleton_type == "environmental":
          with obj.chain_data._lock:
            if (hasattr(region, 'value') and
                hasattr(region, 'lastWhen') and
                region.value is not None and
                region.lastWhen is not None):
              ts_str = get_iso_time(region.lastWhen)
              obj.chain_data.env_sensor_state[key] = {
                'readings': [(ts_str, float(region.value))]
              }
            else:
              obj.chain_data.env_sensor_state[key] = {
                'readings': []
              }

        elif region.singleton_type == "attribute":
          with obj.chain_data._lock:
            if key not in obj.chain_data.attr_sensor_events:
              obj.chain_data.attr_sensor_events[key] = []

    emit_region_event = (len(new) or len(old)) and now - rstate.when > DEBOUNCE_DELAY
    if emit_region_event:
      log.debug("REGION EVENT", key, now_str, regionObjects, len(objects))
      entered = []
      for obj in objects:
        if obj.gid in new and key in obj.chain_data.regions:
          entered.append(obj)
      rstate.entered[detection_type] = entered

      exited = []
      for obj in regionObjects:
        if obj.gid in old:
          if key in obj.chain_data.regions:
            entered = get_epoch_time(obj.chain_data.regions[key]['entered'])
            dwell = now - entered
            exited.append((obj, dwell))

      rstate.exited[detection_type] = exited

      rstate.objects[detection_type] = list(objects)
      updated.add(key)
      rstate.when = now
      if 'objects' not in events:
        events['objects'] = []
      events['objects'].append((key, region))
      if len(cur) != len(prev):
        if 'count' not in events:
          events['count'] = []
        events['count'].append((key, region))

      # Clean up exited objects only after an exit event can be emitted,
      # so entered timestamps remain available for dwell-time calculation.
      # NOTE: env_sensor_state[key] is intentionally NOT cleared here — it must
      # remain available when publish_events serialises the exited objects.
      # It is cleared in event_publisher._build_exited_objs_list after serialisation.
      for obj in regionObjects:
        if obj.gid in old:
          with obj.chain_data._lock:
            obj.chain_data.regions.pop(key, None)

            if region.singleton_type is not None:
              obj.chain_data.active_sensors.discard(key)

              # Attribute sensors: keep event history (data persists after exit)
              # attr_sensor_events[key] intentionally not removed

  return updated
