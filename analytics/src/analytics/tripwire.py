# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log
from scene_common.geometry import getTripwireEvents

from analytics.state import DEBOUNCE_DELAY


class TripwireEvent:
  def __init__(self, object, direction):
    self.object = object
    self.direction = direction
    return


def update_tripwire_events(detection_type, tripwires, now, cur_objects, events, state_store):
  """Detect tripwire crossings and append events to the shared events dict.

  The caller is responsible for pre-filtering *cur_objects* by reliability
  (e.g. frameCount gate) if needed.  Objects with fewer than two published
  locations are skipped here as they cannot produce a crossing segment.

  Args:
    detection_type: Detection category string (e.g. 'person').
    tripwires:      Dict of {key: Tripwire} from the scene.
    now:            Current epoch timestamp (float).
    cur_objects:    List of AnalyticsObject for this frame.
    events:         Mutable dict; crossing events are appended under 'objects'.
    state_store:    AnalyticsStateStore that owns per-tripwire analytics state.
  """
  reliable_objects = [
    obj for obj in cur_objects
    if len(obj.chain_data.publishedLocations) > 1
  ]

  object_locations = [
    obj.chain_data.publishedLocations[:2] for obj in reliable_objects
  ]

  crossing_events = getTripwireEvents(tripwires, object_locations)

  for key, tripwire in tripwires.items():
    tstate = state_store.tripwire(key)
    event_matches = crossing_events.get(key, [])
    previous_objects = tstate.objects.get(detection_type, [])
    crossed_objects = [
      TripwireEvent(reliable_objects[obj_idx], direction)
      for obj_idx, direction in event_matches
    ]

    if len(previous_objects) != len(crossed_objects) \
       and now - tstate.when > DEBOUNCE_DELAY:
      log.debug("TRIPWIRE EVENT", previous_objects, len(crossed_objects))
      tstate.objects[detection_type] = crossed_objects
      tstate.when = now
      if 'objects' not in events:
        events['objects'] = []
      events['objects'].append((key, tripwire))
