# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pose resolution and caching for the unified external-source ingestion path.

External sources (configured child scenes, physical agents such as drones or
vehicles, and the Scenescape positioning service) publish observations
expressed in their own local frame on
``scenescape/external/{publisher_id}/{thing_type}``. This module resolves
the transform that maps that local frame into a bound scene:

- Static child scenes populate the cache from their configured
  ``Scene.cameraPose`` (handled by callers, not this module).
- A dynamic agent may supply a global WGS84 pose. This is only resolvable
  when the target scene has valid four-corner geospatial calibration
  (``Scene.trs_xyz_to_lla``); otherwise ingestion is rejected rather than
  approximated.
- An authorized Scenescape positioning service may supply a pose already
  expressed in scene-local coordinates.

A message may omit ``pose`` entirely, in which case the most recent
non-expired cached transform for that ``(scene_id, source_id)`` pair is
reused. A message with a pose and an empty ``objects`` list updates the
cache without ingesting any observations.
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from scene_common import log
from scene_common.earth_lla import convertLLAToECEF
from scene_common.transform import CameraPose

DEFAULT_POSE_CACHE_TTL_SECONDS = 30.0
DEFAULT_IDENTITY_CLAIM_TTL_SECONDS = 30.0

# Upper bound on entries examined per sweep chunk, so a single
# background-sweep lock acquisition never blocks the ingestion critical
# path (resolve()/claim()) for more than a small, constant amount of time --
# even after a large backlog of expired entries has accumulated (e.g. the
# process was descheduled for a while). Chunks rotate every examined live
# entry to the end, so each background tick makes steady bounded progress
# across the complete cache rather than depending on message order.
DEFAULT_SWEEP_CHUNK_SIZE = 500

POSE_REFERENCE_FRAME_WGS84 = "wgs84"
POSE_REFERENCE_FRAME_SCENE = "scene"

# Reasons returned alongside a None transform so callers can log/report why
# an external-source message could not be ingested.
REASON_NO_POSE_AVAILABLE = "no_pose_available"
REASON_POSE_EXPIRED = "pose_expired"
REASON_SCENE_GEOREFERENCE_UNAVAILABLE = "scene_georeference_unavailable"
REASON_UNTRUSTED_SCENE_POSE = "untrusted_scene_pose"
REASON_UNSUPPORTED_REFERENCE_FRAME = "unsupported_reference_frame"
REASON_INVALID_POSE = "invalid_pose"

# Reason returned by IdentityClaimRegistry.claim() when a different source
# currently holds a live claim on the requested id.
REASON_IDENTITY_COLLISION = "identity_collision"


@dataclass
class _CachedPose:
  pose_mat: np.ndarray
  reference_frame: str
  provider: Optional[str]
  when: float
  expires_at: float


class ExternalSourcePoseCache:
  """Resolves and caches source-to-scene transforms for external sources.

  ``resolve()`` runs on the MQTT message-handling thread (the ingestion
  critical path) and must stay O(1): it only ever touches the single entry
  for its own ``key``, and holds ``_lock`` only for that brief dict access.
  Expired-entry cleanup is handled separately by a background daemon timer
  (``startBackgroundSweep()``); each tick evicts at most
  ``DEFAULT_SWEEP_CHUNK_SIZE`` entries so a sweep's lock acquisition is
  itself bounded and never makes ``resolve()`` wait on a large O(n) pass --
  see ``sweepExpired()``.
  """

  def __init__(self, ttl_seconds: float = DEFAULT_POSE_CACHE_TTL_SECONDS,
               sweep_interval_seconds: Optional[float] = None,
               sweep_chunk_size: int = DEFAULT_SWEEP_CHUNK_SIZE,
               sweep_grace_seconds: float = 0.0,
               sweep_time_provider: Optional[Callable[[], float]] = None):
    self._ttl_seconds = ttl_seconds
    self._sweep_interval_seconds = sweep_interval_seconds or ttl_seconds
    self._sweep_chunk_size = sweep_chunk_size
    self._sweep_grace_seconds = sweep_grace_seconds
    self._sweep_time_provider = sweep_time_provider or time.time
    # OrderedDict supports rotating a bounded sweep chunk without scanning
    # the entire cache while holding `_lock`.
    self._cache = OrderedDict()
    self._lock = threading.Lock()
    self._sweep_timer = None
    # Separate from `_lock` (which only guards `_cache`): protects the
    # timer lifecycle (`_sweep_timer`, `_sweep_stop`) across the thread
    # that calls start/stopBackgroundSweep() and the timer thread itself.
    self._sweep_lifecycle_lock = threading.Lock()
    self._sweep_stop = None
    return

  def resolve(self, scene, source_id, pose_data, when, trusted_scene_pose=False):
    """Resolve the transform to use for an external-source message.

    @param  scene                 Target Scene instance.
    @param  source_id             Identifier of the publishing source.
    @param  pose_data             The message's optional ``pose`` dict, or None.
    @param  when                  Epoch timestamp of the message.
    @param  trusted_scene_pose    Whether this source is authorized to publish
                                  a pose already expressed in scene-local
                                  coordinates (positioning-service privilege).
    @returns  (CameraPose or None, reason or None) tuple. ``reason`` is only
              set when the returned transform is None.
    """
    key = (scene.uid, source_id)
    with self._lock:
      if pose_data is not None:
        return self._resolveFromPose(scene, key, pose_data, when, trusted_scene_pose)
      return self._resolveFromCache(key, when)

  def _resolveFromPose(self, scene, key, pose_data, when, trusted_scene_pose):
    reference_frame = pose_data.get('reference_frame')
    rotation = pose_data.get('rotation', [0, 0, 0, 1])

    if reference_frame == POSE_REFERENCE_FRAME_SCENE:
      if not trusted_scene_pose:
        return None, REASON_UNTRUSTED_SCENE_POSE
      if 'translation' not in pose_data:
        return None, REASON_INVALID_POSE
      translation = pose_data['translation']
    elif reference_frame == POSE_REFERENCE_FRAME_WGS84:
      if scene.trs_xyz_to_lla is None:
        return None, REASON_SCENE_GEOREFERENCE_UNAVAILABLE
      if 'lat_long_alt' not in pose_data:
        return None, REASON_INVALID_POSE
      translation = self._wgs84ToScene(scene, pose_data['lat_long_alt'])
    else:
      return None, REASON_UNSUPPORTED_REFERENCE_FRAME

    existing = self._cache.get(key)
    if existing is not None and when < existing.when:
      # Out-of-order pose update; keep using the newer cached transform
      # (if still valid) rather than regressing to a stale position.
      log.warning(f"Ignoring out-of-order external source pose for {key}")
      return self._resolveFromCache(key, when)

    try:
      camera_pose = CameraPose(
        {'translation': translation, 'rotation': rotation, 'scale': [1.0, 1.0, 1.0]}, None)
    except (ValueError, TypeError) as e:
      log.error(f"Invalid external source pose for {key}: {e}")
      return None, REASON_INVALID_POSE

    self._cache[key] = _CachedPose(
      pose_mat=camera_pose.pose_mat,
      reference_frame=reference_frame,
      provider=pose_data.get('provider'),
      when=when,
      expires_at=when + self._ttl_seconds)
    # Keep recently refreshed entries at the end so bounded sweep chunks
    # spread work fairly over entries that are not being updated.
    self._cache.move_to_end(key)
    return camera_pose, None

  def _resolveFromCache(self, key, when):
    cached = self._cache.get(key)
    if cached is None:
      return None, REASON_NO_POSE_AVAILABLE
    if when > cached.expires_at:
      return None, REASON_POSE_EXPIRED
    return CameraPose(cached.pose_mat, None), None

  @staticmethod
  def _wgs84ToScene(scene, lat_long_alt):
    """Convert a global WGS84 position into the scene's local coordinates.

    Note: only position is transformed through the scene's geospatial
    calibration. Orientation (``rotation``) is passed through unrotated,
    matching the existing camera-detection ``lat_long_alt`` handling in
    ``Scene.processSceneData()``, which likewise does not rotate detection
    orientation. Full ENU-to-scene orientation alignment is future work.
    """
    ecef = convertLLAToECEF(lat_long_alt)
    inverse_trs = np.linalg.inv(scene.trs_xyz_to_lla)
    local = np.matmul(inverse_trs, np.hstack([ecef, 1]))
    return local[:3].tolist()

  def invalidate(self, scene_uid=None, source_id=None):
    """Clear cached transforms, optionally scoped to a scene and/or source."""
    with self._lock:
      if scene_uid is None and source_id is None:
        self._cache.clear()
        return
      for key in list(self._cache.keys()):
        if (scene_uid is None or key[0] == scene_uid) and \
           (source_id is None or key[1] == source_id):
          self._cache.pop(key, None)
    return

  def scenesWithLiveCache(self, source_id, when):
    """Return scene uids that still hold a non-expired pose for source_id."""
    scene_uids = []
    with self._lock:
      for (scene_uid, cached_source_id), cached in self._cache.items():
        if cached_source_id == source_id and when <= cached.expires_at:
          scene_uids.append(scene_uid)
    return scene_uids

  def _sweepExpiredChunk(self, now):
    """Sweep one bounded chunk and return ``(evicted, examined)``.

    Called only from the background timer, never from ``resolve()``.
    Live entries are moved to the end rather than stopping the sweep: event
    timestamps may arrive out of order, so touch order cannot determine
    expiration order. Entries remain eligible for
    ``_sweep_grace_seconds`` after their event-time TTL so a message
    delayed by up to the controller's accepted ``max_lag`` can still
    resolve its pose.
    """
    with self._lock:
      evicted = 0
      examined = 0
      while self._cache and examined < self._sweep_chunk_size:
        key, cached = self._cache.popitem(last=False)
        examined += 1
        if now > cached.expires_at + self._sweep_grace_seconds:
          evicted += 1
        else:
          self._cache[key] = cached
    return evicted, examined

  def sweepExpired(self, now):
    """Evict expired cache entries from one bounded sweep chunk."""
    evicted, _ = self._sweepExpiredChunk(now)
    return evicted

  def startBackgroundSweep(self):
    """Start a daemon timer thread that periodically evicts expired cache
    entries using the configured controller clock. Source ids are
    publisher-controlled and not pre-registered, so without this, a source
    that keeps publishing under fresh/rotating source ids would grow
    ``_cache`` without bound for the life of the process. Idempotent; safe
    to call multiple times.
    """
    with self._sweep_lifecycle_lock:
      if self._sweep_timer is not None:
        return
      self._sweep_stop = threading.Event()
      self._scheduleSweep(self._sweep_stop)
    return

  def stopBackgroundSweep(self):
    """Cancel the background sweep timer, if running.

    ``Timer.cancel()`` alone is not sufficient: it only prevents a timer
    that hasn't fired yet from firing, but does nothing if ``_sweepTick``
    is already running (e.g. mid-chunk-loop under a large backlog) --
    without the ``_sweep_stop`` event, that in-flight tick would just
    unconditionally reschedule itself at the end, silently undoing the
    stop. Each start creates a new stop event, which the callback captures;
    setting its own event first ensures an in-flight callback cannot
    reschedule after a stop/restart cycle.
    """
    with self._sweep_lifecycle_lock:
      if self._sweep_stop is not None:
        self._sweep_stop.set()
      if self._sweep_timer is not None:
        self._sweep_timer.cancel()
        self._sweep_timer = None
    return

  def _scheduleSweep(self, stop_event):
    # Caller must hold self._sweep_lifecycle_lock.
    timer = threading.Timer(
      self._sweep_interval_seconds, self._sweepTick, args=(stop_event,))
    timer.daemon = True
    self._sweep_timer = timer
    timer.start()
    return

  def _sweepTick(self, stop_event):
    # Repeat bounded chunks (each its own brief lock acquisition, so a
    # waiting resolve()/claim() call can always interleave between chunks)
    # until a chunk comes back under-full, meaning the backlog is drained
    # for now. This lets one tick keep up with a burst larger than a single
    # chunk without ever holding the lock for more than one chunk at a time.
    # The brief sleep between chunks matters: immediately re-acquiring the
    # lock after releasing it tends to win the race against another thread
    # that's still being scheduled to acquire it (Python's Lock is not
    # FIFO-fair), so without a yield a multi-chunk drain can still starve a
    # waiting resolve()/claim() call for the whole drain, not just one chunk.
    with self._lock:
      remaining = len(self._cache)
    while remaining > 0 and not stop_event.is_set():
      now = self._sweep_time_provider()
      _, examined = self._sweepExpiredChunk(now)
      remaining -= examined
      if examined == 0 or remaining <= 0:
        break
      if stop_event.is_set():
        return
      time.sleep(0)
    with self._sweep_lifecycle_lock:
      if stop_event.is_set() or self._sweep_stop is not stop_event:
        return
      self._scheduleSweep(stop_event)
    return


@dataclass
class _IdentityClaim:
  source_id: str
  when: float
  expires_at: float


class IdentityClaimRegistry:
  """Arbitrates ownership of external-source ``objects[*].id`` values used
  directly as global track identity (``gid``).

  External sources are not pre-registered or centrally provisioned: any
  source may publish observations carrying whatever per-object ``id`` it
  chooses (see the ``external_detection`` schema definition). Requiring an
  operator to pre-configure, per deployment, which sources' ids are safe to
  trust does not scale with the number of sources/integrations. Instead,
  every external-source object's ``id`` is trusted as its global track
  identity by default -- used directly as ``gid``, bypassing Scenescape's
  kinematic tracker/ReID association -- as long as no other source
  currently holds a live claim on that same id within the same scene and
  object category.

  If two different sources publish the same id concurrently, accepting both
  would silently merge two distinct physical objects under one identity.
  This registry detects exactly that case; the caller is expected to reject
  (drop) the newly arriving, colliding object rather than corrupt the
  existing track.

  Scope and limitation: this only protects against two *different* sources
  colliding on the same id at the same time. It does not, and cannot,
  protect against a single source reusing one of its own previously-claimed
  ids for a genuinely different physical object once that earlier claim has
  expired (for example, a robot restarting and reissuing small integer
  track-slot numbers). Sources with unstable/resettable local id schemes
  should still avoid relying on this trust; see the Scene Controller data
  format documentation for source_id/id selection guidance.

  ``claim()`` runs on the MQTT message-handling thread (the ingestion
  critical path) and must stay O(1): it only ever touches the single entry
  for its own ``key``, and holds ``_lock`` only for that brief dict access.
  Expired-claim cleanup is handled separately by a background daemon timer
  (``startBackgroundSweep()``); each tick evicts at most
  ``DEFAULT_SWEEP_CHUNK_SIZE`` entries so a sweep's lock acquisition is
  itself bounded and never makes ``claim()`` wait on a large O(n) pass --
  see ``sweepExpired()``.
  """

  def __init__(self, ttl_seconds: float = DEFAULT_IDENTITY_CLAIM_TTL_SECONDS,
               sweep_interval_seconds: Optional[float] = None,
               sweep_chunk_size: int = DEFAULT_SWEEP_CHUNK_SIZE,
               sweep_grace_seconds: float = 0.0,
               sweep_time_provider: Optional[Callable[[], float]] = None):
    self._ttl_seconds = ttl_seconds
    self._sweep_interval_seconds = sweep_interval_seconds or ttl_seconds
    self._sweep_chunk_size = sweep_chunk_size
    self._sweep_grace_seconds = sweep_grace_seconds
    self._sweep_time_provider = sweep_time_provider or time.time
    # OrderedDict supports rotating a bounded sweep chunk without scanning
    # the entire registry while holding `_lock`.
    self._claims = OrderedDict()
    self._lock = threading.Lock()
    self._sweep_timer = None
    # Separate from `_lock` (which only guards `_claims`): protects the
    # timer lifecycle (`_sweep_timer`, `_sweep_stop`) across the thread
    # that calls start/stopBackgroundSweep() and the timer thread itself.
    self._sweep_lifecycle_lock = threading.Lock()
    self._sweep_stop = None
    return

  def claim(self, scene_uid, category, source_id, obj_id, when):
    """Attempt to claim ``obj_id`` as global identity for ``source_id``.

    @param  scene_uid   Target scene's UID.
    @param  category    Object category/thing_type (the message's detection type).
    @param  source_id   Identifier of the publishing source.
    @param  obj_id      The object's source-local ``id`` from the payload.
    @param  when        Epoch timestamp of the message.
    @returns  (bool ok, reason or None) tuple. ``ok`` is False only when a
              different source currently holds a live (non-expired) claim
              on this id; ``reason`` is set in that case.
    """
    key = (scene_uid, category, obj_id)
    with self._lock:
      existing = self._claims.get(key)
      if existing is not None and existing.source_id != source_id and when <= existing.expires_at:
        return False, REASON_IDENTITY_COLLISION
      if existing is not None and existing.source_id == source_id and when < existing.when:
        return True, None
      self._claims[key] = _IdentityClaim(
        source_id=source_id, when=when, expires_at=when + self._ttl_seconds)
      # Keep recently refreshed entries at the end so bounded sweep chunks
      # spread work fairly over entries that are not being updated.
      self._claims.move_to_end(key)
      return True, None

  def invalidate(self, scene_uid=None, source_id=None):
    """Clear identity claims, optionally scoped to a scene and/or source."""
    with self._lock:
      if scene_uid is None and source_id is None:
        self._claims.clear()
        return
      for key, claim in list(self._claims.items()):
        if (scene_uid is None or key[0] == scene_uid) and \
           (source_id is None or claim.source_id == source_id):
          self._claims.pop(key, None)
    return

  def _sweepExpiredChunk(self, now):
    """Sweep one bounded chunk and return ``(evicted, examined)``.

    Called only from the background timer, never from ``claim()``. Live
    entries are moved to the end rather than stopping the sweep: event
    timestamps may arrive out of order, so touch order cannot determine
    expiration order. Claims remain eligible for
    ``_sweep_grace_seconds`` after their event-time TTL so a message
    delayed by up to the controller's accepted ``max_lag`` is still
    collision-checked.
    """
    with self._lock:
      evicted = 0
      examined = 0
      while self._claims and examined < self._sweep_chunk_size:
        key, claim = self._claims.popitem(last=False)
        examined += 1
        if now > claim.expires_at + self._sweep_grace_seconds:
          evicted += 1
        else:
          self._claims[key] = claim
    return evicted, examined

  def sweepExpired(self, now):
    """Evict expired identity claims from one bounded sweep chunk."""
    evicted, _ = self._sweepExpiredChunk(now)
    return evicted

  def startBackgroundSweep(self):
    """Start a daemon timer thread that periodically evicts expired claims
    using the configured controller clock. ``obj_id`` values are
    publisher-controlled and unbounded (see class docstring), so without
    this, a source that keeps publishing new ids would grow ``_claims``
    without bound for the life of the process. Idempotent; safe to call
    multiple times.
    """
    with self._sweep_lifecycle_lock:
      if self._sweep_timer is not None:
        return
      self._sweep_stop = threading.Event()
      self._scheduleSweep(self._sweep_stop)
    return

  def stopBackgroundSweep(self):
    """Cancel the background sweep timer, if running.

    ``Timer.cancel()`` alone is not sufficient: it only prevents a timer
    that hasn't fired yet from firing, but does nothing if ``_sweepTick``
    is already running (e.g. mid-chunk-loop under a large backlog) --
    without the ``_sweep_stop`` event, that in-flight tick would just
    unconditionally reschedule itself at the end, silently undoing the
    stop. Each start creates a new stop event, which the callback captures;
    setting its own event first ensures an in-flight callback cannot
    reschedule after a stop/restart cycle.
    """
    with self._sweep_lifecycle_lock:
      if self._sweep_stop is not None:
        self._sweep_stop.set()
      if self._sweep_timer is not None:
        self._sweep_timer.cancel()
        self._sweep_timer = None
    return

  def _scheduleSweep(self, stop_event):
    # Caller must hold self._sweep_lifecycle_lock.
    timer = threading.Timer(
      self._sweep_interval_seconds, self._sweepTick, args=(stop_event,))
    timer.daemon = True
    self._sweep_timer = timer
    timer.start()
    return

  def _sweepTick(self, stop_event):
    # Repeat bounded chunks (each its own brief lock acquisition, so a
    # waiting claim() call can always interleave between chunks) until a
    # chunk comes back under-full, meaning the backlog is drained for now.
    # This lets one tick keep up with a burst larger than a single chunk
    # without ever holding the lock for more than one chunk at a time. The
    # brief sleep between chunks matters: immediately re-acquiring the lock
    # after releasing it tends to win the race against another thread
    # that's still being scheduled to acquire it (Python's Lock is not
    # FIFO-fair), so without a yield a multi-chunk drain can still starve a
    # waiting claim() call for the whole drain, not just one chunk.
    with self._lock:
      remaining = len(self._claims)
    while remaining > 0 and not stop_event.is_set():
      now = self._sweep_time_provider()
      _, examined = self._sweepExpiredChunk(now)
      remaining -= examined
      if examined == 0 or remaining <= 0:
        break
      if stop_event.is_set():
        return
      time.sleep(0)
    with self._sweep_lifecycle_lock:
      if stop_event.is_set() or self._sweep_stop is not stop_event:
        return
      self._scheduleSweep(stop_event)
    return
