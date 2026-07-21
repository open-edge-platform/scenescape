# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pose resolution and caching for the unified external-source ingestion path.

External sources (configured child scenes, physical agents such as drones or
vehicles, and the Scenescape positioning service) publish observations
expressed in their own local frame on the existing
``scenescape/external/{scene_id}/{thing_type}`` topic. This module resolves
the transform that maps that local frame into the target scene:

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

from dataclasses import dataclass
from typing import Optional

import numpy as np

from scene_common import log
from scene_common.earth_lla import convertLLAToECEF
from scene_common.transform import CameraPose

DEFAULT_POSE_CACHE_TTL_SECONDS = 30.0

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


@dataclass
class _CachedPose:
  pose_mat: np.ndarray
  reference_frame: str
  provider: Optional[str]
  when: float
  expires_at: float


class ExternalSourcePoseCache:
  """Resolves and caches source-to-scene transforms for external sources."""

  def __init__(self, ttl_seconds: float = DEFAULT_POSE_CACHE_TTL_SECONDS):
    self._ttl_seconds = ttl_seconds
    self._cache = {}
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
    if scene_uid is None and source_id is None:
      self._cache.clear()
      return
    for key in list(self._cache.keys()):
      if (scene_uid is None or key[0] == scene_uid) and \
         (source_id is None or key[1] == source_id):
        self._cache.pop(key, None)
    return
