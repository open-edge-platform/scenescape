#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
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
from controller.scene_controller import SceneController
from scene_common.earth_lla import calculateTRSLocal2LLAFromSurfacePoints
from scene_common.transform import CameraPose


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

  def test_trusted_scene_pose_defaults_missing_rotation_to_identity(self):
    """Rotation is optional; omitted poses use identity quaternion."""
    cache = ExternalSourcePoseCache()
    scene = _makeScene()
    pose_data = {
      'reference_frame': 'scene',
      'translation': [1.0, 2.0, 3.0],
    }

    camera_pose, reason = cache.resolve(
      scene, 'drone-1', pose_data, when=100.0, trusted_scene_pose=True)

    assert reason is None
    assert camera_pose is not None
    np.testing.assert_allclose(camera_pose.pose_mat[:3, 3], [1.0, 2.0, 3.0])


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

  def test_sweep_evicts_expired_pose_behind_live_pose(self):
    cache = ExternalSourcePoseCache(ttl_seconds=30.0, sweep_chunk_size=2)
    scene = _makeScene()
    pose_data = {
      'reference_frame': 'scene',
      'translation': [5.0, 6.0, 0.0],
      'rotation': IDENTITY_ROTATION,
    }
    cache.resolve(scene, 'newer', pose_data, when=105.0, trusted_scene_pose=True)
    cache.resolve(scene, 'older', pose_data, when=95.0, trusted_scene_pose=True)

    assert cache.sweepExpired(131.0) == 1

    camera_pose, reason = cache.resolve(scene, 'older', None, when=120.0)
    assert camera_pose is None
    assert reason == REASON_NO_POSE_AVAILABLE
    camera_pose, reason = cache.resolve(scene, 'newer', None, when=131.0)
    assert camera_pose is not None
    assert reason is None

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

  def test_scenes_with_live_cache_lists_non_expired_scenes_for_source(self):
    cache = ExternalSourcePoseCache(ttl_seconds=30.0)
    scene_a = _makeScene(uid='scene-a')
    scene_b = _makeScene(uid='scene-b')
    pose_data = {
      'reference_frame': 'scene',
      'translation': [1.0, 0.0, 0.0],
      'rotation': IDENTITY_ROTATION,
    }
    cache.resolve(scene_a, 'drone-1', pose_data, when=100.0, trusted_scene_pose=True)
    cache.resolve(scene_b, 'drone-1', pose_data, when=100.0, trusted_scene_pose=True)
    cache.resolve(scene_a, 'other', pose_data, when=100.0, trusted_scene_pose=True)

    assert set(cache.scenesWithLiveCache('drone-1', when=110.0)) == {'scene-a', 'scene-b'}
    assert cache.scenesWithLiveCache('drone-1', when=200.0) == []
    assert cache.scenesWithLiveCache('missing', when=110.0) == []


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

  def test_sweep_evicts_expired_claim_behind_live_claim(self):
    registry = IdentityClaimRegistry(ttl_seconds=30.0, sweep_chunk_size=2)
    registry.claim('scene-1', 'person', 'source-a', 'newer', when=105.0)
    registry.claim('scene-1', 'person', 'source-a', 'older', when=95.0)

    assert registry.sweepExpired(131.0) == 1

    ok, reason = registry.claim('scene-1', 'person', 'source-b', 'older', when=120.0)
    assert ok is True
    assert reason is None
    ok, reason = registry.claim('scene-1', 'person', 'source-b', 'newer', when=131.0)
    assert ok is False
    assert reason == REASON_IDENTITY_COLLISION

  def test_out_of_order_same_source_claim_preserves_newer_expiry(self):
    registry = IdentityClaimRegistry(ttl_seconds=30.0)
    registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=100.0)
    registry.claim('scene-1', 'person', 'source-a', 'tag-1', when=96.0)

    ok, reason = registry.claim('scene-1', 'person', 'source-b', 'tag-1', when=128.0)

    assert ok is False
    assert reason == REASON_IDENTITY_COLLISION

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


class TestExternalSourceSweepLifecycle:
  """Background sweep callbacks must not survive a stop/start cycle."""

  @pytest.mark.parametrize(
    'factory',
    [
      lambda: ExternalSourcePoseCache(sweep_interval_seconds=60.0),
      lambda: IdentityClaimRegistry(sweep_interval_seconds=60.0),
    ],
    ids=['pose-cache', 'identity-claims'])
  def test_stopped_callback_does_not_schedule_after_restart(self, factory):
    cache = factory()
    cache.startBackgroundSweep()
    stopped_event = cache._sweep_stop
    cache.stopBackgroundSweep()
    cache.startBackgroundSweep()
    restarted_timer = cache._sweep_timer

    cache._sweepTick(stopped_event)

    assert cache._sweep_timer is restarted_timer
    cache.stopBackgroundSweep()

  def test_tick_stops_after_one_full_chunked_pass(self):
    registry = IdentityClaimRegistry(
      sweep_chunk_size=2, sweep_interval_seconds=60.0, sweep_time_provider=lambda: 0.0)
    for obj_id in range(4):
      registry.claim('scene-1', 'person', 'source-a', str(obj_id), when=0.0)
    stop_event = threading.Event()
    registry._sweep_stop = stop_event

    registry._sweepTick(stop_event)

    assert registry._sweep_timer is not None
    registry.stopBackgroundSweep()


class TestExternalSourceTrackRouting:
  def _makeController(self):
    controller = SceneController.__new__(SceneController)
    controller.external_source_pose_cache = MagicMock()
    controller.external_source_pose_cache.resolve.return_value = (
      CameraPose({'translation': [0.0, 0.0, 0.0],
                  'rotation': [0.0, 0.0, 0.0, 1.0],
                  'scale': [1.0, 1.0, 1.0]}, None), None)
    controller.identity_claim_registry = MagicMock()
    controller.identity_claim_registry.claim.return_value = (True, None)
    controller.trusted_positioning_sources = frozenset()
    controller.external_source_bindings = {}
    return controller

  @staticmethod
  def _makeScene():
    scene = MagicMock()
    scene.uid = 'scene-1'
    return scene

  def test_source_track_false_applies_to_all_objects_and_preserves_ids(self):
    controller = self._makeController()
    scene = self._makeScene()
    jdata = {
      'source_id': 'drone-1',
      'track': False,
      'objects': [
        {'id': 'obj-1', 'category': 'person', 'translation': [0, 0, 0]},
        {'id': 'obj-2', 'category': 'person', 'translation': [1, 0, 0]},
      ],
    }

    controller._handleExternalSourceObject(scene, jdata, 'person', 10.0)

    assert scene.processSceneData.call_count == 1
    routed_jdata, source_ns = scene.processSceneData.call_args[0][0], scene.processSceneData.call_args[0][1]
    assert [obj['id'] for obj in routed_jdata['objects']] == ['obj-1', 'obj-2']
    assert all('track' not in obj for obj in routed_jdata['objects'])
    assert source_ns.retrack is False
    assert [claim.args for claim in controller.identity_claim_registry.claim.call_args_list] == [
      ('scene-1', 'person', 'drone-1', 'obj-1', 10.0),
      ('scene-1', 'person', 'drone-1', 'obj-2', 10.0),
    ]

  def test_source_track_false_uses_passthrough(self):
    controller = self._makeController()
    scene = self._makeScene()
    jdata = {
      'source_id': 'drone-1',
      'track': False,
      'objects': [
        {'id': 'obj-1', 'category': 'person', 'translation': [0, 0, 0]},
      ],
    }

    controller._handleExternalSourceObject(scene, jdata, 'person', 10.0)

    routed_jdata, source_ns = scene.processSceneData.call_args[0][0], scene.processSceneData.call_args[0][1]
    assert routed_jdata['objects'][0]['id'] == 'obj-1'
    assert source_ns.retrack is False

  def test_tracked_object_without_id_gets_controller_local_placeholder(self):
    controller = self._makeController()
    scene = self._makeScene()
    jdata = {
      'source_id': 'drone-1',
      'objects': [
        {'category': 'person', 'translation': [0, 0, 0]},
      ],
    }

    controller._handleExternalSourceObject(scene, jdata, 'person', 10.0)

    routed_jdata, source_ns = scene.processSceneData.call_args[0][0], scene.processSceneData.call_args[0][1]
    assert routed_jdata['objects'][0]['id'] == 'tracked:drone-1:person:0'
    assert source_ns.retrack is True
    controller.identity_claim_registry.claim.assert_not_called()
    assert 'track' not in routed_jdata

  def test_source_track_true_uses_tracked_path_for_all_objects(self):
    controller = self._makeController()
    scene = self._makeScene()
    jdata = {
      'source_id': 'drone-1',
      'track': True,
      'objects': [
        {'id': 'obj-1', 'category': 'person', 'translation': [0, 0, 0]},
      ],
    }

    controller._handleExternalSourceObject(scene, jdata, 'person', 10.0)

    assert scene.processSceneData.call_count == 1
    routed_jdata, source_ns = scene.processSceneData.call_args[0][0], scene.processSceneData.call_args[0][1]
    assert source_ns.retrack is True
    assert routed_jdata['objects'][0]['id'] == 'tracked:drone-1:person:obj-1'
    controller.identity_claim_registry.claim.assert_not_called()

  def test_tracked_objects_with_source_ids_use_stable_tracking_hints(self):
    controller = self._makeController()
    scene = self._makeScene()
    jdata = {
      'source_id': 'drone-1',
      'objects': [
        {'id': 'obj-1', 'category': 'person', 'translation': [0, 0, 0]},
        {'id': 'obj-2', 'category': 'person', 'translation': [1, 0, 0]},
      ],
    }

    controller._handleExternalSourceObject(scene, jdata, 'person', 10.0)

    routed_jdata = scene.processSceneData.call_args[0][0]
    assert [obj['id'] for obj in routed_jdata['objects']] == [
      'tracked:drone-1:person:obj-1',
      'tracked:drone-1:person:obj-2',
    ]

  def test_duplicate_tracked_source_ids_do_not_use_id_hint(self):
    controller = self._makeController()
    scene = self._makeScene()
    jdata = {
      'source_id': 'drone-1',
      'objects': [
        {'id': 'obj-1', 'category': 'person', 'translation': [0, 0, 0]},
        {'id': 'obj-1', 'category': 'person', 'translation': [1, 0, 0]},
      ],
    }

    controller._handleExternalSourceObject(scene, jdata, 'person', 10.0)

    routed_jdata = scene.processSceneData.call_args[0][0]
    assert [obj['id'] for obj in routed_jdata['objects']] == [
      'tracked:drone-1:person:0',
      'tracked:drone-1:person:1',
    ]

  def test_pixel_detection_forces_tracking_through_camera_path(self):
    controller = self._makeController()
    scene = self._makeScene()
    pixel_pose = CameraPose({'translation': [1.0, 2.0, 3.0],
                             'rotation': [0.0, 0.0, 0.0, 1.0],
                             'scale': [1.0, 1.0, 1.0]}, None)
    controller.external_source_pose_cache.resolve.return_value = (pixel_pose, None)
    jdata = {
      'source_id': 'drone-1',
      'track': False,
      'pose': {
        'reference_frame': 'scene',
        'translation': [1.0, 2.0, 3.0],
        'rotation': IDENTITY_ROTATION,
      },
      'intrinsics': {'fx': 905.0, 'fy': 905.0, 'cx': 640.0, 'cy': 360.0},
      'objects': [
        {
          'id': 'obj-1',
          'category': 'person',
          'bounding_box_px': {'x': 221, 'y': 157, 'width': 108, 'height': 259},
        },
      ],
    }

    controller._handleExternalSourceObject(scene, jdata, 'person', 10.0)

    scene.processSceneData.assert_not_called()
    detection_type, routed_objects, when, pixel_camera = \
      scene._createMovingObjectsForDetection.call_args[0]
    assert detection_type == 'person'
    assert routed_objects[0]['id'] == 'tracked:drone-1:person:obj-1'
    assert routed_objects[0]['bounding_box_px']['x'] == 221
    assert routed_objects[0]['bounding_box_px']['y'] == 157
    assert 'translation' not in routed_objects[0]
    assert when == 10.0
    assert pixel_camera.pose.intrinsics is not None
    scene._finishProcessing.assert_called_once()
    controller.identity_claim_registry.claim.assert_not_called()

  def test_pixel_detection_missing_intrinsics_is_discarded(self):
    controller = self._makeController()
    scene = self._makeScene()
    jdata = {
      'source_id': 'drone-1',
      'pose': {
        'reference_frame': 'scene',
        'translation': [1.0, 2.0, 3.0],
        'rotation': IDENTITY_ROTATION,
      },
      'objects': [
        {
          'category': 'person',
          'bounding_box_px': {'x': 221, 'y': 157, 'width': 108, 'height': 259},
        },
      ],
    }

    controller._handleExternalSourceObject(scene, jdata, 'person', 10.0)

    scene.processSceneData.assert_not_called()

  def test_mixed_translation_and_pixel_objects_use_their_native_paths(self):
    controller = self._makeController()
    scene = self._makeScene()
    pixel_moving_object = object()
    translation_moving_object = object()
    scene._createMovingObjectsForDetection.return_value = [pixel_moving_object]
    scene._createMovingObjectsForSceneData.return_value = (
      [],
      [translation_moving_object],
    )
    pixel_pose = CameraPose({'translation': [1.0, 2.0, 3.0],
                             'rotation': [0.0, 0.0, 0.0, 1.0],
                             'scale': [1.0, 1.0, 1.0]}, None)
    controller.external_source_pose_cache.resolve.return_value = (pixel_pose, None)
    jdata = {
      'source_id': 'drone-1',
      'track': False,
      'pose': {
        'reference_frame': 'scene',
        'translation': [1.0, 2.0, 3.0],
        'rotation': IDENTITY_ROTATION,
      },
      'intrinsics': {'fx': 905.0, 'fy': 905.0, 'cx': 640.0, 'cy': 360.0},
      'objects': [
        {'id': 'obj-translation', 'category': 'person', 'translation': [0, 0, 0]},
        {
          'id': 'obj-pixel',
          'category': 'person',
          'bounding_box_px': {'x': 221, 'y': 157, 'width': 108, 'height': 259},
        },
      ],
    }

    controller._handleExternalSourceObject(scene, jdata, 'person', 10.0)

    scene.processSceneData.assert_not_called()
    routed_jdata, source_ns, camera_pose = \
      scene._createMovingObjectsForSceneData.call_args[0][:3]
    assert [obj['id'] for obj in routed_jdata['objects']] == ['obj-translation']
    assert source_ns.retrack is False
    assert camera_pose.intrinsics is None

    pixel_objects = scene._createMovingObjectsForDetection.call_args[0][1]
    pixel_camera = scene._createMovingObjectsForDetection.call_args[0][3]
    assert pixel_objects[0]['id'] == 'tracked:drone-1:person:obj-pixel'
    assert 'translation' not in pixel_objects[0]
    assert pixel_camera.pose.intrinsics is not None
    scene._finishProcessing.assert_called_once_with(
      'person',
      10.0,
      [pixel_moving_object],
      [translation_moving_object],
    )
