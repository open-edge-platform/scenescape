#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for UUID/GID continuity across track occlusions (issue #1152).

These tests verify that when a tracked object temporarily disappears from the
scene (becomes suspended or unreliable in the tracker) and then reappears, the
controller assigns the same GID rather than minting a new one.

The key code path under test is IntelLabsTracking.from_tracked_object, which
must look up any existing GID in uuid_manager.active_ids when the incoming
tracked object has no matching entry in all_tracker_objects.
"""

import uuid as uuid_module
from unittest.mock import MagicMock, Mock, patch

import pytest


def _make_tracked_object(rv_id, obj_uuid=None):
  """Build a mock TrackedObject as returned by the C++ tracker.

  Returns a Mock whose .attributes['info'] carries a UUID string and whose
  .id carries the tracker-assigned integer track id.
  """
  if obj_uuid is None:
    obj_uuid = str(uuid_module.uuid4())
  tracked = Mock()
  tracked.id = rv_id
  tracked.attributes = {'info': obj_uuid}
  tracked.x = 1.0
  tracked.y = 2.0
  tracked.z = 0.0
  tracked.vx = 0.0
  tracked.vy = 0.0
  return tracked, obj_uuid


def _make_sscape_object(obj_uuid, rv_id=None):
  """Build a mock SceneScape detection object for use as tracker input."""
  obj = MagicMock()
  obj.uuid = obj_uuid
  obj.rv_id = rv_id
  obj.gid = None
  # Avoid exercising yaw/quaternion conversion in these GID-continuity tests.
  obj.has_detection_rotation = False
  obj.location = [MagicMock()]
  obj.location[0].point = MagicMock()
  return obj


@pytest.fixture
def ilabs_tracker():
  """
  Return an IntelLabsTracking instance with the C++ tracker fully mocked.

  The robot_vision extension is patched at module level so that the tracker
  constructor and all rv.tracking calls are replaced by MagicMocks.  The
  uuid_manager attribute (a real UUIDManager) and all_tracker_objects are
  left intact for per-test inspection and manipulation.
  """
  with patch('controller.ilabs_tracking.rv') as mock_rv:
    mock_rv.tracking.TrackManagerConfig.return_value = MagicMock()
    mock_rv.tracking.MotionModel = MagicMock()
    mock_rv.tracking.MultipleObjectTracker.return_value = MagicMock()
    mock_rv.tracking.DistanceType = MagicMock()

    from controller.ilabs_tracking import IntelLabsTracking

    tracker = IntelLabsTracking(
      max_unreliable_time=0.5,
      non_measurement_time_dynamic=1.0,
      non_measurement_time_static=2.0,
      effective_object_update_rate=30.0,
    )
    yield tracker


class TestGIDReuseAcrossOcclusion:
  """Tests for GID/UUID continuity when a track reappears after occlusion.

  The fix for #1152 ensures that IntelLabsTracking.from_tracked_object
  checks uuid_manager.active_ids for an existing GID before calling
  setGID with the raw UUID string.  This class verifies that contract.
  """

  def test_existing_gid_is_reused_when_rv_id_in_active_ids(self, ilabs_tracker):
    """GID from active_ids must be reused when an rv_id reappears.

    Simulates a static object that was tracked, went through a suspended
    period (disappearing from reliable_tracks), and has now returned.
    The uuid_manager still holds the original GID for that rv_id.
    """
    obj_uuid = str(uuid_module.uuid4())
    rv_id = 42
    original_gid = "gid-from-previous-appearance"

    # Pre-populate active_ids to simulate the suspended-but-retained mapping
    with ilabs_tracker.uuid_manager.active_ids_lock:
      ilabs_tracker.uuid_manager.active_ids[rv_id] = [original_gid, None]

    tracked_obj, _ = _make_tracked_object(rv_id, obj_uuid)
    sscape_obj = _make_sscape_object(obj_uuid)
    sscape_obj.setGID = Mock()

    # all_tracker_objects is empty: this is a "not found" path (reappearance)
    ilabs_tracker.all_tracker_objects = []

    ilabs_tracker.from_tracked_object(tracked_obj, [sscape_obj])

    sscape_obj.setGID.assert_called_once_with(original_gid), \
      "Existing GID from active_ids must be reused for a returning rv_id"

  def test_uuid_used_as_gid_when_rv_id_not_in_active_ids(self, ilabs_tracker):
    """When rv_id has no existing active_ids entry, the UUID must be used as initial GID.

    This is the normal first-appearance path: the object has never been seen
    before so no GID has been assigned yet, and setGID should receive the
    UUID string carried by the tracked object attributes.
    """
    obj_uuid = str(uuid_module.uuid4())
    rv_id = 99

    # Ensure active_ids has no entry for this rv_id
    with ilabs_tracker.uuid_manager.active_ids_lock:
      ilabs_tracker.uuid_manager.active_ids.pop(rv_id, None)

    tracked_obj, _ = _make_tracked_object(rv_id, obj_uuid)
    sscape_obj = _make_sscape_object(obj_uuid)
    sscape_obj.setGID = Mock()
    ilabs_tracker.all_tracker_objects = []

    ilabs_tracker.from_tracked_object(tracked_obj, [sscape_obj])

    sscape_obj.setGID.assert_called_once_with(obj_uuid), \
      "UUID from tracked object must be used as GID when rv_id is brand new"

  def test_none_gid_in_active_ids_falls_back_to_uuid(self, ilabs_tracker):
    """When active_ids holds [None, None] for rv_id, the UUID must be used as GID.

    This happens when the track was seen before but the UUID query has not
    completed yet (active_ids is initialised to [None, None] by assignID).
    """
    obj_uuid = str(uuid_module.uuid4())
    rv_id = 77

    with ilabs_tracker.uuid_manager.active_ids_lock:
      ilabs_tracker.uuid_manager.active_ids[rv_id] = [None, None]

    tracked_obj, _ = _make_tracked_object(rv_id, obj_uuid)
    sscape_obj = _make_sscape_object(obj_uuid)
    sscape_obj.setGID = Mock()
    ilabs_tracker.all_tracker_objects = []

    ilabs_tracker.from_tracked_object(tracked_obj, [sscape_obj])

    sscape_obj.setGID.assert_called_once_with(obj_uuid), \
      "UUID must be used as GID when existing active_ids entry has None GID"

  def test_gid_not_changed_when_previous_object_found_in_all_tracker_objects(self, ilabs_tracker):
    """When a previous object is found in all_tracker_objects, setPrevious is used instead.

    The GID reuse path (active_ids lookup) is only reached when the object
    is NOT found in all_tracker_objects.  This test confirms the found path
    does not call setGID.
    """
    obj_uuid = str(uuid_module.uuid4())
    rv_id = 55
    previous_gid = "gid-from-previous-frame"

    tracked_obj, _ = _make_tracked_object(rv_id, obj_uuid)

    sscape_obj = _make_sscape_object(obj_uuid)
    sscape_obj.setGID = Mock()
    sscape_obj.rv_id = rv_id

    # Build a previous object with the same rv_id (as if seen in prior frame)
    prev_obj = MagicMock()
    prev_obj.rv_id = rv_id
    prev_obj.gid = previous_gid
    ilabs_tracker.all_tracker_objects = [prev_obj]

    ilabs_tracker.from_tracked_object(tracked_obj, [sscape_obj])

    sscape_obj.setGID.assert_not_called(), \
      "setGID must not be called when object is found via all_tracker_objects"
    sscape_obj.setPrevious.assert_called_once_with(prev_obj), \
      "setPrevious must be called when matching previous object is found"
