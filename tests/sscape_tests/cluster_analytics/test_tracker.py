#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the simplified ClusterTracker (Phase 1 target API).

These tests are written as an executable specification for the
post-refactor ClusterTracker.  They are skipped until Phase 1 of the
tracker refactoring is complete and the new API is in place.

Expected API after refactor:
  ClusterTracker(max_matching_distance=2.0, expiry_seconds=10.0)
  tracker.update(scene_id: str, raw_detections: list[dict], timestamp: float) -> None
  tracker.get_clusters(scene_id: str) -> list[TrackedCluster]

  TrackedCluster.uuid      – persistent str UUID
  TrackedCluster.category  – str
  TrackedCluster.centroid  – dict with 'x', 'y' keys
  TrackedCluster.first_seen, TrackedCluster.last_seen – float timestamps
"""

import pytest

SCENE = "tracker-test-scene"


def _detection(x, y, category="person", n_objects=3):
  return {
    "category": category,
    "objects_count": n_objects,
    "center_of_mass": {"x": float(x), "y": float(y)},
    "shape_analysis": {"shape": "circle", "size": {}},
    "velocity_analysis": {
      "movement_type": "stationary",
      "average_velocity": [0.0, 0.0, 0.0],
      "velocity_magnitude": 0.0,
      "movement_direction_degrees": 0.0,
      "velocity_coherence": 0.0,
    },
    "object_ids": [f"obj-{i}" for i in range(n_objects)],
    "dbscan_params": {"eps": 2.0, "min_samples": 2, "category": category},
  }


class TestClusterTrackerUUIDStability:

  def _make_tracker(self, max_dist=2.0, expiry=10.0):
    from cluster_analytics_tracker import ClusterTracker
    return ClusterTracker(max_matching_distance=max_dist, expiry_seconds=expiry)

  def test_first_update_creates_cluster_with_uuid(self):
    tracker = self._make_tracker()
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.0)

    clusters = tracker.get_clusters(SCENE)
    assert len(clusters) == 1
    assert clusters[0].uuid is not None
    assert len(clusters[0].uuid) > 0

  def test_same_centroid_next_frame_keeps_uuid(self):
    tracker = self._make_tracker()
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.0)
    uuid_first = tracker.get_clusters(SCENE)[0].uuid

    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.1)
    uuid_second = tracker.get_clusters(SCENE)[0].uuid

    assert uuid_first == uuid_second

  def test_centroid_beyond_max_distance_creates_new_uuid(self):
    tracker = self._make_tracker(max_dist=2.0)
    tracker.update(SCENE, [_detection(0.0, 0.0)], timestamp=100.0)
    uuid_first = tracker.get_clusters(SCENE)[0].uuid

    tracker.update(SCENE, [_detection(10.0, 10.0)], timestamp=100.1)
    clusters = tracker.get_clusters(SCENE)

    # Both clusters coexist (old one not yet expired); the new one must have a distinct UUID
    assert len(clusters) == 2
    uuids = {c.uuid for c in clusters}
    assert uuid_first in uuids
    assert len(uuids) == 2, "Detection far beyond max_dist must create a new UUID"

  def test_cluster_restored_within_expiry_window(self):
    tracker = self._make_tracker(expiry=10.0)
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.0)
    original_uuid = tracker.get_clusters(SCENE)[0].uuid

    # Gap of 2 seconds — within the 10 s expiry window
    tracker.update(SCENE, [], timestamp=102.0)
    assert len(tracker.get_clusters(SCENE)) == 1
    assert tracker.get_clusters(SCENE)[0].uuid == original_uuid

    # Cluster reappears at same location
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=104.0)
    assert tracker.get_clusters(SCENE)[0].uuid == original_uuid

  def test_cluster_expired_after_expiry_window(self):
    tracker = self._make_tracker(expiry=5.0)
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.0)
    original_uuid = tracker.get_clusters(SCENE)[0].uuid

    # Gap of 6 seconds — beyond expiry
    tracker.update(SCENE, [], timestamp=106.0)

    # Reappearance should get a new UUID
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=106.1)
    new_uuid = tracker.get_clusters(SCENE)[0].uuid

    assert new_uuid != original_uuid

  def test_different_categories_at_same_position_get_separate_uuids(self):
    tracker = self._make_tracker()
    tracker.update(SCENE, [
      _detection(1.0, 1.0, category="person"),
      _detection(1.0, 1.0, category="vehicle"),
    ], timestamp=100.0)

    clusters = tracker.get_clusters(SCENE)
    assert len(clusters) == 2
    uuids = {c.uuid for c in clusters}
    assert len(uuids) == 2  # both unique

  def test_get_clusters_excludes_expired(self):
    tracker = self._make_tracker(expiry=5.0)
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.0)

    tracker.update(SCENE, [], timestamp=106.0)  # past expiry

    assert len(tracker.get_clusters(SCENE)) == 0

  def test_empty_detections_no_crash(self):
    tracker = self._make_tracker()
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.0)
    original_uuid = tracker.get_clusters(SCENE)[0].uuid

    tracker.update(SCENE, [], timestamp=100.5)  # within window

    clusters = tracker.get_clusters(SCENE)
    assert len(clusters) == 1
    assert clusters[0].uuid == original_uuid


class TestClusterTrackerClearScene:

  def _make_tracker(self, max_dist=2.0, expiry=10.0):
    from cluster_analytics_tracker import ClusterTracker
    return ClusterTracker(max_matching_distance=max_dist, expiry_seconds=expiry)

  def test_clear_scene_removes_clusters_immediately(self):
    tracker = self._make_tracker(expiry=10.0)
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.0)
    assert len(tracker.get_clusters(SCENE)) == 1

    tracker.clear_scene(SCENE)

    assert len(tracker.get_clusters(SCENE)) == 0

  def test_clear_scene_allows_fresh_uuid_after_settings_change(self):
    tracker = self._make_tracker(expiry=10.0)
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.0)
    old_uuid = tracker.get_clusters(SCENE)[0].uuid

    # Simulate settings change — clear, then re-detect at the same location
    tracker.clear_scene(SCENE)
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.1)

    clusters = tracker.get_clusters(SCENE)
    assert len(clusters) == 1
    assert clusters[0].uuid != old_uuid, "A new UUID must be assigned after clear_scene()"

  def test_clear_scene_on_unknown_scene_does_not_raise(self):
    tracker = self._make_tracker()
    tracker.clear_scene("nonexistent-scene")  # must not raise

  def test_clear_scene_only_affects_target_scene(self):
    other_scene = "other-scene"
    tracker = self._make_tracker(expiry=10.0)
    tracker.update(SCENE, [_detection(1.0, 1.0)], timestamp=100.0)
    tracker.update(other_scene, [_detection(2.0, 2.0)], timestamp=100.0)

    tracker.clear_scene(SCENE)

    assert len(tracker.get_clusters(SCENE)) == 0
    assert len(tracker.get_clusters(other_scene)) == 1
