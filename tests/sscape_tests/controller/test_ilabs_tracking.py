# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from controller.ilabs_tracking import IntelLabsTracking


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
          with patch.object(itracking, '_from_tracked_objects', return_value=[]):
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
          with patch.object(itracking, '_from_tracked_objects', return_value=[]):
            itracking.trackCategoryBatched([[]], 0.0, [])

    pruned_with = itracking.uuid_manager.pruneInactiveTracks.call_args[0][0]
    pruned_ids = {obj.id for obj in pruned_with}
    self.assertIn(10, pruned_ids, "Reliable track must be in prune set")
    self.assertIn(20, pruned_ids, "Unreliable track must be in prune set")
    self.assertIn(30, pruned_ids, "Suspended track must be in prune set")
