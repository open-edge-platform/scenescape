# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Bounded constant-velocity prediction for untracked external objects."""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple
import uuid

from scene_common.geometry import Line, Point
from scene_common.timestamp import get_epoch_time

from analytics.state import PotentialAnalyticsEvent, PredictionAnalyticsState


SOURCE_VELOCITY_WEIGHT = 0.75
DEFAULT_HORIZON_INTERVALS = 2.0


@dataclass
class PredictionSample:
  """A predicted position and the metadata needed for regulated output."""
  scene_id: str
  detection_type: str
  object_id: str
  location: Point
  velocity: Point
  interval_ms: float
  observation_timestamp: float
  prediction_timestamp: float
  prediction_age_ms: float
  prediction_horizon_ms: float


@dataclass
class PredictionResult:
  """Predictions and potential-event lifecycle updates from one tick."""
  samples: List[PredictionSample] = field(default_factory=list)
  events: List[PotentialAnalyticsEvent] = field(default_factory=list)


@dataclass
class _PredictionTrack:
  scene_id: str
  scene_name: str
  detection_type: str
  object_id: str
  last_observed_location: Point
  last_observed_timestamp: float
  source_velocity: Point
  effective_velocity: Point
  interval_seconds: float
  start_delay_seconds: float
  horizon_seconds: float
  next_prediction_timestamp: float
  state: PredictionAnalyticsState
  expired: bool = False


class PredictionManager:
  """Own prediction baselines independently of tracker and analytics history."""

  def __init__(self):
    self._tracks: Dict[
      str, Dict[Tuple[str, str], _PredictionTrack]
    ] = {}

  def observe(self, scene, detection_type, objects, timestamp,
              scheduling_timestamp=None) -> List[PotentialAnalyticsEvent]:
    """Update real baselines and resolve active potential events."""
    events = []
    for obj in objects:
      object_id = getattr(obj, 'gid', None)
      if object_id is None:
        continue
      key = (detection_type, object_id)
      if not self._eligible(obj):
        scene_tracks = self._tracks.get(scene.uid, {})
        old_track = scene_tracks.pop(key, None)
        if old_track is not None:
          events.extend(self._resolve_all(
            old_track, 'rejected', timestamp, self._point(obj.sceneLoc)))
        if scene.uid in self._tracks and not scene_tracks:
          self._tracks.pop(scene.uid, None)
        continue

      velocity = self._point(getattr(obj, 'velocity', None))
      location = self._point(obj.sceneLoc)
      if velocity is None or location is None:
        continue

      scene_tracks = self._tracks.setdefault(scene.uid, {})
      old_track = scene_tracks.get(key)
      observation_timestamp = (
        scheduling_timestamp
        if scheduling_timestamp is not None
        else self._observation_time(obj, timestamp)
      )
      if (old_track is not None
          and observation_timestamp <= old_track.last_observed_timestamp):
        continue
      effective_velocity = velocity
      state = self._new_state(scene, location)
      if old_track is not None:
        events.extend(self._resolve(
          scene, old_track, location, observation_timestamp))
        effective_velocity = self._blend_velocity(
          velocity, old_track.last_observed_location,
          old_track.last_observed_timestamp, location, observation_timestamp)

      interval_seconds = float(obj.extrapolation_interval_ms) / 1000.0
      start_delay_ms = getattr(obj, 'extrapolation_start_delay_ms', None)
      start_delay_seconds = (
        float(start_delay_ms) / 1000.0
        if start_delay_ms is not None else interval_seconds
      )
      horizon_intervals = float(
        getattr(obj, 'extrapolation_horizon_intervals',
                DEFAULT_HORIZON_INTERVALS))
      scene_tracks[key] = _PredictionTrack(
        scene_id=scene.uid,
        scene_name=scene.name,
        detection_type=detection_type,
        object_id=object_id,
        last_observed_location=location,
        last_observed_timestamp=observation_timestamp,
        source_velocity=velocity,
        effective_velocity=effective_velocity,
        interval_seconds=interval_seconds,
        start_delay_seconds=start_delay_seconds,
        horizon_seconds=(
          start_delay_seconds + interval_seconds * horizon_intervals),
        next_prediction_timestamp=observation_timestamp + start_delay_seconds,
        state=state,
      )
    return events

  def is_fresh_observation(self, scene_id, detection_type, obj, timestamp,
                           scheduling_timestamp=None):
    """Return whether *obj* advances its external observation baseline."""
    if not self._eligible(obj):
      return True
    key = (detection_type, getattr(obj, 'gid', None))
    track = self._tracks.get(scene_id, {}).get(key)
    observation_timestamp = (
      scheduling_timestamp
      if scheduling_timestamp is not None
      else self._observation_time(obj, timestamp)
    )
    return (
      track is None
      or observation_timestamp > track.last_observed_timestamp
    )

  def predict(self, scene, now) -> PredictionResult:
    """Return due predictions and event updates for one scene."""
    result = PredictionResult()
    expired_keys = []
    scene_tracks = self._tracks.get(scene.uid, {})
    for key, track in list(scene_tracks.items()):
      age = now - track.last_observed_timestamp
      if now < track.next_prediction_timestamp:
        continue
      if age > track.horizon_seconds:
        if not track.expired:
          result.events.extend(self._resolve_all(track, 'expired', now))
          track.expired = True
        expired_keys.append(key)
        continue

      # Do not replay missed scheduler intervals as a burst. A delayed
      # scheduler tick represents the object's position at the current time.
      prediction_timestamp = now
      prediction_age = prediction_timestamp - track.last_observed_timestamp
      location = self._extrapolate(track, prediction_age)
      result.samples.append(PredictionSample(
        scene_id=track.scene_id,
        detection_type=track.detection_type,
        object_id=track.object_id,
        location=location,
        velocity=track.effective_velocity,
        interval_ms=track.interval_seconds * 1000.0,
        observation_timestamp=track.last_observed_timestamp,
        prediction_timestamp=prediction_timestamp,
        prediction_age_ms=prediction_age * 1000.0,
        prediction_horizon_ms=track.horizon_seconds * 1000.0,
      ))
      result.events.extend(self._evaluate_potential(
        scene, track, location, prediction_timestamp))
      track.next_prediction_timestamp = (
        prediction_timestamp + track.interval_seconds)

    for key in expired_keys:
      scene_tracks.pop(key, None)
    if not scene_tracks:
      self._tracks.pop(scene.uid, None)
    return result

  def has_scene(self, scene_id):
    """Return whether a scene has at least one live prediction baseline."""
    return bool(self._tracks.get(scene_id))

  def scene_ids(self):
    """Return scene IDs with prediction baselines."""
    return set(self._tracks)

  def discard_scene(self, scene_id, timestamp):
    """Expire and remove all prediction state for a deleted scene."""
    events = []
    scene_tracks = self._tracks.pop(scene_id, {})
    for track in scene_tracks.values():
      events.extend(self._resolve_all(track, 'expired', timestamp))
    return events

  @staticmethod
  def _eligible(obj):
    interval = getattr(obj, 'extrapolation_interval_ms', None)
    return (
      getattr(obj, 'extrapolation_enabled', False)
      and interval is not None
      and interval > 0
      and getattr(obj, 'position_source', 'observed') == 'observed'
    )

  @staticmethod
  def _observation_time(obj, fallback):
    value = getattr(obj, 'observation_timestamp', None)
    if isinstance(value, (int, float)):
      return float(value)
    if value is not None:
      return get_epoch_time(value)
    return fallback

  @staticmethod
  def _point(value) -> Optional[Point]:
    if value is None:
      return None
    values = value.asCartesianVector if isinstance(value, Point) else value
    try:
      valid = len(values) == 3 and all(
        math.isfinite(float(item)) for item in values)
    except (TypeError, ValueError):
      return None
    if not valid:
      return None
    return Point([float(item) for item in values])

  @staticmethod
  def _blend_velocity(source_velocity, previous_location, previous_time,
                      location, timestamp):
    delta = timestamp - previous_time
    if delta <= 0:
      return source_velocity
    measured = [
      (current - previous) / delta
      for current, previous in zip(
        location.asCartesianVector, previous_location.asCartesianVector)
    ]
    if not all(math.isfinite(value) for value in measured):
      return source_velocity
    source = source_velocity.asCartesianVector
    return Point([
      SOURCE_VELOCITY_WEIGHT * source[index]
      + (1.0 - SOURCE_VELOCITY_WEIGHT) * measured[index]
      for index in range(3)
    ])

  @staticmethod
  def _new_state(scene, location):
    return PredictionAnalyticsState(
      region_membership={
        key: region.isPointWithin(location)
        for key, region in scene.regions.items()
      },
      previous_location=location,
    )

  @staticmethod
  def _extrapolate(track, age):
    origin = track.last_observed_location.asCartesianVector
    velocity = track.effective_velocity.asCartesianVector
    return Point([
      origin[index] + velocity[index] * age
      for index in range(3)
    ])

  def _evaluate_potential(self, scene, track, location, now):
    events = []
    for geometry_id, region in scene.regions.items():
      previous = track.state.region_membership.get(
        geometry_id, region.isPointWithin(track.last_observed_location))
      current = region.isPointWithin(location)
      if current != previous:
        transition = 'entered' if current else 'exited'
        event = self._activate(
          track, 'region', geometry_id, region, transition, location, now)
        if event is not None:
          events.append(event)
      track.state.region_membership[geometry_id] = current

    previous_location = track.state.previous_location
    if previous_location is not None:
      line = Line(previous_location.as2Dxy, location.as2Dxy)
      for geometry_id, tripwire in scene.tripwires.items():
        direction = tripwire.lineCrosses(line)
        if direction:
          event = self._activate(
            track, 'tripwire', geometry_id, tripwire, -direction, location, now)
          if event is not None:
            events.append(event)
    track.state.previous_location = location
    return events

  def _activate(
      self, track, geometry_type, geometry_id, geometry, transition,
      location, now):
    key = (geometry_type, geometry_id, str(transition))
    if key in track.state.active_events:
      return None
    event = PotentialAnalyticsEvent(
      event_id=str(uuid.uuid4()),
      scene_id=track.scene_id,
      scene_name=track.scene_name,
      geometry_type=geometry_type,
      geometry_id=geometry_id,
      geometry_name=geometry.name,
      geometry_metadata=geometry.serialize(),
      object_id=track.object_id,
      detection_type=track.detection_type,
      transition=transition,
      anchor_timestamp=track.last_observed_timestamp,
      prediction_timestamp=now,
      translation=location.asCartesianVector,
    )
    track.state.active_events[key] = event
    return event

  def _resolve(self, scene, track, location, timestamp):
    events = []
    observed_line = Line(
      track.last_observed_location.as2Dxy, location.as2Dxy)
    for key, event in list(track.state.active_events.items()):
      geometry = (
        scene.regions.get(event.geometry_id)
        if event.geometry_type == 'region'
        else scene.tripwires.get(event.geometry_id)
      )
      confirmed = False
      if geometry is not None and event.geometry_type == 'region':
        was_inside = geometry.isPointWithin(track.last_observed_location)
        is_inside = geometry.isPointWithin(location)
        transition = 'entered' if is_inside and not was_inside else 'exited'
        confirmed = was_inside != is_inside and transition == event.transition
      elif geometry is not None:
        direction = geometry.lineCrosses(observed_line)
        confirmed = direction != 0 and -direction == event.transition
      event.status = 'confirmed' if confirmed else 'rejected'
      event.prediction_timestamp = timestamp
      event.translation = location.asCartesianVector
      events.append(event)
      track.state.active_events.pop(key, None)
    return events

  @staticmethod
  def _resolve_all(track, status, timestamp, location=None):
    events = []
    for event in track.state.active_events.values():
      event.status = status
      event.prediction_timestamp = timestamp
      if location is not None:
        event.translation = location.asCartesianVector
      events.append(event)
    track.state.active_events.clear()
    return events
