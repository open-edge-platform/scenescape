# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common.timestamp import get_iso_time

from analytics.region import update_region_events
from analytics.tripwire import update_tripwire_events

# Objects must appear this many times before being passed to region/tripwire
# analytics.
MIN_FRAMES_FOR_RELIABLE_TRACK = 3


def process_frame(
    detection_type,
    now,
    cur_objects,
    regions,
    sensors,
    tripwires,
    events,
    state_store,
    is_intersecting_fn=None,
):
  """Run all analytics for one frame and write results into events.

  This is the single entry point that replaces scene._updateEvents.  The
  caller (Scene) is responsible for:
    - resolving cur_objects from the tracker or analytics cache
    - converting them to AnalyticsObject via moving_object_to_analytics_object

  Objects are filtered internally by MIN_FRAMES_FOR_RELIABLE_TRACK using
  publishedLocations length, so the same gate applies to both the primary
  tracker path and the analytics-only path.

  Args:
    detection_type:    Detection category string (e.g. 'person').
    now:               Current epoch timestamp (float).
    cur_objects:       List of AnalyticsObject for this frame.
    regions:           Dict of {key: Region} — geometry regions.
    sensors:           Dict of {key: Sensor} — sensor regions.
    tripwires:         Dict of {key: Tripwire}.
    events:            Mutable dict; region, count, and tripwire events are
                       appended here.
    state_store:       AnalyticsStateStore that owns all analytics state for
                       this scene.
    is_intersecting_fn: Optional callable(obj, region) -> bool for 3-D mesh
                       intersection fallback in region analytics.
  """
  now_str = get_iso_time(now)

  for obj in cur_objects:
    obj.chain_data.publishedLocations.insert(0, obj.sceneLoc)

  reliable_objects = [
    obj for obj in cur_objects
    if len(obj.chain_data.publishedLocations) > MIN_FRAMES_FOR_RELIABLE_TRACK
  ]

  update_region_events(
    detection_type, regions, now, now_str, reliable_objects, events,
    state_store, is_intersecting_fn,
  )
  update_region_events(
    detection_type, sensors, now, now_str, reliable_objects, events,
    state_store, is_intersecting_fn,
  )

  update_tripwire_events(
    detection_type, tripwires, now, reliable_objects, events, state_store,
  )
