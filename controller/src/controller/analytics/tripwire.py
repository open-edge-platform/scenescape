# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log
from scene_common.geometry import getTripwireEvents

DEBOUNCE_DELAY = 0.5
MIN_FRAMES_FOR_RELIABLE_TRACK = 3


class TripwireEvent:
  def __init__(self, object, direction):
    self.object = object
    self.direction = direction
    return


def update_tripwire_events(detection_type, tripwires, now, cur_objects, events, use_tracker):
  """Detect tripwire crossings and append events to the shared events dict.

  When use_tracker is False (analytics-only mode) the frameCount reliability
  gate is skipped and all objects with enough location history are considered.

  Args:
    detection_type: Detection category string (e.g. 'person').
    tripwires:      Dict of {key: Tripwire} from the scene.
    now:            Current epoch timestamp (float).
    cur_objects:    List of AnalyticsObject for this frame.
    events:         Mutable dict; crossing events are appended under 'objects'.
    use_tracker:    When True the frameCount > MIN_FRAMES_FOR_RELIABLE_TRACK
                    gate is applied.
  """
  reliable_objects = [
    obj for obj in cur_objects
    if (not use_tracker or obj.frameCount > MIN_FRAMES_FOR_RELIABLE_TRACK)
    and len(obj.chain_data.publishedLocations) > 1
  ]

  object_locations = [
    obj.chain_data.publishedLocations[:2] for obj in reliable_objects
  ]

  crossing_events = getTripwireEvents(tripwires, object_locations)

  for key, tripwire in tripwires.items():
    event_matches = crossing_events.get(key, [])
    previous_objects = tripwire.objects.get(detection_type, [])
    crossed_objects = [
      TripwireEvent(reliable_objects[obj_idx], direction)
      for obj_idx, direction in event_matches
    ]

    if len(previous_objects) != len(crossed_objects) \
       and now - tripwire.when > DEBOUNCE_DELAY:
      log.debug("TRIPWIRE EVENT", previous_objects, len(crossed_objects))
      tripwire.objects[detection_type] = crossed_objects
      tripwire.when = now
      if 'objects' not in events:
        events['objects'] = []
      events['objects'].append((key, tripwire))
