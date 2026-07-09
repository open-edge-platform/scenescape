# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common.timestamp import get_iso_time

from controller.analytics.region import update_region_events
from controller.analytics.tripwire import update_tripwire_events


def process_frame(
    detection_type,
    now,
    cur_objects,
    regions,
    sensors,
    tripwires,
    events,
    use_tracker,
    is_intersecting_fn=None,
):
  """Run all analytics for one frame and write results into events.

  This is the single entry point that replaces scene._updateEvents.  The
  caller (Scene) is responsible for:
    - resolving cur_objects from the tracker or analytics cache
    - converting them to AnalyticsObject via moving_object_to_analytics_object

  Args:
    detection_type:    Detection category string (e.g. 'person').
    now:               Current epoch timestamp (float).
    cur_objects:       List of AnalyticsObject for this frame.
    regions:           Dict of {key: Region} — geometry regions.
    sensors:           Dict of {key: Sensor} — sensor regions.
    tripwires:         Dict of {key: Tripwire}.
    events:            Mutable dict; region, count, and tripwire events are
                       appended here.
    use_tracker:       Controls the frameCount reliability gate across all
                       analytics sub-functions.
    is_intersecting_fn: Optional callable(obj, region) -> bool for 3-D mesh
                       intersection fallback in region analytics.
  """
  now_str = get_iso_time(now)

  for obj in cur_objects:
    obj.chain_data.publishedLocations.insert(0, obj.sceneLoc)

  update_region_events(
    detection_type, regions, now, now_str, cur_objects, events,
    use_tracker, is_intersecting_fn,
  )
  update_region_events(
    detection_type, sensors, now, now_str, cur_objects, events,
    use_tracker, is_intersecting_fn,
  )

  update_tripwire_events(
    detection_type, tripwires, now, cur_objects, events, use_tracker,
  )
