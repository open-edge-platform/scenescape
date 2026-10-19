# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Routing, filtering and parity counters of TrackIngest."""

import json
import unittest

from reid.ingest import TrackIngest
from reid.matcher import MatcherConfig
from test_ingest_parse import _object, scene_message
from test_matcher import FakeAdapter, all_match

TOPIC = "scenescape/data/scene/scene1/person"


def make_ingest(adapter_results=None, **kw):
  adapters = []

  def factory():
    adapter = FakeAdapter(adapter_results)
    adapters.append(adapter)
    return adapter

  ingest = TrackIngest(factory, MatcherConfig(minimum_feature_count=3), **kw)
  return ingest, adapters


class TestTrackIngest(unittest.TestCase):

  def test_one_matcher_per_scene_and_category(self):
    ingest, adapters = make_ingest()
    ingest.handle_message(TOPIC, scene_message([_object("t1")]))
    ingest.handle_message(TOPIC, scene_message([_object("t1")]))
    ingest.handle_message("scenescape/data/scene/scene1/vehicle", scene_message([]))
    ingest.handle_message("scenescape/data/scene/scene2/person", scene_message([]))
    self.assertEqual(len(adapters), 3)
    self.assertEqual(ingest.stats["messages"], 4)

  def test_scene_allowlist(self):
    ingest, adapters = make_ingest(scenes=["scene2"])
    ingest.handle_message(TOPIC, scene_message([_object("t1")]))
    self.assertEqual(adapters, [])
    self.assertEqual(ingest.stats["messages_ignored_scene"], 1)

  def test_malformed_and_foreign_topics(self):
    ingest, _ = make_ingest()
    ingest.handle_message(TOPIC, b"{not json")
    ingest.handle_message("scenescape/data/camera/cam1", b"{}")
    self.assertEqual(ingest.stats["messages_malformed"], 1)
    self.assertEqual(ingest.stats["messages_ignored_topic"], 1)

  def test_end_to_end_shadow_decision_and_parity(self):
    # Controller already said "query_no_match"; reid-service agrees.
    ingest, adapters = make_ingest()
    for seed in range(3):
      ingest.handle_message(TOPIC, scene_message([_object("t1", seed=seed)]))
    ingest.handle_message(TOPIC, scene_message([]))  # track leaves
    counters = ingest.snapshot()["counters"]
    self.assertEqual(counters["decisions"], 1)
    self.assertEqual(counters["parity_agree"], 1)
    self.assertEqual(counters["shadow_writes"], 1)
    self.assertEqual(adapters[0].writes, [])

  def test_parity_disagree(self):
    ingest, _ = make_ingest(all_match("gid-other"))
    for seed in range(3):
      ingest.handle_message(TOPIC, scene_message([_object("t1", seed=seed)]))
    self.assertEqual(ingest.snapshot()["counters"]["parity_disagree"], 1)

  def test_snapshot_shape(self):
    ingest, _ = make_ingest()
    ingest.handle_message(TOPIC, scene_message([_object("t1")]))
    snap = ingest.snapshot()
    self.assertEqual(snap["matchers"], ["scene1/person"])
    self.assertFalse(snap["write_enabled"])
    json.dumps(snap)  # must be serializable for the IngestStats RPC


class FakePubSub:
  def __init__(self):
    self.published = []

  def publish(self, topic, payload, qos=0, retain=False):
    self.published.append((topic, json.loads(payload), qos))


class TestDecisionPublishing(unittest.TestCase):

  def test_disabled_state_is_published_without_a_query(self):
    ingest, adapters = make_ingest()
    ingest.pubsub = FakePubSub()
    ingest._matcherFor('scene1', 'person').reid_enabled = False

    ingest.handle_message(TOPIC, scene_message([_object('t1')]))

    _, payload, _ = ingest.pubsub.published[-1]
    self.assertEqual(payload['reid_state'], 'reid_disabled')
    self.assertEqual(payload['unique_id_count'], 1)
    self.assertEqual(adapters[0].queries, [])
    self.assertEqual(ingest.snapshot()['unique_id_counts'], {'scene1/person': 1})

  def test_no_match_published_with_track_id_as_gid(self):
    ingest, _ = make_ingest()
    ingest.pubsub = FakePubSub()
    for seed in range(3):
      ingest.handle_message(TOPIC, scene_message([_object("t1", seed=seed)]))
    topic, payload, qos = ingest.pubsub.published[-1]
    self.assertEqual([message[1]["reid_state"] for message in ingest.pubsub.published],
             ["pending_collection"] * 3 + ["query_no_match"])
    self.assertEqual(topic, "scenescape/data/reid/scene1/person")
    self.assertEqual(qos, 1)
    self.assertEqual(payload["track_id"], "t1")
    self.assertEqual(payload["gid"], "t1")
    self.assertFalse(payload["matched"])
    self.assertEqual(payload["unique_id_count"], 1)

  def test_match_published_with_stored_gid(self):
    ingest, _ = make_ingest(all_match("gid-old", 0.8))
    ingest.pubsub = FakePubSub()
    for seed in range(3):
      ingest.handle_message(TOPIC, scene_message([_object("t2", seed=seed)]))
    _, payload, _ = ingest.pubsub.published[-1]
    self.assertTrue(payload["matched"])
    self.assertEqual((payload["track_id"], payload["gid"]), ("t2", "gid-old"))
    self.assertAlmostEqual(payload["similarity"], 0.8, places=6)
    self.assertEqual(payload["reid_state"], "matched")
    self.assertEqual(payload["unique_id_count"], 0)

  def test_decision_message_shape(self):
    msg = TrackIngest._decision_message({"scene_id": "s", "category": "person", "track_id": "t",
                            "gid": "g", "matched": True, "similarity": 0.7,
                            "timestamp": "2026-10-14T16:11:47.410Z"}, 0.0)
    self.assertEqual(msg["decided_at"], "1970-01-01T00:00:00.000Z")
    self.assertEqual(set(msg), {"scene_id", "category", "track_id", "gid", "matched",
                                "similarity", "timestamp", "decided_at", "reid_state",
                                "unique_id_count"})


if __name__ == "__main__":
  unittest.main()
