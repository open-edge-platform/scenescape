#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for DBSCAN clustering in ClusterAnalyticsContext.

Tests analyze_object_clusters via its return value (raw cluster list),
with the ClusterTracker mocked out so only DBSCAN logic is exercised.
"""

import pytest
import math


SCENE_ID = "test-scene-001"


def _detection(objects):
  return {"name": "test-scene", "timestamp": None, "objects": objects}


class TestAnalyzeObjectClusters:

  def test_two_groups_produce_two_clusters(self, context, make_objects):
    group_a = make_objects([(1.0 + i * 0.05, 1.0 + i * 0.05) for i in range(6)])
    group_b = make_objects([(10.0 + i * 0.05, 10.0 + i * 0.05) for i in range(5)])
    clusters = context.analyze_object_clusters(SCENE_ID, _detection(group_a + group_b))

    assert len(clusters) == 2

  def test_two_groups_correct_centroids(self, context, make_objects):
    group_a = make_objects([(1.0 + i * 0.05, 1.0) for i in range(6)])
    group_b = make_objects([(10.0 + i * 0.05, 10.0) for i in range(6)])
    clusters = context.analyze_object_clusters(SCENE_ID, _detection(group_a + group_b))

    centroids = sorted(
      [(c["center_of_mass"]["x"], c["center_of_mass"]["y"]) for c in clusters]
    )
    assert math.isclose(centroids[0][0], 1.125, abs_tol=0.5)
    assert math.isclose(centroids[1][0], 10.125, abs_tol=0.5)

  def test_object_ids_not_mixed_across_clusters(self, context, make_objects):
    group_a = make_objects([(0.0, 0.0), (0.1, 0.1), (0.2, 0.0)])
    group_b = make_objects([(10.0, 10.0), (10.1, 10.0), (10.0, 10.1)])
    ids_a = {obj["id"] for obj in group_a}
    ids_b = {obj["id"] for obj in group_b}

    clusters = context.analyze_object_clusters(SCENE_ID, _detection(group_a + group_b))

    assert len(clusters) == 2
    for cluster in clusters:
      cluster_ids = set(cluster["object_ids"])
      assert cluster_ids.issubset(ids_a) or cluster_ids.issubset(ids_b), (
        f"Cluster object_ids span both groups: {cluster_ids}"
      )

  def test_two_categories_clustered_independently(self, context, make_objects):
    persons = make_objects([(1.0, 1.0), (1.1, 1.0), (0.9, 1.0)], category="person")
    vehicles = make_objects([(1.0, 1.0), (1.1, 1.0), (0.9, 1.0)], category="vehicle")
    clusters = context.analyze_object_clusters(SCENE_ID, _detection(persons + vehicles))

    categories = {c["category"] for c in clusters}
    assert "person" in categories
    assert "vehicle" in categories
    assert len(clusters) >= 2

  def test_noise_object_excluded(self, context, make_objects):
    group = make_objects([(0.0, 0.0), (0.1, 0.0), (0.2, 0.0)])
    # Use an explicit ID that does not collide with the group IDs
    noise = [{"id": "noise-far", "category": "person",
              "translation": [100.0, 100.0, 0.0], "velocity": [0.0, 0.0, 0.0]}]
    clusters = context.analyze_object_clusters(SCENE_ID, _detection(group + noise))

    all_ids = {oid for c in clusters for oid in c["object_ids"]}
    assert "noise-far" not in all_ids

  def test_fewer_objects_than_min_samples_returns_empty(self, context, make_objects):
    # person min_samples == 2; 1 object is not enough
    one_person = make_objects([(1.0, 1.0)], category="person")
    clusters = context.analyze_object_clusters(SCENE_ID, _detection(one_person))

    assert clusters == []

  def test_empty_objects_returns_empty(self, context):
    clusters = context.analyze_object_clusters(SCENE_ID, _detection([]))

    assert clusters == []

  def test_objects_missing_translation_falls_back(self, context):
    objects = [
      {"id": "a", "category": "person", "x": 0.0, "y": 0.0, "velocity": [0, 0, 0]},
      {"id": "b", "category": "person", "x": 0.1, "y": 0.0, "velocity": [0, 0, 0]},
      {"id": "c", "category": "person", "x": 0.2, "y": 0.0, "velocity": [0, 0, 0]},
    ]
    # Should not raise; uses x/y fallback
    clusters = context.analyze_object_clusters(SCENE_ID, _detection(objects))

    assert isinstance(clusters, list)

  def test_cluster_has_expected_keys(self, context, make_objects):
    objects = make_objects([(0.0, 0.0), (0.1, 0.0), (0.2, 0.0)])
    clusters = context.analyze_object_clusters(SCENE_ID, _detection(objects))

    assert len(clusters) == 1
    cluster = clusters[0]
    for key in ("category", "objects_count", "center_of_mass", "object_ids",
                "shape_analysis", "velocity_analysis", "dbscan_params"):
      assert key in cluster, f"Missing key: {key}"

  def test_cluster_objects_count_is_correct(self, context, make_objects):
    objects = make_objects([(0.0 + i * 0.1, 0.0) for i in range(4)])
    clusters = context.analyze_object_clusters(SCENE_ID, _detection(objects))

    assert len(clusters) == 1
    assert clusters[0]["objects_count"] == 4
