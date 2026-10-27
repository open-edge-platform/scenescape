# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""ReidIdentityMap: applying reid-service decisions to scene objects."""

import json
import unittest
from unittest.mock import Mock

from analytics.reid_identity import ReidIdentityMap


def decision(track_id, gid, matched, similarity=None, scene="s1", category="person"):
  return json.dumps({"scene_id": scene, "category": category, "track_id": track_id,
                     "gid": gid, "matched": matched, "similarity": similarity,
                     "decided_at": "2026-10-14T21:30:00.000Z"}).encode()


def objects(*ids):
  return [{"id": i, "category": "person", "translation": [0, 0, 0]} for i in ids]


class TestReidIdentityMap(unittest.TestCase):

  def test_pending_and_disabled_states_preserve_identity_and_count(self):
    for state in ("pending_collection", "reid_disabled"):
      with self.subTest(state=state):
        ids = ReidIdentityMap()
        ids.update({"scene_id": "s1", "category": "person", "track_id": "t1",
                    "gid": "t1", "matched": False, "reid_state": state,
                    "unique_id_count": 3})
        objs = objects("t1")

        self.assertEqual(ids.apply("s1", "person", objs), 0)

        self.assertEqual(objs[0]["reid_state"], state)
        self.assertEqual(objs[0]["id"], "t1")
        self.assertEqual(ids.uniqueDetectionCount("s1", "person"), 3)
        self.assertIsNone(ids.uniqueDetectionCount("s2", "person"))
        self.assertIsNone(ids.uniqueDetectionCount("s1", "vehicle"))

  def test_matched_state_is_applied_when_gid_does_not_change(self):
    ids = ReidIdentityMap()
    ids.update(decision("t1", "t1", True, 0.9))
    objs = objects("t1")

    self.assertEqual(ids.apply("s1", "person", objs), 0)

    self.assertEqual(objs[0]["reid_state"], "matched")
    self.assertEqual(objs[0]["similarity"], 0.9)
    self.assertNotIn("previous_ids_chain", objs[0])

  def test_invalid_state_or_count_is_rejected(self):
    for invalid in ({"reid_state": "unknown"}, {"unique_id_count": -1},
                    {"unique_id_count": True}):
      ids = ReidIdentityMap()
      payload = {"scene_id": "s1", "category": "person", "track_id": "t1", "gid": "t1"}
      payload.update(invalid)

      self.assertFalse(ids.update(payload))
      self.assertEqual(len(ids), 0)
      self.assertIsNone(ids.uniqueDetectionCount("s1", "person"))

  def test_match_replaces_id_and_adds_reid_fields(self):
    ids = ReidIdentityMap()
    ids.update(decision("track-new", "gid-old", True, 0.78))
    objs = objects("track-new", "someone-else")
    self.assertEqual(ids.apply("s1", "person", objs), 1)
    self.assertEqual(objs[0]["id"], "gid-old")
    self.assertEqual(objs[0]["reid_state"], "matched")
    self.assertEqual(objs[0]["similarity"], 0.78)
    self.assertEqual(objs[0]["previous_ids_chain"],
                     [{"id": "track-new", "timestamp": "2026-10-14T21:30:00.000Z",
                       "similarity_score": 0.78}])
    self.assertEqual(objs[1], {**objects("someone-else")[0], "reid_state": "pending_collection"})

  def test_no_match_keeps_track_id(self):
    ids = ReidIdentityMap()
    ids.update(decision("track-1", "track-1", False))
    objs = objects("track-1")
    self.assertEqual(ids.apply("s1", "person", objs), 0)
    self.assertEqual(objs[0]["id"], "track-1")
    self.assertEqual(objs[0]["reid_state"], "query_no_match")

  def test_no_match_honors_fresh_gid_without_merging_identities(self):
    ids = ReidIdentityMap()
    ids.update(decision("track-1", "track-2", True, 0.9))
    ids.update(decision("track-2", "fresh-gid", False))
    objs = objects("track-1", "track-2")
    objs[1]["reid_state"] = "matched"

    self.assertEqual(ids.apply("s1", "person", objs), 2)

    self.assertEqual([obj["id"] for obj in objs], ["track-2", "fresh-gid"])
    self.assertEqual(objs[1]["reid_state"], "query_no_match")
    self.assertNotIn("previous_ids_chain", objs[1])
    self.assertNotIn("similarity", objs[1])

  def test_no_match_migrates_cache_before_applying_fresh_gid(self):
    ids = ReidIdentityMap()
    ids.update(decision("track-1", "fresh-gid", False))
    objs = objects("track-1")

    def migrate(category, old_id, new_id):
      self.assertEqual(objs[0]["id"], "track-1")
      return True

    rename = Mock(side_effect=migrate)

    self.assertEqual(ids.apply("s1", "person", objs, rename_object=rename), 1)

    rename.assert_called_once_with("person", "track-1", "fresh-gid")
    self.assertEqual(objs[0]["id"], "fresh-gid")
    self.assertEqual(objs[0]["reid_state"], "query_no_match")

  def test_no_match_defers_fresh_gid_when_cache_migration_conflicts(self):
    ids = ReidIdentityMap()
    ids.update(decision("track-1", "fresh-gid", False))
    objs = objects("track-1")
    rename = Mock(return_value=False)

    self.assertEqual(ids.apply("s1", "person", objs, rename_object=rename), 0)

    rename.assert_called_once_with("person", "track-1", "fresh-gid")
    self.assertEqual(objs, objects("track-1"))

  def test_decision_is_scoped_to_scene_and_category(self):
    ids = ReidIdentityMap()
    ids.update(decision("track-1", "gid-A", True, 0.9, scene="s1"))
    other_scene = objects("track-1")
    ids.apply("s2", "person", other_scene)
    self.assertEqual(other_scene[0]["id"], "track-1")
    vehicle = [{"id": "track-1", "category": "vehicle"}]
    ids.apply("s1", "vehicle", vehicle)
    self.assertEqual(vehicle[0]["id"], "track-1")

  def test_applies_on_every_frame_until_stale(self):
    now = [0.0]
    ids = ReidIdentityMap(ttl_secs=30, clock=lambda: now[0])
    ids.update(decision("track-1", "gid-A", True, 0.9))
    for t in (1.0, 20.0, 45.0):  # seen regularly: never stale
      now[0] = t
      objs = objects("track-1")
      ids.apply("s1", "person", objs)
      self.assertEqual(objs[0]["id"], "gid-A")
    now[0] = 80.0  # track gone for 35 s
    ids.apply("s1", "person", [])
    self.assertEqual(len(ids), 0)

  def test_malformed_decision_ignored(self):
    ids = ReidIdentityMap()
    self.assertFalse(ids.update(b"{not json"))
    self.assertFalse(ids.update(b'{"track_id": "t"}'))
    self.assertEqual(len(ids), 0)


if __name__ == "__main__":
  unittest.main()
