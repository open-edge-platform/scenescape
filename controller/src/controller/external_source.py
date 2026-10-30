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
reused. Legacy single-camera calibration and multi-camera configurations are
cached on the same entry; camera observations remain scoped to their camera.
"""

import threading
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Callable, Optional

import numpy as np

from scene_common import log
from scene_common.earth_lla import convertLLAToECEF
from scene_common.transform import CameraIntrinsics, CameraPose

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
REASON_NO_INTRINSICS_AVAILABLE = "no_intrinsics_available"
REASON_INVALID_INTRINSICS = "invalid_intrinsics"

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
  # Legacy single-camera calibration is kept separately from multi-camera state.
  intrinsics: Optional[dict] = None
  distortion: Optional[dict] = None
  cameras: Optional[list[dict]] = None


class ExternalSourcePoseCache:
  """Resolves and caches source-to-scene transforms for external sources.

  ``resolve()`` / ``resolveIntrinsics()`` run on the MQTT message-handling
  thread (the ingestion critical path) and must stay O(1): each only ever
  touches the single entry for its own ``key``, and holds ``_lock`` only for
  that brief dict access. Expired-entry cleanup is handled separately by a
  background daemon timer (``startBackgroundSweep()``); each tick evicts at
  most ``DEFAULT_SWEEP_CHUNK_SIZE`` entries so a sweep's lock acquisition is
  itself bounded and never makes ``resolve()`` wait on a large O(n) pass --
  see ``sweepExpired()``.
  """

  def __init__(self, ttl_seconds: float = DEFAULT_POSE_CACHE_TTL_SECONDS,
               sweep_interval_seconds: Optional[float] = None,
               sweep_chunk_size: int = DEFAULT_SWEEP_CHUNK_SIZE,
               sweep_grace_seconds: float = 0.0,
               sweep_time_provider: Optional[Callable[[], float]] = None,
               on_remove: Optional[Callable[[str, str], None]] = None):
    self._ttl_seconds = ttl_seconds
    self._sweep_interval_seconds = sweep_interval_seconds or ttl_seconds
    self._sweep_chunk_size = sweep_chunk_size
    self._sweep_grace_seconds = sweep_grace_seconds
    self._sweep_time_provider = sweep_time_provider or time.time
    # Called under the cache lock: callbacks must not re-enter the cache.
    self._on_remove = on_remove
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
    pose, _, reason = self.resolveMessage(
      scene, source_id, {'pose': pose_data}, when, trusted_scene_pose)
    return pose, reason

  def resolveMessage(self, scene, source_id, message: dict, when: float,
                     trusted_scene_pose: bool = False):
    """Return (pose, cached state, reason), updating source and camera state."""
    key = (scene.uid, source_id)
    with self._lock:
      pose_data = message.get('pose')
      existing = self._cache.get(key)
      reason = self._validateCameraUpdate(key, message, existing)
      if reason is not None:
        return None, None, reason
      if pose_data is not None:
        pose, reason = self._resolveFromPose(
          scene, key, pose_data, when, trusted_scene_pose)
      else:
        pose, reason = self._resolveFromCache(key, when)
      if pose is None:
        return None, None, reason
      state = self._cache[key]
      self._cacheCameraConfiguration(message, state, when)
      return pose, state, None

  def _validateCameraUpdate(self, key, message, existing):
    """Reject invalid camera snapshots and incomplete camera-source pose updates."""
    if 'cameras' in message:
      if not self._validCameraConfiguration(key, message['cameras']):
        return REASON_INVALID_INTRINSICS
      return None
    if existing is not None and existing.cameras is not None and message.get('pose') is not None:
      log.error(f"Camera pose update for {key} is missing the complete cameras list")
      return REASON_INVALID_INTRINSICS
    return None

  @staticmethod
  def _cacheCameraConfiguration(message, state, when):
    if 'cameras' not in message:
      return
    if when < state.when:
      log.warning(
        f"Ignoring stale external camera configuration: incoming_time={when} "
        f"cached_time={state.when} cached_camera_ids="
        f"{[camera['id'] for camera in state.cameras or []]}")
      return
    cameras = deepcopy(message['cameras'])
    for camera in cameras:
      camera.pop('objects', None)
    state.cameras = cameras
    state.intrinsics = None
    state.distortion = None

  def _validCameraConfiguration(self, key, cameras: list) -> bool:
    try:
      if not isinstance(cameras, list):
        raise ValueError("cameras must be an array")
      camera_ids = [self._validateCamera(camera) for camera in cameras]
      if len(camera_ids) != len(set(camera_ids)):
        raise ValueError("Camera ids must be unique within the source")
    except (KeyError, ValueError, TypeError) as error:
      log.error(f"Invalid external camera configuration for {key}: {error}")
      return False
    return True

  def _validateCamera(self, camera):
    if not isinstance(camera, dict) or not all(
        field in camera for field in ('id', 'mount', 'intrinsics', 'objects')):
      raise ValueError("Each camera requires id, mount, intrinsics, and objects")
    camera_id = camera['id']
    if not isinstance(camera_id, str) or not camera_id:
      raise ValueError("Camera ids must be non-empty strings")
    mount = camera['mount']
    CameraPose({
      'translation': mount['translation'],
      'rotation': mount['rotation'],
      'scale': [1.0, 1.0, 1.0],
    }, None)
    if not isinstance(camera['objects'], list):
      raise ValueError(f"Objects for camera {camera_id} must be an array")
    self._validateIntrinsics(camera['intrinsics'], camera.get('distortion'))
    return camera_id

  def _poseTranslation(self, scene, pose_data, trusted_scene_pose):
    """Resolve position while enforcing frame-specific trust requirements."""
    reference_frame = pose_data.get('reference_frame')
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
    return translation, None

  def _resolveFromPose(self, scene, key, pose_data, when, trusted_scene_pose):
    translation, reason = self._poseTranslation(scene, pose_data, trusted_scene_pose)
    if reason is not None:
      return None, reason
    rotation = pose_data.get('rotation', [0, 0, 0, 1])

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

    pose_update = dict(
      pose_mat=camera_pose.pose_mat,
      reference_frame=pose_data['reference_frame'],
      provider=pose_data.get('provider'),
      when=when,
      expires_at=when + self._ttl_seconds)
    # A live pose refresh preserves calibration; a new lifetime starts clean.
    if existing is None or when > existing.expires_at:
      self._cache[key] = _CachedPose(**pose_update)
    else:
      self._cache[key] = replace(existing, **pose_update)
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

  def resolveIntrinsics(self, scene_uid, source_id, intrinsics_data, distortion_data, when):
    """Resolve camera intrinsics for pixel detections from this source.

    When ``intrinsics_data`` is provided, validates it and stores it on the
    live pose-cache entry for ``(scene_uid, source_id)``. Otherwise reuses
    the most recently cached non-expired intrinsics for that key.

    Intrinsics are attached to the pose-cache entry, so a live pose must
    already exist (from this message or a prior one). Returns
    ``(CameraIntrinsics or None, reason or None)``.
    """
    key = (scene_uid, source_id)
    with self._lock:
      cached = self._cache.get(key)
      if cached is None:
        return None, REASON_NO_POSE_AVAILABLE
      if when > cached.expires_at:
        return None, REASON_POSE_EXPIRED

      if intrinsics_data is not None and when >= cached.when:
        try:
          resolved = self._validateIntrinsics(intrinsics_data, distortion_data)
        except (ValueError, TypeError) as e:
          log.error(f"Invalid external source intrinsics for {key}: {e}")
          return None, REASON_INVALID_INTRINSICS
        cached.intrinsics = deepcopy(intrinsics_data)
        cached.distortion = deepcopy(distortion_data)
        self._cache.move_to_end(key)
        return resolved, None

      if cached.intrinsics is None:
        return None, REASON_NO_INTRINSICS_AVAILABLE
      try:
        return CameraIntrinsics(cached.intrinsics, cached.distortion), None
      except (ValueError, TypeError) as e:
        log.error(f"Invalid cached external source intrinsics for {key}: {e}")
        return None, REASON_INVALID_INTRINSICS

  @staticmethod
  def _validateIntrinsics(intrinsics_data, distortion_data):
    resolved = CameraIntrinsics(intrinsics_data, distortion_data)
    if not np.isfinite(resolved.intrinsics).all() or \
       resolved.intrinsics[0, 0] <= 0 or resolved.intrinsics[1, 1] <= 0:
      raise ValueError("Focal lengths must be positive and intrinsics finite")
    return resolved

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
      for key in list(self._cache.keys()):
        if (scene_uid is None or key[0] == scene_uid) and \
           (source_id is None or key[1] == source_id):
          self._cache.pop(key, None)
          if self._on_remove is not None:
            self._on_remove(*key)
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
          if self._on_remove is not None:
            self._on_remove(*key)
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
  """Arbitrates ownership of external-source object identities used as a
  global track identity (``gid``).

  External sources are not pre-registered or centrally provisioned: any
  source may publish observations carrying whatever per-object ``id`` it
  chooses (see the ``external_detection`` schema definition). Requiring an
  operator to pre-configure, per deployment, which sources' ids are safe to
  trust does not scale with the number of sources/integrations. An object's
  source-provided ``id`` is used directly as ``gid``, as long as no other
  source currently holds a live claim on that id in the same scene and
  category.

  If two different sources publish the same source-local id concurrently,
  accepting both would silently merge two distinct physical objects. The
  caller rejects that collision.

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
    @param  source_id   Claim owner: publisher id or shared global-identity key.
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
