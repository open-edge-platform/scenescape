# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shadow-mode parity validation for analytics.

Runs an independent analytics pass (shadow path) alongside the primary tracker
path and compares results frame-by-frame.  Divergences are logged as warnings so
engineers can validate correctness before switching to the analytics-only path.

Public API
----------
run_shadow(detection_type, raw_objects, scene, now)
    Ingest *raw_objects* into ``scene.shadow_ingestion``, run ``process_frame``
    against ``scene.shadow_state``, and store per-frame events in
    ``scene._shadow_events``.

compare_states(primary_state, shadow_state, scene_id, detection_type)
    Compare per-region/tripwire gid sets between the two stores.  Returns the
    number of divergent keys found this frame.

build_event_dicts(events, scene, state, ts_str, scene_controller)
    Mirror the ``publishEvents`` serialisation loop against an arbitrary
    *state* store and *events* dict — without publishing.  Returns a mapping
    ``{(region_key, event_type): event_data_dict}``.

compare_events(primary_events, shadow_events, scene_id)
    Structurally compare two ``build_event_dicts`` outputs.  Returns the
    number of divergent event keys found.
"""

from scene_common import log
from scene_common.geometry import Region, Tripwire

from controller.analytics.analytics_models import moving_object_to_analytics_object
from controller.analytics.engine import process_frame
from controller.analytics.state import RegionAnalyticsState, TripwireAnalyticsState


# ---------------------------------------------------------------------------
# Shadow run
# ---------------------------------------------------------------------------

def run_shadow(detection_type, raw_objects, scene, now):
  """Run one frame of shadow analytics.

  Ingests *raw_objects* (MQTT-serialised dict list) through
  ``scene.shadow_ingestion``, converts them to ``AnalyticsObject`` instances,
  and calls ``process_frame`` against ``scene.shadow_state``.  Per-frame events
  are written to ``scene._shadow_events`` (reset on each call).

  Args:
    detection_type: Detection category string, e.g. ``'person'``.
    raw_objects:    List of MQTT object dicts (same shape as
                    ``jdata['objects']`` after ``publishDetections``).
    scene:          Scene instance with ``shadow_ingestion``, ``shadow_state``
                    and ``_shadow_events`` attributes.
    now:            Current epoch timestamp (float).
  """
  scene._shadow_events = {}

  # Clear per-frame entered/exited state from the previous shadow frame,
  # mirroring the primary path's _clearSensorValuesOnExit inside publishEvents.
  for rstate in scene.shadow_state._regions.values():
    rstate.clear_frame_state()

  scene.shadow_ingestion.ingest(detection_type, raw_objects, scene.sensors)
  shadow_objs = scene.shadow_ingestion.get_objects(detection_type)
  ao_list = [moving_object_to_analytics_object(o) for o in shadow_objs]

  process_frame(
    detection_type,
    now,
    ao_list,
    scene.regions,
    scene.sensors,
    scene.tripwires,
    scene._shadow_events,
    scene.shadow_state,
    scene.isIntersecting,
  )


# ---------------------------------------------------------------------------
# State comparison
# ---------------------------------------------------------------------------

# Events fired by one path up to this many seconds before the other path fires
# the same event are treated as debounce-timing offsets, not logic errors.
_DEBOUNCE_SUPPRESS_WINDOW_S = 1.5


def _check_suppress(cache, cache_key, this_path, now):
  """Return True if this event was already seen in the other path within the window.

  As a side effect, records this occurrence when no matching other-path entry is
  found, or consumes the match when suppressing.
  """
  other_path = 'shadow' if this_path == 'primary' else 'primary'
  entry = cache.get(cache_key)
  if entry is not None:
    ts, path = entry
    if path == other_path and now - ts <= _DEBOUNCE_SUPPRESS_WINDOW_S:
      del cache[cache_key]   # consume match
      return True
  # Not yet seen from the other path — record this occurrence.
  cache[cache_key] = (now, this_path)
  return False


def _cleanup_cache(cache, now, max_age=3.0):
  stale = [k for k, (ts, _) in cache.items() if now - ts > max_age]
  for k in stale:
    del cache[k]


def compare_states(primary_state, shadow_state, scene_id, detection_type,
                  event_cache=None, now=None):
  """Compare per-region and per-tripwire analytics state gid sets.

  Logs a WARNING for each key where primary and shadow differ.  Does **not**
  raise; divergences are counted and returned so the caller can record metrics.

  Args:
    primary_state:   ``AnalyticsStateStore`` from the tracker path.
    shadow_state:    ``AnalyticsStateStore`` from the shadow path.
    scene_id:        Scene uid string (for log context).
    detection_type:  Detection category string (for log context).

  Returns:
    int: Number of divergent region/tripwire keys detected this frame.
  """
  divergences = 0

  if event_cache is not None and now is not None:
    _cleanup_cache(event_cache, now)

  all_region_keys = set(primary_state._regions) | set(shadow_state._regions)
  for key in all_region_keys:
    p = primary_state._regions.get(key) or RegionAnalyticsState()
    s = shadow_state._regions.get(key) or RegionAnalyticsState()

    p_ent = {o.gid for objs in p.entered.values() for o in objs}
    s_ent = {o.gid for objs in s.entered.values() for o in objs}
    if p_ent != s_ent:
      report = True
      if event_cache is not None and now is not None:
        suppressed = all(
          _check_suppress(event_cache, (key, g, 'entered'), 'shadow', now)
          for g in s_ent - p_ent
        ) and all(
          _check_suppress(event_cache, (key, g, 'entered'), 'primary', now)
          for g in p_ent - s_ent
        )
        report = not suppressed
      if report:
        log.warning(
          f"SHADOW divergence scene={scene_id} type={detection_type} "
          f"region={key} entered: primary={p_ent} shadow={s_ent}"
        )
        divergences += 1

    p_exit = {o.gid for objs in p.exited.values() for o, _ in objs}
    s_exit = {o.gid for objs in s.exited.values() for o, _ in objs}
    if p_exit != s_exit:
      report = True
      if event_cache is not None and now is not None:
        suppressed = all(
          _check_suppress(event_cache, (key, g, 'exited'), 'shadow', now)
          for g in s_exit - p_exit
        ) and all(
          _check_suppress(event_cache, (key, g, 'exited'), 'primary', now)
          for g in p_exit - s_exit
        )
        report = not suppressed
      if report:
        log.warning(
          f"SHADOW divergence scene={scene_id} type={detection_type} "
          f"region={key} exited: primary={p_exit} shadow={s_exit}"
        )
        divergences += 1

  all_tripwire_keys = set(primary_state._tripwires) | set(shadow_state._tripwires)
  for key in all_tripwire_keys:
    p = primary_state._tripwires.get(key) or TripwireAnalyticsState()
    s = shadow_state._tripwires.get(key) or TripwireAnalyticsState()

    p_cross = {
      (e.object.gid, e.direction)
      for evts in p.objects.values()
      for e in evts
    }
    s_cross = {
      (e.object.gid, e.direction)
      for evts in s.objects.values()
      for e in evts
    }
    if p_cross != s_cross:
      report = True
      if event_cache is not None and now is not None:
        suppressed = all(
          _check_suppress(event_cache, (key, g, d, 'crossing'), 'shadow', now)
          for g, d in s_cross - p_cross
        ) and all(
          _check_suppress(event_cache, (key, g, d, 'crossing'), 'primary', now)
          for g, d in p_cross - s_cross
        )
        report = not suppressed
      if report:
        log.warning(
          f"SHADOW divergence scene={scene_id} type={detection_type} "
          f"tripwire={key} crossings: primary={p_cross} shadow={s_cross}"
        )
        divergences += 1

  return divergences


# ---------------------------------------------------------------------------
# Event dict builder (publishEvents equivalent — no publish side-effect)
# ---------------------------------------------------------------------------

def build_event_dicts(events, scene, state, ts_str, scene_controller):
  """Serialise analytics events from *events*/*state* without publishing.

  Mirrors the loop inside ``SceneController.publishEvents`` but writes output
  to a plain dict instead of pushing to MQTT.  This lets the shadow path
  produce event payloads that can be structurally compared against the primary
  path.

  Args:
    events:           Mutable events dict produced by ``process_frame`` (e.g.
                      ``scene.events`` or ``scene._shadow_events``).
    scene:            Scene instance (for geometry and metadata access).
    state:            ``AnalyticsStateStore`` whose region/tripwire state to
                      read (primary or shadow).
    ts_str:           ISO-8601 timestamp string for the current frame.
    scene_controller: ``SceneController`` instance — its ``_buildAllRegionObjsList``,
                      ``_buildEnteredObjsList``, and ``_buildExitedObjsList``
                      helpers are reused here.

  Returns:
    dict: Mapping ``{(region_key, event_type): event_data_dict}``.
  """
  result = {}
  for event_type in events:
    for key, region in events[event_type]:
      if isinstance(region, Tripwire):
        etype = 'tripwire'
        region_state = state.tripwire(key)
      elif isinstance(region, Region):
        etype = 'region'
        region_state = state.region(key)
      else:
        continue

      event_data = {
        'timestamp': ts_str,
        'scene_id': scene.uid,
        'scene_name': scene.name,
        etype + '_id': region.uuid,
        etype + '_name': region.name,
      }
      detections_dict, _ = scene_controller._buildAllRegionObjsList(
        scene, region_state, event_data
      )
      scene_controller._buildEnteredObjsList(
        scene, region_state, event_data, detections_dict
      )
      scene_controller._buildExitedObjsList(scene, region_state, event_data)

      result[(key, event_type)] = event_data

  return result


# ---------------------------------------------------------------------------
# Event comparison
# ---------------------------------------------------------------------------

_DWELL_TOLERANCE_S = 1.0


def compare_events(primary_events, shadow_events, scene_id, event_cache=None, now=None):
  """Compare two ``build_event_dicts`` outputs structurally.

  Compares counts (exact), entered id-sets (exact), exited id-sets (exact),
  and per-object dwell times (within ``±1 s``).  Float-valued fields outside
  dwell times are ignored to avoid floating-point instability.

  Args:
    primary_events: Return value of ``build_event_dicts(scene.events, ...)``.
    shadow_events:  Return value of ``build_event_dicts(scene._shadow_events, ...)``.
    scene_id:       Scene uid string (for log context).

  Returns:
    int: Number of divergent event keys detected.
  """
  divergences = 0
  all_keys = set(primary_events) | set(shadow_events)

  for ev_key in all_keys:
    key, event_type = ev_key

    if ev_key not in primary_events:
      suppress = (event_cache is not None and now is not None
                  and _check_suppress(event_cache, (key, event_type, 'event'), 'shadow', now))
      if not suppress:
        log.warning(
          f"SHADOW event divergence scene={scene_id} region={key} "
          f"type={event_type}: present in shadow only"
        )
        divergences += 1
      continue

    if ev_key not in shadow_events:
      suppress = (event_cache is not None and now is not None
                  and _check_suppress(event_cache, (key, event_type, 'event'), 'primary', now))
      if not suppress:
        log.warning(
          f"SHADOW event divergence scene={scene_id} region={key} "
          f"type={event_type}: present in primary only"
        )
        divergences += 1
      continue

    p = primary_events[ev_key]
    s = shadow_events[ev_key]

    # counts
    if p.get('counts') != s.get('counts'):
      log.warning(
        f"SHADOW event divergence scene={scene_id} region={key} "
        f"type={event_type} counts: primary={p.get('counts')} "
        f"shadow={s.get('counts')}"
      )
      divergences += 1

    # entered id-sets
    p_entered = {o['id'] for o in p.get('entered', [])}
    s_entered = {o['id'] for o in s.get('entered', [])}
    if p_entered != s_entered:
      log.warning(
        f"SHADOW event divergence scene={scene_id} region={key} "
        f"type={event_type} entered: primary={p_entered} shadow={s_entered}"
      )
      divergences += 1

    # exited id-sets and dwell times
    p_exited = {item['object']['id']: item['dwell'] for item in p.get('exited', [])}
    s_exited = {item['object']['id']: item['dwell'] for item in s.get('exited', [])}
    if set(p_exited) != set(s_exited):
      log.warning(
        f"SHADOW event divergence scene={scene_id} region={key} "
        f"type={event_type} exited ids: primary={set(p_exited)} "
        f"shadow={set(s_exited)}"
      )
      divergences += 1
    else:
      for gid, p_dwell in p_exited.items():
        s_dwell = s_exited.get(gid, 0.0)
        if abs(p_dwell - s_dwell) > _DWELL_TOLERANCE_S:
          log.warning(
            f"SHADOW event divergence scene={scene_id} region={key} "
            f"type={event_type} dwell for {gid}: "
            f"primary={p_dwell:.3f}s shadow={s_dwell:.3f}s"
          )
          divergences += 1

  return divergences
