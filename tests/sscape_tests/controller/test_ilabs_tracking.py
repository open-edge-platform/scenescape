# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from controller.ilabs_tracking import IntelLabsTracking


def _make_tracker():
  tracker = IntelLabsTracking.__new__(IntelLabsTracking)
  tracker.uuid_manager = SimpleNamespace(active_ids={}, assignID=Mock())
  tracker.all_tracker_objects = []
  return tracker


class TestIntelLabsTrackingFromTrackedObject(unittest.TestCase):

  def test_uses_previous_track_when_rv_id_matches(self):
    tracker = _make_tracker()
    prev_obj = SimpleNamespace(rv_id=10, uuid="prev")
    tracker.all_tracker_objects = [prev_obj]

    current_obj = SimpleNamespace(
        uuid="obj-1",
        location=[SimpleNamespace(point=None)],
        velocity=None,
        rv_id=None,
        setPrevious=Mock(),
        inferRotationFromVelocity=Mock(),
        setGID=Mock()
    )
    tracked_object = SimpleNamespace(
        id=10, x=1.0, y=2.0, z=3.0, vx=0.1, vy=0.2,
        attributes={"info": "obj-1"}
    )

    out = tracker.from_tracked_object(tracked_object, [current_obj])

    self.assertIs(out, current_obj)
    current_obj.setPrevious.assert_called_once_with(prev_obj)
    current_obj.inferRotationFromVelocity.assert_called_once()
    current_obj.setGID.assert_not_called()
    tracker.uuid_manager.assignID.assert_called_once_with(current_obj)
    self.assertEqual(current_obj.location[0].point.x, 1.0)
    self.assertEqual(current_obj.velocity.x, 0.1)

  def test_returns_existing_tracker_object_when_not_in_current_frame(self):
    tracker = _make_tracker()
    existing = SimpleNamespace(uuid="obj-2")
    tracker.all_tracker_objects = [existing]

    tracked_object = SimpleNamespace(
        id=22, x=0.0, y=0.0, z=0.0, vx=0.0, vy=0.0,
        attributes={"info": "obj-2"}
    )

    out = tracker.from_tracked_object(tracked_object, [])
    self.assertIs(out, existing)
    tracker.uuid_manager.assignID.assert_not_called()

  def test_preserves_existing_gid_mapping(self):
    tracker = _make_tracker()
    tracker.uuid_manager.active_ids = {33: ["gid-33", None]}

    current_obj = SimpleNamespace(
        uuid="obj-3",
        location=[SimpleNamespace(point=None)],
        velocity=None,
        rv_id=None,
        setPrevious=Mock(),
        inferRotationFromVelocity=Mock(),
        setGID=Mock()
    )
    tracked_object = SimpleNamespace(
        id=33, x=4.0, y=5.0, z=6.0, vx=0.3, vy=0.4,
        attributes={"info": "obj-3"}
    )

    out = tracker.from_tracked_object(tracked_object, [current_obj])
    self.assertIs(out, current_obj)
    current_obj.setPrevious.assert_not_called()
    current_obj.setGID.assert_called_once_with("gid-33")
    tracker.uuid_manager.assignID.assert_called_once_with(current_obj)

  def test_returns_none_when_uuid_not_found(self):
    tracker = _make_tracker()
    tracked_object = SimpleNamespace(
        id=99, x=0.0, y=0.0, z=0.0, vx=0.0, vy=0.0,
        attributes={"info": "missing"}
    )
    out = tracker.from_tracked_object(tracked_object, [])
    self.assertIsNone(out)
    tracker.uuid_manager.assignID.assert_not_called()


class TestTrackCategoryIncludesSuspendedTracksInPrune(unittest.TestCase):
  """Verifies the fix in trackCategory/trackCategoryBatched: pruneInactiveTracks
  is called with reliable + unreliable + suspended tracks so that UUID mappings
  for occluded static objects are preserved (commit f4d8d7f)."""

  def _make_tracked(self, rv_id):
    return SimpleNamespace(id=rv_id)

  def _build_tracker_mock(self, reliable, unreliable, suspended):
    tracker = Mock()
    tracker.get_reliable_tracks.return_value = reliable
    tracker.get_unreliable_tracks.return_value = unreliable
    tracker.get_suspended_tracks.return_value = suspended
    return tracker

  def test_track_category_passes_all_track_states_to_prune(self):
    """trackCategory includes unreliable and suspended tracks in the prune set."""
    reliable = [self._make_tracked(1)]
    unreliable = [self._make_tracked(2)]
    suspended = [self._make_tracked(3)]

    itracking = IntelLabsTracking.__new__(IntelLabsTracking)
    itracking.tracker = self._build_tracker_mock(reliable, unreliable, suspended)
    itracking.uuid_manager = Mock()
    itracking.uuid_manager.active_ids = {}
    itracking.all_tracker_objects = []
    itracking.already_tracked_objects = []

    with patch.object(itracking, '_assert_owner_thread'):
      with patch.object(itracking, 'update_tracks'):
        with patch.object(itracking, 'mergeAlreadyTrackedObjects', return_value=[]):
          with patch.object(itracking, 'from_tracked_object', return_value=None):
            itracking.trackCategory([], 0.0, [])

    pruned_with = itracking.uuid_manager.pruneInactiveTracks.call_args[0][0]
    pruned_ids = {obj.id for obj in pruned_with}
    self.assertIn(1, pruned_ids, "Reliable track must be in prune set")
    self.assertIn(2, pruned_ids, "Unreliable track must be in prune set")
    self.assertIn(3, pruned_ids, "Suspended track must be in prune set")

  def test_track_category_batched_passes_all_track_states_to_prune(self):
    """trackCategoryBatched includes unreliable and suspended tracks in the prune set."""
    reliable = [self._make_tracked(10)]
    unreliable = [self._make_tracked(20)]
    suspended = [self._make_tracked(30)]

    itracking = IntelLabsTracking.__new__(IntelLabsTracking)
    itracking.tracker = self._build_tracker_mock(reliable, unreliable, suspended)
    itracking.uuid_manager = Mock()
    itracking.uuid_manager.active_ids = {}
    itracking.all_tracker_objects = []
    itracking.already_tracked_objects = []

    with patch.object(itracking, '_assert_owner_thread'):
      with patch.object(itracking, 'update_tracks_batched'):
        with patch.object(itracking, 'mergeAlreadyTrackedObjects', return_value=[]):
          with patch.object(itracking, '_from_tracked_object_indexed', return_value=None):
            itracking.trackCategoryBatched([[]], 0.0, [])

    pruned_with = itracking.uuid_manager.pruneInactiveTracks.call_args[0][0]
    pruned_ids = {obj.id for obj in pruned_with}
    self.assertIn(10, pruned_ids, "Reliable track must be in prune set")
    self.assertIn(20, pruned_ids, "Unreliable track must be in prune set")
    self.assertIn(30, pruned_ids, "Suspended track must be in prune set")
