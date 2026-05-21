# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for controller.UUIDManager."""

import collections
import sys
import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

# Ensure the vdms stub is present before any controller import
sys.modules.setdefault('vdms', MagicMock())

from controller.uuid_manager import (DEFAULT_MINIMUM_FEATURE_COUNT,
                                     UUIDManager)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_uuid_manager():
  """Create a UUIDManager with all external dependencies mocked out."""
  um = UUIDManager.__new__(UUIDManager)
  um.active_ids = {}
  um.active_ids_lock = threading.Lock()
  um.active_query = {}
  um.features_for_database = {}
  um.quality_features = {}
  um.unique_id_count = 0
  um.reid_database = MagicMock()
  um.pool = MagicMock()
  um.similarity_query_times = collections.deque(maxlen=10)
  um.similarity_query_times_lock = threading.Lock()
  um.reid_enabled = True
  return um


def _make_sscape_object(rv_id=1, gid='test-gid', reid_vector=None,
                        bbox_area=10000, category='person'):
  """Create a minimal mock Scenescape object."""
  obj = MagicMock()
  obj.rv_id = rv_id
  obj.gid = gid
  obj.reidVector = reid_vector if reid_vector is not None else np.ones((1, 256))
  obj.boundingBoxPixels = MagicMock()
  obj.boundingBoxPixels.area = bbox_area
  obj.category = category
  obj.similarity = None
  return obj


def _populate_features(uuid_manager, rv_id, count):
  """Insert *count* dummy ReID vectors for *rv_id* into quality_features."""
  uuid_manager.quality_features[rv_id] = [np.ones((1, 256)) for _ in range(count)]


# ===========================================================================
# PR #1155 – preserve UUID for static objects after occlusion
# ===========================================================================

class TestPruneInactiveTracks:
  """pruneInactiveTracks must accept a *set* of tracked objects and remove
  only the tracks whose IDs are absent from that set."""

  def test_preserves_tracks_present_in_active_set(self, uuid_manager):
    """! Tracks still present in the active set are kept in active_ids.

    Verifies that a track ID found in the supplied set is NOT removed.
    """
    uuid_manager.active_ids = {1: ['gid-1', None], 2: ['gid-2', 0.3]}

    active_obj = _make_tracked_obj(1)
    uuid_manager.pruneInactiveTracks({active_obj})

    assert 1 in uuid_manager.active_ids

  def test_removes_tracks_absent_from_active_set(self, uuid_manager):
    """! Tracks absent from the active set are removed from active_ids.

    Verifies that a track ID NOT found in the supplied set IS removed.
    """
    uuid_manager.active_ids = {1: ['gid-1', None], 2: ['gid-2', None]}

    active_obj = _make_tracked_obj(1)
    uuid_manager.pruneInactiveTracks({active_obj})

    assert 2 not in uuid_manager.active_ids

  def test_accepts_set_containing_suspended_tracks(self, uuid_manager):
    """! Passing a mixed set of reliable, unreliable, and suspended track
    objects preserves all their IDs (mirrors the PR #1155 change that passes
    set(reliable + unreliable + suspended) to pruneInactiveTracks).
    """
    uuid_manager.active_ids = {
      10: ['gid-reliable', 0.2],
      20: ['gid-unreliable', None],
      30: ['gid-suspended', None],
    }

    reliable = _make_tracked_obj(10)
    unreliable = _make_tracked_obj(20)
    suspended = _make_tracked_obj(30)

    all_active = {reliable, unreliable, suspended}
    uuid_manager.pruneInactiveTracks(all_active)

    assert 10 in uuid_manager.active_ids
    assert 20 in uuid_manager.active_ids
    assert 30 in uuid_manager.active_ids

  def test_increments_unique_id_count_for_unmatched_tracks(self, uuid_manager):
    """! When an inactive track has similarity==None, unique_id_count
    is incremented because no database match was found for that object.
    """
    uuid_manager.active_ids = {5: ['gid-5', None]}  # similarity is None → new object
    uuid_manager.unique_id_count = 0

    uuid_manager.pruneInactiveTracks(set())  # empty → track 5 is inactive

    assert uuid_manager.unique_id_count == 1

  def test_does_not_increment_unique_id_count_for_matched_tracks(self, uuid_manager):
    """! When an inactive track has a non-None similarity score, it was
    matched to an existing database entry and unique_id_count must NOT
    be incremented.
    """
    uuid_manager.active_ids = {5: ['gid-5', 12.3]}  # similarity is not None → matched
    uuid_manager.unique_id_count = 0

    uuid_manager.pruneInactiveTracks(set())

    assert uuid_manager.unique_id_count == 0

  def test_suspended_track_uuid_survives_occlusion(self, uuid_manager):
    """! Simulates an object becoming occluded (moving to suspended state)
    and reappearing.

    When the object's rv_id is included in all_active_tracks (because the
    C++ tracker keeps the suspended track alive), its GID must not be
    removed from active_ids, so when it reappears pickBestID can restore
    the original GID.
    """
    rv_id = 42
    original_gid = 'original-gid'
    uuid_manager.active_ids = {rv_id: [original_gid, None]}

    # Object is suspended – its ID IS in the all_active set
    suspended_track = _make_tracked_obj(rv_id)
    uuid_manager.pruneInactiveTracks({suspended_track})

    # GID must still be present
    assert rv_id in uuid_manager.active_ids
    assert uuid_manager.active_ids[rv_id][0] == original_gid


# ===========================================================================
# PR #1155 – pickBestID restores GID for reappearing static objects
# ===========================================================================

class TestPickBestID:
  """pickBestID must restore the database GID (and similarity) from
  active_ids onto the sscape_object when an existing mapping exists."""

  def test_restores_gid_from_active_ids(self, uuid_manager, sscape_object):
    """! When active_ids contains a non-None GID for the track, pickBestID
    sets that GID on the object so the original identity is preserved.
    """
    stored_gid = 'database-uuid'
    stored_similarity = 5.2
    uuid_manager.active_ids[sscape_object.rv_id] = [stored_gid, stored_similarity]

    uuid_manager.pickBestID(sscape_object)

    assert sscape_object.gid == stored_gid
    assert sscape_object.similarity == stored_similarity

  def test_sets_similarity_none_when_no_mapping(self, uuid_manager, sscape_object):
    """! When active_ids has no entry for the track, similarity is set to
    None and the object's gid is left unchanged.
    """
    uuid_manager.active_ids = {}
    sscape_object.gid = 'original-gid'

    uuid_manager.pickBestID(sscape_object)

    assert sscape_object.similarity is None

  def test_accumulates_reid_vectors_for_known_track(self, uuid_manager, sscape_object):
    """! Once a GID is locked in active_ids and the object has reid
    vectors, subsequent calls to pickBestID append them to
    features_for_database so the track can be indexed on departure.
    """
    stored_gid = 'database-uuid'
    uuid_manager.active_ids[sscape_object.rv_id] = [stored_gid, None]
    uuid_manager.features_for_database[sscape_object.rv_id] = {
      'gid': stored_gid,
      'category': sscape_object.category,
      'reid_vectors': [],
    }
    reid_vector = np.ones((1, 256))
    sscape_object.reidVector = reid_vector

    uuid_manager.pickBestID(sscape_object)

    assert len(uuid_manager.features_for_database[sscape_object.rv_id]['reid_vectors']) == 1


class TestAssignIDFallbackBehavior:
  """The GID fallback in assignID must fire ONLY when re-id is explicitly
  disabled, never while feature collection is still in progress."""

  def test_reid_enabled_insufficient_features_does_not_lock_gid(
      self, uuid_manager, sscape_object):
    """! Core bug-fix regression test: with re-id enabled and fewer than
    DEFAULT_MINIMUM_FEATURE_COUNT features gathered, active_ids must stay
    [None, None] so that feature collection continues on subsequent frames.

    Before the fix the 'else' branch would set active_ids[rv_id] to
    [gid, None] on the very first frame, causing isNewTrackerID() to return
    False on subsequent frames and permanently skipping
    gatherQualityVisualFeatures().
    """
    uuid_manager.reid_enabled = True
    # Seed fewer features than the minimum
    _populate_features(uuid_manager, sscape_object.rv_id,
                       DEFAULT_MINIMUM_FEATURE_COUNT - 1)

    uuid_manager.assignID(sscape_object)

    # active_ids should remain [None, None] – GID must NOT be locked in yet
    assert uuid_manager.active_ids.get(sscape_object.rv_id) == [None, None]

  def test_reid_enabled_gid_not_locked_across_multiple_frames(
      self, uuid_manager, sscape_object):
    """! Calling assignID repeatedly while features are still accumulating
    must keep active_ids[rv_id] == [None, None] on every call (not
    prematurely lock the GID after the first call).
    """
    uuid_manager.reid_enabled = True

    for _ in range(DEFAULT_MINIMUM_FEATURE_COUNT - 1):
      uuid_manager.assignID(sscape_object)
      assert uuid_manager.active_ids.get(sscape_object.rv_id) == [None, None], \
        "GID was locked before sufficient features were collected"

  def test_reid_disabled_locks_gid_immediately(self, uuid_manager, sscape_object):
    """! When re-id is disabled the GID fallback must fire on the first
    call to assignID, setting active_ids[rv_id] to [gid, None].
    """
    uuid_manager.reid_enabled = False

    uuid_manager.assignID(sscape_object)

    result = uuid_manager.active_ids.get(sscape_object.rv_id)
    assert result == [sscape_object.gid, None]

  def test_reid_enabled_sufficient_features_submits_query(
      self, uuid_manager, sscape_object):
    """! When re-id is enabled and the feature count reaches
    DEFAULT_MINIMUM_FEATURE_COUNT, a similarity query must be submitted
    to the thread pool exactly once.
    """
    uuid_manager.reid_enabled = True
    _populate_features(uuid_manager, sscape_object.rv_id,
                       DEFAULT_MINIMUM_FEATURE_COUNT)

    uuid_manager.assignID(sscape_object)

    uuid_manager.pool.submit.assert_called_once()

  def test_reid_enabled_sufficient_features_query_submitted_only_once(
      self, uuid_manager, sscape_object):
    """! Once the similarity query has been submitted (active_query[rv_id]
    is set), subsequent frames must not submit it again even if the feature
    count remains above the minimum.
    """
    uuid_manager.reid_enabled = True
    _populate_features(uuid_manager, sscape_object.rv_id,
                       DEFAULT_MINIMUM_FEATURE_COUNT)

    uuid_manager.assignID(sscape_object)  # first call – query submitted
    uuid_manager.assignID(sscape_object)  # second call – should not re-submit

    assert uuid_manager.pool.submit.call_count == 1

  def test_assign_id_known_tracker_id_calls_pick_best_id(
      self, uuid_manager, sscape_object):
    """! For a track that already has an entry in active_ids with a non-None
    GID (i.e., isNewTrackerID returns False), assignID must call pickBestID
    to apply the stored GID to the object.
    """
    stored_gid = 'already-resolved-gid'
    uuid_manager.active_ids[sscape_object.rv_id] = [stored_gid, 3.1]

    uuid_manager.assignID(sscape_object)

    assert sscape_object.gid == stored_gid

  def test_reid_disabled_no_query_submitted(self, uuid_manager, sscape_object):
    """! When re-id is disabled the thread pool must never be asked to run
    a similarity query.
    """
    uuid_manager.reid_enabled = False
    _populate_features(uuid_manager, sscape_object.rv_id,
                       DEFAULT_MINIMUM_FEATURE_COUNT)

    uuid_manager.assignID(sscape_object)

    uuid_manager.pool.submit.assert_not_called()


# ===========================================================================
# Supporting helpers
# ===========================================================================

def _make_tracked_obj(track_id):
  """Return a minimal mock with .id set to *track_id*."""
  obj = MagicMock()
  obj.id = track_id
  return obj


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def uuid_manager():
  """Provide a fresh UUIDManager for each test."""
  return _make_uuid_manager()


@pytest.fixture
def sscape_object():
  """Provide a default mock Scenescape object."""
  return _make_sscape_object()
