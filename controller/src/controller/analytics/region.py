# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log
from scene_common.geometry import getRegionEvents
from scene_common.timestamp import get_epoch_time, get_iso_time

from controller.analytics.tripwire import DEBOUNCE_DELAY, MIN_FRAMES_FOR_RELIABLE_TRACK


def update_region_events(
    detection_type,
    regions,
    now,
    now_str,
    cur_objects,
    events,
    use_tracker,
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
    cur_objects:       List of AnalyticsObject for this frame.
    events:            Mutable dict; region and count events are appended.
    use_tracker:       When True the frameCount reliability gate is applied.
    is_intersecting_fn: Optional callable(obj, region) -> bool for 3-D mesh
                       intersection fallback in addition to point-in-region.

  Returns:
    Set of region keys that were updated this frame.
  """
  updated = set()

  reliable_objects = [
    obj for obj in cur_objects
    if obj.frameCount > MIN_FRAMES_FOR_RELIABLE_TRACK or not use_tracker
  ]

  object_locations = [obj.sceneLoc for obj in reliable_objects]
  objects_within_region = getRegionEvents(regions, object_locations)

  for key, region in regions.items():
    matched_indices = set(objects_within_region.get(key, []))
    if is_intersecting_fn is not None:
      for obj_idx, obj in enumerate(reliable_objects):
        if obj_idx not in matched_indices and is_intersecting_fn(obj, region):
          matched_indices.add(obj_idx)

    objects = [reliable_objects[i] for i in sorted(matched_indices)]
    regionObjects = region.objects.get(detection_type, [])

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

    emit_region_event = (len(new) or len(old)) and now - region.when > DEBOUNCE_DELAY
    if emit_region_event:
      log.debug("REGION EVENT", key, now_str, regionObjects, len(objects))
      entered = []
      for obj in objects:
        if obj.gid in new and key in obj.chain_data.regions:
          entered.append(obj)
      if not hasattr(region, 'entered'):
        region.entered = {}
      region.entered[detection_type] = entered

      exited = []
      for obj in regionObjects:
        if obj.gid in old:
          if key in obj.chain_data.regions:
            entered = get_epoch_time(obj.chain_data.regions[key]['entered'])
            dwell = now - entered
            exited.append((obj, dwell))

      if not hasattr(region, 'exited'):
        region.exited = {}
      region.exited[detection_type] = exited

      region.objects[detection_type] = objects
      updated.add(key)
      region.when = now
      if 'objects' not in events:
        events['objects'] = []
      events['objects'].append((key, region))
      if len(cur) != len(prev):
        if 'count' not in events:
          events['count'] = []
        events['count'].append((key, region))

      # Clean up exited objects only after an exit event can be emitted,
      # so entered timestamps remain available for dwell-time calculation.
      for obj in regionObjects:
        if obj.gid in old:
          with obj.chain_data._lock:
            obj.chain_data.regions.pop(key, None)

            if region.singleton_type is not None:
              obj.chain_data.active_sensors.discard(key)

              if region.singleton_type == "environmental":
                obj.chain_data.env_sensor_state.pop(key, None)

              # Attribute sensors: keep event history (data persists after exit)
              # attr_sensor_events[key] intentionally not removed

  return updated
