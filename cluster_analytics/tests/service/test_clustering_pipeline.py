#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Component tests for cluster analytics MQTT pipeline.

These tests start a real broker and cluster-analytics container, inject
DATA_REGULATED messages, and assert on what arrives at ANALYTICS_CLUSTERS.

Requires:
  - Docker available on the host
  - scenescape-cluster-analytics-test image built (`make test-build`
    in cluster_analytics/)
"""

import json
import math
import time
import pytest
import paho.mqtt.client as mqtt

from test_utils.mqtt import wait_for_message


SCENE_ID = "component-test-scene-001"
DATA_REGULATED_TOPIC = f"scenescape/regulated/scene/{SCENE_ID}"
ANALYTICS_CLUSTERS_PREFIX = "scenescape/analytics/clusters"
MESSAGE_TIMEOUT = 10.0


def _publish_detection(client, broker_port, objects, scene_id=SCENE_ID):
  """Publish a DATA_REGULATED message and return the paho result."""
  payload = {
    "name": "ComponentTestScene",
    "timestamp": None,
    "objects": objects,
  }
  topic = f"scenescape/regulated/scene/{scene_id}"
  result = client.publish(topic, json.dumps(payload), qos=1)
  result.wait_for_publish()
  return result


# The centroid tracker publishes clusters from the first frame.
# _warmup_and_publish sends one "silent" warmup frame to establish the cluster
# UUID in tracker state, then one final frame whose response is returned.
FRAMES_TO_ACTIVATE = 1


def _warmup_and_publish(client, broker_port, objects, scene_id=SCENE_ID,
                        warmup_frames=FRAMES_TO_ACTIVATE):
  """Warm up tracker state then return the message from the final publish."""
  for _ in range(warmup_frames):
    _publish_detection(client, broker_port, objects, scene_id)
    wait_for_message(client, ANALYTICS_CLUSTERS_PREFIX, timeout=MESSAGE_TIMEOUT)
  _publish_detection(client, broker_port, objects, scene_id)
  return wait_for_message(client, ANALYTICS_CLUSTERS_PREFIX, timeout=MESSAGE_TIMEOUT)


def _person_at(x, y, obj_id):
  return {
    "id": obj_id,
    "category": "person",
    "translation": [float(x), float(y), 0.0],
    "velocity": [0.0, 0.0, 0.0],
  }


def _vehicle_at(x, y, obj_id):
  return {
    "id": obj_id,
    "category": "vehicle",
    "translation": [float(x), float(y), 0.0],
    "velocity": [0.0, 0.0, 0.0],
  }


class TestClusteringPipeline:

  def test_single_group_produces_one_cluster(self, mqtt_client, cluster_analytics_service):
    objects = [_person_at(1.0 + i * 0.1, 1.0, f"p{i}") for i in range(6)]
    msg = _warmup_and_publish(mqtt_client, cluster_analytics_service["broker_port"], objects)

    assert "clusters" in msg
    person_clusters = [c for c in msg["clusters"] if c["category"] == "person"]
    assert len(person_clusters) == 1
    assert person_clusters[0]["objects_count"] == 6

  def test_two_groups_produce_two_clusters(self, mqtt_client, cluster_analytics_service):
    group_a = [_person_at(1.0 + i * 0.1, 1.0, f"a{i}") for i in range(4)]
    group_b = [_person_at(10.0 + i * 0.1, 10.0, f"b{i}") for i in range(4)]
    msg = _warmup_and_publish(
      mqtt_client, cluster_analytics_service["broker_port"], group_a + group_b
    )

    person_clusters = [c for c in msg["clusters"] if c["category"] == "person"]
    assert len(person_clusters) == 2
    centroids_x = sorted(c["center_of_mass"]["x"] for c in person_clusters)
    assert math.isclose(centroids_x[0], 1.15, abs_tol=0.5)
    assert math.isclose(centroids_x[1], 10.15, abs_tol=0.5)

  def test_sequential_publishes_produce_same_uuid(self, mqtt_client, cluster_analytics_service):
    objects = [_person_at(2.0 + i * 0.1, 2.0, f"p{i}") for i in range(4)]
    broker_port = cluster_analytics_service["broker_port"]

    # Warm up: publish FRAMES_TO_ACTIVATE frames so cluster reaches ACTIVE state
    for _ in range(FRAMES_TO_ACTIVATE):
      _publish_detection(mqtt_client, broker_port, objects)
      wait_for_message(mqtt_client, ANALYTICS_CLUSTERS_PREFIX, timeout=MESSAGE_TIMEOUT)

    _publish_detection(mqtt_client, broker_port, objects)
    msg1 = wait_for_message(mqtt_client, ANALYTICS_CLUSTERS_PREFIX, timeout=MESSAGE_TIMEOUT)

    time.sleep(0.1)

    _publish_detection(mqtt_client, broker_port, objects)
    msg2 = wait_for_message(mqtt_client, ANALYTICS_CLUSTERS_PREFIX, timeout=MESSAGE_TIMEOUT)

    clusters1 = [c for c in msg1["clusters"] if c["category"] == "person"]
    clusters2 = [c for c in msg2["clusters"] if c["category"] == "person"]
    assert len(clusters1) == 1
    assert len(clusters2) == 1
    assert clusters1[0]["id"] == clusters2[0]["id"], (
      "UUID changed between sequential frames for the same cluster"
    )

  def test_two_categories_clustered_independently(self, mqtt_client, cluster_analytics_service):
    persons = [_person_at(1.0 + i * 0.1, 1.0, f"person-{i}") for i in range(4)]
    vehicles = [_vehicle_at(1.0 + i * 0.1, 1.0, f"vehicle-{i}") for i in range(3)]
    msg = _warmup_and_publish(
      mqtt_client, cluster_analytics_service["broker_port"], persons + vehicles
    )

    categories = {c["category"] for c in msg["clusters"]}
    assert "person" in categories
    assert "vehicle" in categories
    # Confirm no category mixing: each cluster's object_ids all start with category prefix
    for cluster in msg["clusters"]:
      prefix = cluster["category"]
      for oid in cluster["object_ids"]:
        assert oid.startswith(prefix), (
          f"Cluster of '{prefix}' contains id '{oid}' from another category"
        )

  def test_below_min_samples_produces_empty_clusters(self, mqtt_client, cluster_analytics_service):
    # person min_samples == 2; only 1 object
    objects = [_person_at(1.0, 1.0, "solo")]
    _publish_detection(mqtt_client, cluster_analytics_service["broker_port"], objects)

    msg = wait_for_message(mqtt_client, ANALYTICS_CLUSTERS_PREFIX, timeout=MESSAGE_TIMEOUT)

    assert "clusters" in msg
    assert msg["clusters"] == []

  def test_empty_objects_produces_empty_clusters(self, mqtt_client, cluster_analytics_service):
    _publish_detection(mqtt_client, cluster_analytics_service["broker_port"], [])

    msg = wait_for_message(mqtt_client, ANALYTICS_CLUSTERS_PREFIX, timeout=MESSAGE_TIMEOUT)

    assert "clusters" in msg
    assert msg["clusters"] == []

  def test_objects_too_far_apart_produce_no_clusters(self, mqtt_client, cluster_analytics_service):
    # Person DBSCAN eps=2 m; place 3 persons each 10 m apart so every point is
    # noise (no neighbour within eps) → DBSCAN finds zero clusters.
    objects = [
      _person_at(0.0, 0.0, "p0"),
      _person_at(10.0, 0.0, "p1"),
      _person_at(20.0, 0.0, "p2"),
    ]
    _publish_detection(mqtt_client, cluster_analytics_service["broker_port"], objects)

    msg = wait_for_message(mqtt_client, ANALYTICS_CLUSTERS_PREFIX, timeout=MESSAGE_TIMEOUT)

    assert "clusters" in msg
    assert msg["clusters"] == []
