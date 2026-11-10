# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

from scene_common.options import (
  POSE_CLASS_CALIBRATION,
  POSE_CLASS_LIVE,
  POSE_CONFIGURED,
  POSE_OBSERVATION,
  POSE_ORIGIN_DETECTOR_EXTRINSICS,
  POSE_ORIGIN_MANAGER_REST,
  POSE_ORIGIN_UNKNOWN,
  make_pose_provenance,
  pose_is_live,
  provenance_from_camera_info,
  sync_legacy_pose_source,
)


def test_make_pose_provenance_optional_updated_at():
  assert make_pose_provenance(POSE_CLASS_LIVE, POSE_ORIGIN_DETECTOR_EXTRINSICS) == {
    'class': 'live', 'origin': 'detector.extrinsics',
  }
  stamped = make_pose_provenance(
    POSE_CLASS_CALIBRATION, POSE_ORIGIN_MANAGER_REST, updated_at='t0')
  assert stamped['updated_at'] == 't0'


def test_provenance_from_camera_info_prefers_pose_provenance():
  assert provenance_from_camera_info({})['origin'] == POSE_ORIGIN_UNKNOWN
  assert provenance_from_camera_info({
    'calibration_origin': 'manager.mesh',
  }) == {'class': 'calibration', 'origin': 'manager.mesh'}
  assert provenance_from_camera_info({
    'pose_provenance': {'class': 'live', 'origin': 'external_source'},
    'calibration_origin': 'manager.rest',
  }) == {'class': 'live', 'origin': 'external_source'}


def test_pose_is_live_uses_provenance_class_over_stale_pose_source():
  camera = SimpleNamespace(
    pose_provenance={'class': 'calibration', 'origin': 'manager.rest'},
    pose_source=POSE_OBSERVATION,
  )
  assert pose_is_live(camera) is False
  camera.pose_provenance = {'class': 'live', 'origin': 'detector.extrinsics'}
  camera.pose_source = POSE_CONFIGURED
  assert pose_is_live(camera) is True


def test_pose_is_live_falls_back_when_provenance_absent():
  assert pose_is_live(SimpleNamespace(pose_source=POSE_OBSERVATION)) is True
  assert pose_is_live(SimpleNamespace(pose_source=POSE_CONFIGURED)) is False


def test_sync_legacy_pose_source_follows_class():
  camera = SimpleNamespace(
    pose_provenance=make_pose_provenance(POSE_CLASS_LIVE, POSE_ORIGIN_DETECTOR_EXTRINSICS))
  sync_legacy_pose_source(camera)
  assert camera.pose_source == POSE_OBSERVATION
  camera.pose_provenance = make_pose_provenance(
    POSE_CLASS_CALIBRATION, POSE_ORIGIN_MANAGER_REST)
  sync_legacy_pose_source(camera)
  assert camera.pose_source == POSE_CONFIGURED
