# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for UUID preservation fixes in UUIDManager (commit f4d8d7f).

Verifies that:
1. pruneInactiveTracks retains UUID mappings for suspended/unreliable tracks.
2. assignID stores the generated GID in active_ids when re-ID is disabled or
   insufficient features are available (new else-branch).
"""

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock


def _make_uuid_manager():
  """Build a UUIDManager bypassing __init__ to avoid real DB/thread-pool."""
  from controller.uuid_manager import UUIDManager
  mgr = UUIDManager.__new__(UUIDManager)
  mgr.active_ids = {}
  mgr.active_ids_lock = threading.Lock()
  mgr.active_query = {}
  mgr.features_for_database = {}
  mgr.quality_features = {}
  mgr.unique_id_count = 0
  mgr.reid_enabled = True
  # Thread-pool stub — submit() calls the function synchronously for testing
  pool = MagicMock()
  pool.submit.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)
  mgr.pool = pool
  mgr.reid_database = MagicMock()
  mgr.similarity_query_times = []
  mgr.similarity_query_times_lock = threading.Lock()
  return mgr


def _make_sscape_object(rv_id, gid, reid_vector=None):
  return SimpleNamespace(
      rv_id=rv_id,
      gid=gid,
      reidVector=reid_vector,
      category="person",
      similarity=None,
      boundingBoxPixels=SimpleNamespace(area=0),
  )


def _make_tracked(rv_id):
  """Minimal tracked-object stub with just an id attribute."""
  class TrackedObject:
    def __init__(self, id_):
      self.id = id_

  return TrackedObject(rv_id)


class TestPruneInactiveTracksPreservesSuspendedUUIDs(unittest.TestCase):
  """Verifies the fix: pruneInactiveTracks must NOT remove UUID mappings for
  tracks that are suspended or unreliable (included in all_active_tracks)."""

  def test_suspended_track_uuid_is_preserved_when_included_in_active_set(self):
    """UUID for a suspended track stays in active_ids when that track is passed."""
    mgr = _make_uuid_manager()
    mgr.active_ids = {
        10: ["gid-reliable", None],
        20: ["gid-suspended", None],   # suspended track
    }
    reliable = [_make_tracked(10)]
    suspended = [_make_tracked(20)]

    # Simulate the fix: all_active_tracks = reliable + suspended
    all_active_tracks = reliable + suspended
    mgr.pruneInactiveTracks(all_active_tracks)

    self.assertIn(10, mgr.active_ids, "Reliable track UUID should be retained")
    self.assertIn(20, mgr.active_ids, "Suspended track UUID should be retained")

  def test_suspended_track_uuid_is_pruned_without_fix(self):
    """Without the fix (only reliable tracks passed), suspended UUID is removed."""
    mgr = _make_uuid_manager()
    mgr.active_ids = {
        10: ["gid-reliable", None],
        20: ["gid-suspended", None],
    }
    reliable_only = [_make_tracked(10)]

    # Old (pre-fix) behaviour: only reliable tracks passed to pruneInactiveTracks
    mgr.pruneInactiveTracks(reliable_only)

    self.assertIn(10, mgr.active_ids, "Reliable track UUID should be retained")
    self.assertNotIn(20, mgr.active_ids,
                     "Suspended track UUID should be pruned when not included")

  def test_unreliable_track_uuid_is_preserved_when_included(self):
    """UUID for an unreliable track stays when included in the active set."""
    mgr = _make_uuid_manager()
    mgr.active_ids = {30: ["gid-unreliable", None]}
    unreliable = [_make_tracked(30)]

    mgr.pruneInactiveTracks(unreliable)

    self.assertIn(30, mgr.active_ids, "Unreliable track UUID should be retained")

  def test_fully_gone_track_is_always_pruned(self):
    """A track absent from all categories is removed regardless."""
    mgr = _make_uuid_manager()
    mgr.active_ids = {
        10: ["gid-active", None],
        99: ["gid-gone", None],
    }
    mgr.pruneInactiveTracks([_make_tracked(10)])

    self.assertIn(10, mgr.active_ids)
    self.assertNotIn(99, mgr.active_ids)


class TestAssignIDStoresGIDWhenReidDisabled(unittest.TestCase):
  """Verifies the new else-branch in assignID: when re-ID is disabled (or
  insufficient features), the generated GID is stored in active_ids so that
  subsequent calls can retrieve the preserved UUID."""

  def test_gid_stored_in_active_ids_when_reid_disabled(self):
    """assignID stores sscape_object.gid in active_ids when reid_enabled=False."""
    mgr = _make_uuid_manager()
    mgr.reid_enabled = False

    obj = _make_sscape_object(rv_id=5, gid="stable-gid")
    mgr.assignID(obj)

    self.assertIn(5, mgr.active_ids,
                  "active_ids should contain an entry for rv_id after assignID")
    self.assertEqual(mgr.active_ids[5][0], "stable-gid",
                     "Stored GID must match the object's GID")

  def test_gid_stored_in_active_ids_when_insufficient_features(self):
    """assignID stores GID when reid is enabled but features are below threshold."""
    mgr = _make_uuid_manager()
    mgr.reid_enabled = True
    # No features gathered → haveSufficientVisualFeatures returns False

    obj = _make_sscape_object(rv_id=7, gid="stable-gid-2", reid_vector=None)
    mgr.assignID(obj)

    self.assertIn(7, mgr.active_ids)
    self.assertEqual(mgr.active_ids[7][0], "stable-gid-2")

  def test_existing_gid_not_overwritten_in_active_ids(self):
    """If active_ids already has a non-None GID for an rv_id, assignID leaves it."""
    mgr = _make_uuid_manager()
    mgr.reid_enabled = False
    mgr.active_ids = {11: ["original-gid", None]}

    obj = _make_sscape_object(rv_id=11, gid="new-gid")
    mgr.assignID(obj)

    # The original GID must not be overwritten
    self.assertEqual(mgr.active_ids[11][0], "original-gid")


class TestGetActiveGID(unittest.TestCase):
  """getActiveGID reads under active_ids_lock."""

  def test_returns_gid_when_present(self):
    mgr = _make_uuid_manager()
    mgr.active_ids = {42: ["gid-42", 0.9]}
    self.assertEqual(mgr.getActiveGID(42), "gid-42")

  def test_returns_none_when_missing_or_unset(self):
    mgr = _make_uuid_manager()
    self.assertIsNone(mgr.getActiveGID(1))
    mgr.active_ids = {2: [None, None]}
    self.assertIsNone(mgr.getActiveGID(2))


class TestPruneInactiveTracksAcceptsSet(unittest.TestCase):
  """pruneInactiveTracks now accepts a set (changed from list in commit f4d8d7f)."""

  def test_accepts_set_of_tracked_objects(self):
    """pruneInactiveTracks works correctly when passed a set."""
    mgr = _make_uuid_manager()
    mgr.active_ids = {1: ["gid-1", None], 2: ["gid-2", None]}

    active_set = {_make_tracked(1)}  # pass a set, not a list
    mgr.pruneInactiveTracks(active_set)

    self.assertIn(1, mgr.active_ids)
    self.assertNotIn(2, mgr.active_ids)


if __name__ == "__main__":
  unittest.main()
