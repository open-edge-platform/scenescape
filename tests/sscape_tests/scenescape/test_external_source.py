#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest
from types import SimpleNamespace

from controller.external_source import (
  ExternalSourcePoseCache,
  IdentityClaimRegistry,
  REASON_IDENTITY_COLLISION,
  REASON_INVALID_POSE,
  REASON_NO_POSE_AVAILABLE,
  REASON_POSE_EXPIRED,
  REASON_SCENE_GEOREFERENCE_UNAVAILABLE,
  REASON_UNSUPPORTED_REFERENCE_FRAME,
  REASON_UNTRUSTED_SCENE_POSE,
)
from scene_common.earth_lla import calculateTRSLocal2LLAFromSurfacePoints


def _makeScene(uid="scene-1", trs_xyz_to_lla=None):
  return SimpleNamespace(uid=uid, trs_xyz_to_lla=trs_xyz_to_lla)


IDENTITY_ROTATION = [0.0, 0.0, 0.0, 1.0]


class TestExternalSourcePoseCacheSceneFrame:
  """Poses expressed directly in scene-local coordinates require trust."""

  def test_trusted_scene_pose_is_resolved(self):
    cache = ExternalSourcePoseCache()
    scene = _makeScene()
    pose_data = {
      'reference_frame': 'scene',
      'translation': [1.0, 2.0, 3.0],
      'rotation': IDENTITY_ROTATION,
    }

    camera_pose, reason = cache.resolve(
      scene, 'positioning-service-1', pose_data, when=100.0, trusted_scene_pose=True)

    assert reason is None
    assert camera_pose is not None
    np.testing.assert_allclose(camera_pose.pose_mat[:3, 3], [1.0, 2.0, 3.0])

  def test_untrusted_scene_pose_is_rejected(self):
    cache = ExternalSourcePoseCache()
    scene = _makeScene()
    pose_data = {
      'reference_frame': 'scene',
      'translation': [1.0, 2.0, 3.0],
      'rotation': IDENTITY_ROTATION,
    }

    camera_pose, reason = cache.resolve(
      scene, 'random-agent', pose_data, when=100.0, trusted_scene_pose=False)

    assert camera_pose is None
    assert reason == REASON_UNTRUSTED_SCENE_POSE

  def test_missing_translation_is_invalid(self):
    cache = ExternalSourcePoseCache()
    scene = _makeScene()
    pose_data = {'reference_frame': 'scene', 'rotation': IDENTITY_ROTATION}

    camera_pose, reason = cache.resolve(
      scene, 'svc', pose_data, when=100.0, trusted_scene_pose=True)

    assert camera_pose is None
    assert reason == REASON_INVALID_POSE


class TestExternalSourcePoseCacheWgs84Frame:
  """Global poses require the target scene to be geospatially calibrated."""

  def test_wgs84_pose_without_georeference_is_rejected(self):
    cache = ExternalSourcePoseCache()
    scene = _makeScene(trs_xyz_to_lla=None)
    pose_data = {
      'reference_frame': 'wgs84',
      'lat_long_alt': [37.4, -122.1, 10.0],
      'rotation': IDENTITY_ROTATION,
    }

    camera_pose, reason = cache.resolve(
      scene, 'drone-1', pose_data, when=100.0)

    assert camera_pose is None
    assert reason == REASON_SCENE_GEOREFERENCE_UNAVAILABLE

  def test_wgs84_pose_roundtrips_through_scene_calibration(self):
    # Same 4-corner geospatial calibration fixture used and verified (to
    # rtol=1e-8) by tests/functional/test_geospatial_ingest_publish.py.
    map_corners_lla = [
      [37.38685435, -121.96408120, 8.0], [37.38693520, -121.96408120, 8.0],
      [37.38693520, -121.96413896, 8.0], [37.38685435, -121.96413896, 8.0],
    ]
    map_resolution = [900, 643]
    map_scale = 100.0
    map_xyz_pts = [
      [0, 0, 0],
      [map_resolution[0] / map_scale, 0, 0],
      [map_resolution[0] / map_scale, map_resolution[1] / map_scale, 0],
      [0, map_resolution[1] / map_scale, 0],
    ]
    detection_xyz = [3.8679791719486474, 2.7517397452609087, 1.1225254457301852e-19]
    expected_detection_lla = [37.38688947231117, -121.96410520894621, 8.068826778282563]

    trs_xyz_to_lla = calculateTRSLocal2LLAFromSurfacePoints(map_xyz_pts, map_corners_lla)
    scene = _makeScene(trs_xyz_to_lla=trs_xyz_to_lla)

    cache = ExternalSourcePoseCache()
    pose_data = {
      'reference_frame': 'wgs84',
      'lat_long_alt': expected_detection_lla,
      'rotation': IDENTITY_ROTATION,
    }

    camera_pose, reason = cache.resolve(scene, 'drone-1', pose_data, when=100.0)

    assert reason is None
    assert camera_pose is not None
    np.testing.assert_allclose(camera_pose.pose_mat[:3, 3], detection_xyz, atol=1e-3)

  def test_unsupported_reference_frame_is_rejected(self):
    cache = ExternalSourcePoseCache()
    scene = _makeScene()
    pose_data = {'reference_frame': 'ecef', 'rotation': IDENTITY_ROTATION}

    camera_pose, reason = cache.resolve(scene, 'drone-1', pose_data, when=100.0)

    assert camera_pose is None
    assert reason == REASON_UNSUPPORTED_REFERENCE_FRAME


class TestExternalSourcePoseCacheReuse:
  """A message without 'pose' reuses the most recent non-expired transform."""

  def test_no_pose_with_no_prior_cache_is_rejected(self):
    cache = ExternalSourcePoseCache()
    scene = _makeScene()

    camera_pose, reason = cache.resolve(scene, 'drone-1', None, when=100.0)

    assert camera_pose is None
    assert reason == REASON_NO_POSE_AVAILABLE

  def test_no_pose_reuses_cached_transform(self):
    cache = ExternalSourcePoseCache(ttl_seconds=30.0)
    scene = _makeScene()
    pose_data = {
      'reference_frame': 'scene',
      'translation': [5.0, 6.0, 0.0],
      'rotation': IDENTITY_ROTATION,
    }
    cache.resolve(scene, 'drone-1', pose_data, when=100.0, trusted_scene_pose=True)

    camera_pose, reason = cache.resolve(scene, 'drone-1', None, when=110.0)

    assert reason is None
    np.testing.assert_allclose(camera_pose.pose_mat[:3, 3], [5.0, 6.0, 0.0])

  def test_cached_transform_expires_after_ttl(self):
    cache = ExternalSourcePoseCache(ttl_seconds=5.0)
    scene = _makeScene()
    pose_data = {
      'reference_frame': 'scene',
      'translation': [5.0, 6.0, 0.0],
      'rotation': IDENTITY_ROTATION,
    }
    cache.resolve(scene, 'drone-1', pose_data, when=100.0, trusted_scene_pose=True)

    camera_pose, reason = cache.resolve(scene, 'drone-1', None, when=200.0)

    assert camera_pose is None
    assert reason == REASON_POSE_EXPIRED

  def test_sweep_keeps_pose_for_accepted_delayed_message(self):
    cache = ExternalSourcePoseCache(ttl_seconds=30.0, sweep_grace_seconds=5.0)
    scene = _makeScene()
    pose_data = {
      'reference_frame': 'scene',
      'translation': [5.0, 6.0, 0.0],
      'rotation': IDENTITY_ROTATION,
    }
    cache.resolve(scene, 'drone-1', pose_data, when=100.0, trusted_scene_pose=True)

    assert cache.sweepExpired(130.1) == 0

    camera_pose, reason = cache.resolve(scene, 'drone-1', None, when=129.9)
    assert reason is None
    assert camera_pose is not None
    assert cache.sweepExpired(135.1) == 1

  def test_out_of_order_pose_update_keeps_newer_cached_transform(self):
    cache = ExternalSourcePoseCache(ttl_seconds=30.0)
    scene = _makeScene()
    newer_pose = {
      'reference_frame': 'scene',
      'translation': [9.0, 9.0, 0.0],
      'rotation': IDENTITY_ROTATION,
    }
    stale_pose = {
      'reference_frame': 'scene',
      'translation': [1.0, 1.0, 0.0],
      'rotation': IDENTITY_ROTATION,
    }
    cache.resolve(scene, 'drone-1', newer_pose, when=100.0, trusted_scene_pose=True)

    camera_pose, reason = cache.resolve(
      scene, 'drone-1', stale_pose, when=90.0, trusted_scene_pose=True)

    assert reason is None
    np.testing.assert_allclose(camera_pose.pose_mat[:3, 3], [9.0, 9.0, 0.0])


class TestIdentityClaimRegistry:
  """Unit tests for IdentityClaimRegistry, the collision-detection safety net
  behind default (no-allowlist-required) trust of external-source ids."""

  def test_first_claim_on_an_id_succeeds(self):
    registry = IdentityClaimRegistry()

    ok, reason = registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=10.0)

    assert ok is True
    assert reason is None

  def test_same_source_reclaiming_same_id_succeeds(self):
    registry = IdentityClaimRegistry()
    registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=10.0)

    ok, reason = registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=11.0)

    assert ok is True
    assert reason is None

  def test_different_source_claiming_live_id_is_rejected(self):
    registry = IdentityClaimRegistry()
    registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=10.0)

    ok, reason = registry.claim('scene-1', 'person', 'source-b', 'tag-1', when=11.0)

    assert ok is False
    assert reason == REASON_IDENTITY_COLLISION

  def test_different_source_can_reclaim_after_ttl_expires(self):
    registry = IdentityClaimRegistry(ttl_seconds=5.0)
    registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=10.0)

    ok, reason = registry.claim('scene-1', 'person', 'source-b', 'tag-1', when=20.0)

    assert ok is True
    assert reason is None

  def test_sweep_keeps_claim_for_accepted_delayed_message(self):
    registry = IdentityClaimRegistry(ttl_seconds=30.0, sweep_grace_seconds=5.0)
    registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=100.0)

    assert registry.sweepExpired(130.1) == 0

    ok, reason = registry.claim('scene-1', 'person', 'source-b', 'tag-1', when=129.9)
    assert ok is False
    assert reason == REASON_IDENTITY_COLLISION
    assert registry.sweepExpired(135.1) == 1

  def test_same_id_in_different_scenes_does_not_collide(self):
    registry = IdentityClaimRegistry()
    registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=10.0)

    ok, reason = registry.claim('scene-2', 'person', 'source-b', 'tag-1', when=10.0)

    assert ok is True
    assert reason is None

  def test_same_id_in_different_categories_does_not_collide(self):
    registry = IdentityClaimRegistry()
    registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=10.0)

    ok, reason = registry.claim('scene-1', 'vehicle', 'source-b', 'tag-1', when=10.0)

    assert ok is True
    assert reason is None

  def test_invalidate_all_clears_every_claim(self):
    registry = IdentityClaimRegistry()
    registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=10.0)

    registry.invalidate()

    ok, reason = registry.claim('scene-1', 'person', 'source-b', 'tag-1', when=10.0)
    assert ok is True

  def test_invalidate_scoped_to_source_only_clears_that_sources_claims(self):
    registry = IdentityClaimRegistry()
    registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=10.0)
    registry.claim('scene-1', 'person', 'source-c', 'tag-2', when=10.0)

    registry.invalidate(source_id='source-a')

    # source-a's claim was cleared: a different source can now claim tag-1.
    ok, _ = registry.claim('scene-1', 'person', 'source-b', 'tag-1', when=11.0)
    assert ok is True
    # source-c's claim on tag-2 is untouched: a different source colliding is rejected.
    ok, reason = registry.claim('scene-1', 'person', 'source-d', 'tag-2', when=11.0)
    assert ok is False
    assert reason == REASON_IDENTITY_COLLISION

  def test_cache_is_keyed_per_scene_and_source(self):
    cache = ExternalSourcePoseCache()
    scene_a = _makeScene(uid='scene-a')
    scene_b = _makeScene(uid='scene-b')
    pose_data = {
      'reference_frame': 'scene',
      'translation': [1.0, 1.0, 0.0],
      'rotation': IDENTITY_ROTATION,
    }
    cache.resolve(scene_a, 'drone-1', pose_data, when=100.0, trusted_scene_pose=True)

    camera_pose, reason = cache.resolve(scene_b, 'drone-1', None, when=100.0)

    assert camera_pose is None
    assert reason == REASON_NO_POSE_AVAILABLE

  def test_invalidate_clears_cached_entry(self):
    cache = ExternalSourcePoseCache()
    scene = _makeScene()
    pose_data = {
      'reference_frame': 'scene',
      'translation': [1.0, 1.0, 0.0],
      'rotation': IDENTITY_ROTATION,
    }
    cache.resolve(scene, 'drone-1', pose_data, when=100.0, trusted_scene_pose=True)

    cache.invalidate(scene_uid=scene.uid, source_id='drone-1')
    camera_pose, reason = cache.resolve(scene, 'drone-1', None, when=100.0)

    assert camera_pose is None
    assert reason == REASON_NO_POSE_AVAILABLE
