# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Behavior of the live-loop matcher ported from UUIDManager."""

import concurrent.futures
import unittest

import numpy as np

from reid.matcher import MatcherConfig, TrackMatcher, TrackObservation
from reid.reid import ReidNoValidVectorsError, ReidPartialWriteError


def vec(*values):
  return np.asarray(values, dtype=np.float32).reshape(1, -1)


class FakeAdapter:
  """Records calls; findMatches answers come from `self.results`."""

  def __init__(self, results=None):
    self.similarity_metric = None
    self.results = results  # callable(vectors) -> list[list[entity]] or None
    self.queries = []
    self.writes = []
    self.schemas = []
    self.write_error = None
    self.query_error = None

  def connect(self):
    return None

  def ensureSchema(self, dimensions):
    self.schemas.append(dimensions)

  def findMatches(self, category, vectors, k_neighbors=None, **metadata):
    self.queries.append((category, list(vectors), k_neighbors, metadata))
    if self.query_error:
      raise self.query_error
    if self.results is None:
      return [[] for _ in vectors]
    return self.results(vectors)

  def addEntry(self, gid, rvid, category, vectors, persist=None, **metadata):
    if self.write_error:
      raise self.write_error
    self.writes.append((gid, rvid, category, list(vectors), metadata))


def all_match(gid, score=0.9):
  return lambda vectors: [[{"uuid": gid, "rvid": "old", "_distance": score}] for _ in vectors]


class DeferredExecutor:
  """Holds submitted work until run() so tests can interleave events."""

  def __init__(self):
    self.jobs = []

  def submit(self, fn, *args):
    future = concurrent.futures.Future()
    self.jobs.append((future, fn, args))
    return future

  def run(self):
    while self.jobs:
      future, fn, args = self.jobs.pop(0)
      try:
        future.set_result(fn(*args))
      except Exception as err:
        future.set_exception(err)

  def shutdown(self, wait=True):
    return


def make(adapter=None, write_enabled=False, executor=None, clock=None, **cfg):
  config = MatcherConfig(minimum_feature_count=cfg.pop("minimum_feature_count", 3),
                         feature_slice_size=cfg.pop("feature_slice_size", 1), **cfg)
  decisions = []
  matcher = TrackMatcher(
    adapter or FakeAdapter(), config, scene_id="scene1", category="person",
    write_enabled=write_enabled, executor=executor, on_decision=decisions.append,
    clock=clock or (lambda: 0.0))
  return matcher, decisions


def obs(track_id, embedding, **kw):
  return TrackObservation(track_id=track_id, category="person", embedding=embedding, **kw)


def feed(matcher, track_id, vectors, **kw):
  for v in vectors:
    matcher.process_frame([obs(track_id, v, **kw)])


class TestControllerStateParity(unittest.TestCase):

  def test_missing_embedding_counts_once_and_remains_pending(self):
    matcher, decisions = make()
    states = []
    matcher.on_state = states.append

    feed(matcher, "t1", [None, None])

    self.assertEqual(matcher.unique_id_count, 1)
    self.assertEqual(matcher.stats["unique_id_count"], 1)
    self.assertEqual(states[0]["reid_state"], "pending_collection")
    self.assertEqual(states[0]["gid"], "t1")
    self.assertEqual(decisions, [])

  def test_disabled_track_counts_once_without_querying(self):
    matcher, decisions = make()
    matcher.reid_enabled = False
    states = []
    matcher.on_state = states.append

    feed(matcher, "t1", [vec(1, 0), vec(0, 1), vec(1, 1)])

    self.assertEqual(matcher.unique_id_count, 1)
    self.assertEqual(states[0]["reid_state"], "reid_disabled")
    self.assertEqual(matcher.adapter.queries, [])
    self.assertEqual(decisions, [])

  def test_inflight_query_stays_pending_then_no_match_counts(self):
    executor = DeferredExecutor()
    matcher, decisions = make(executor=executor)
    states = []
    matcher.on_state = states.append
    feed(matcher, "t1", [vec(1, 0), vec(0, 1), vec(1, 1)])

    self.assertEqual(states[-1]["reid_state"], "pending_collection")
    self.assertEqual(matcher.unique_id_count, 0)
    self.assertEqual(decisions, [])

    executor.run()

    self.assertEqual(decisions[0]["reid_state"], "query_no_match")
    self.assertEqual(decisions[0]["unique_id_count"], 1)

  def test_match_does_not_increment_unique_count(self):
    matcher, decisions = make(FakeAdapter(all_match("gid-old")))
    feed(matcher, "t1", [vec(1, 0), vec(0, 1), vec(1, 1)])

    self.assertEqual(decisions[0]["reid_state"], "matched")
    self.assertEqual(matcher.unique_id_count, 0)

  def test_initial_missing_embedding_then_no_match_increments_again(self):
    matcher, decisions = make()
    feed(matcher, "t1", [None, vec(1, 0), vec(0, 1), vec(1, 1)])

    self.assertEqual(matcher.unique_id_count, 2)
    self.assertEqual(decisions[0]["unique_id_count"], 2)

  def test_alias_rename_does_not_count_as_new_registration(self):
    matcher, _ = make()
    feed(matcher, "t1", [None])
    matcher.process_frame([obs("renamed", None, previous_ids=["t1"])])

    self.assertEqual(matcher.unique_id_count, 1)

  def test_write_failure_disables_matching_for_subsequent_tracks(self):
    matcher, _ = make()
    matcher._markUnhealthy("backend write failed")
    states = []
    matcher.on_state = states.append
    feed(matcher, "t1", [vec(1, 0)])

    self.assertEqual(states[0]["reid_state"], "reid_disabled")
    self.assertEqual(matcher.unique_id_count, 1)
    self.assertEqual(matcher.adapter.queries, [])

  def test_no_match_after_track_leaves_still_counts(self):
    executor = DeferredExecutor()
    matcher, decisions = make(executor=executor)
    states = []
    matcher.on_state = states.append
    feed(matcher, "t1", [vec(1, 0), vec(0, 1), vec(1, 1)])
    matcher.process_frame([])

    executor.run()

    self.assertEqual(matcher.unique_id_count, 1)
    self.assertEqual(decisions, [])
    self.assertEqual(states[-1]["reid_state"], "query_no_match")
    self.assertEqual(states[-1]["unique_id_count"], 1)


class TestQueryGating(unittest.TestCase):

  def test_shutdown_rejects_new_observations_without_submitting_more_work(self):
    matcher, _ = make(write_enabled=True)
    feed(matcher, 't1', [vec(1, 0), vec(0, 1), vec(1, 1)])
    self.assertEqual(matcher._query_futures, set())

    matcher.shutdown()
    matcher.shutdown()
    feed(matcher, 't2', [None, vec(1, 0), vec(0, 1), vec(1, 1)])

    self.assertEqual(len(matcher.adapter.queries), 1)
    self.assertEqual(len(matcher.adapter.writes), 1)
    self.assertNotIn('t2', matcher._tracks)
    self.assertEqual(matcher.unique_id_count, 1)

  def test_no_query_before_threshold(self):
    matcher, decisions = make()
    feed(matcher, "t1", [vec(1, 0, 0, 0), vec(0, 1, 0, 0)])
    self.assertEqual(matcher.adapter.queries, [])
    self.assertEqual(decisions, [])

  def test_query_at_threshold_with_unique_vectors(self):
    matcher, decisions = make()
    same = vec(1, 0, 0, 0)
    feed(matcher, "t1", [same, same, vec(0, 1, 0, 0)])
    self.assertEqual(len(matcher.adapter.queries), 1)
    category, vectors, k, _ = matcher.adapter.queries[0]
    self.assertEqual(category, "person")
    self.assertEqual(len(vectors), 2)  # exact repeat counted, not re-queried
    self.assertEqual(k, 5)
    self.assertEqual(len(decisions), 1)

  def test_only_one_query_per_track(self):
    matcher, _ = make()
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(6)])
    self.assertEqual(len(matcher.adapter.queries), 1)

  def test_observations_without_embedding_do_not_count(self):
    matcher, _ = make()
    feed(matcher, "t1", [None, None, None, vec(1, 0, 0, 0)])
    self.assertEqual(matcher.adapter.queries, [])
    self.assertEqual(matcher.stats["observations_without_embedding"], 3)

  def test_schema_inferred_once_and_mismatched_dims_dropped(self):
    matcher, _ = make()
    feed(matcher, "t1", [vec(1, 0, 0, 0), vec(1, 0, 0, 0, 0)])
    self.assertEqual(matcher.adapter.schemas, [4])
    self.assertEqual(matcher.stats["embeddings_rejected_dimension"], 1)

  def test_small_pixel_bbox_rejected(self):
    matcher, _ = make()
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)], bbox_px_area=10.0)
    self.assertEqual(matcher.adapter.queries, [])
    self.assertEqual(matcher.stats["embeddings_rejected_quality"], 3)

  def test_unvetted_embeddings_rejected_when_configured(self):
    matcher, _ = make(accept_unvetted_embeddings=False)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    self.assertEqual(matcher.adapter.queries, [])

  def test_vetted_provenance_accepted_when_unvetted_rejected(self):
    matcher, _ = make(accept_unvetted_embeddings=False)
    provenance = {"quality_vetted": True, "origin_scene_id": "child"}
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)], provenance=provenance)
    self.assertEqual(len(matcher.adapter.queries), 1)

  def test_semantic_metadata_passed_as_constraints(self):
    matcher, _ = make()
    meta = {"gender": {"label": "female", "confidence": 0.9}}
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)], metadata=meta)
    self.assertEqual(matcher.adapter.queries[0][3], meta)


class TestDecisions(unittest.TestCase):

  def test_no_match_assigns_new_gid(self):
    matcher, decisions = make()
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    (d,) = decisions
    self.assertFalse(d["matched"])
    self.assertEqual(d["gid"], "t1")  # new person keeps the producer's track id
    self.assertIsNone(d["similarity"])
    self.assertEqual(matcher.stats["no_matches"], 1)

  def test_match_uses_database_gid(self):
    matcher, decisions = make(FakeAdapter(all_match("gid-A", 0.9)))
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    (d,) = decisions
    self.assertTrue(d["matched"])
    self.assertEqual(d["gid"], "gid-A")
    self.assertAlmostEqual(d["similarity"], 0.9, places=6)

  def test_score_below_threshold_is_no_match(self):
    matcher, decisions = make(FakeAdapter(all_match("gid-A", 0.2)))
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    self.assertFalse(decisions[0]["matched"])

  def test_majority_vote(self):
    # 1 of 3 vectors points at gid-A: below half, so no match.
    def results(vectors):
      return [[{"uuid": "gid-A", "_distance": 0.9}], [{"uuid": "gid-B", "_distance": 0.1}],
              [{"uuid": "gid-C", "_distance": 0.1}]]
    matcher, decisions = make(FakeAdapter(results))
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    self.assertFalse(decisions[0]["matched"])

  def test_live_gid_collision_is_no_match(self):
    matcher, decisions = make(FakeAdapter(all_match("gid-A")))
    for i in range(3):
      matcher.process_frame([obs("t1", vec(i, 1, 0, 0)), obs("t2", vec(i, 2, 0, 0))])
    self.assertEqual([d["matched"] for d in decisions], [True, False])
    self.assertNotEqual(decisions[1]["gid"], "gid-A")
    self.assertEqual(matcher.stats["gid_collisions"], 1)

  def test_query_error_is_no_match(self):
    adapter = FakeAdapter()
    adapter.query_error = RuntimeError("backend down")
    matcher, decisions = make(adapter)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    self.assertFalse(decisions[0]["matched"])
    self.assertEqual(matcher.stats["query_errors"], 1)

  def test_track_left_before_query_finished(self):
    executor = DeferredExecutor()
    matcher, decisions = make(executor=executor)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    matcher.process_frame([])  # track leaves
    executor.run()
    self.assertEqual(decisions, [])
    self.assertEqual(matcher.stats["tracks_left_before_decision"], 1)

  def test_rename_via_previous_ids_keeps_track_state(self):
    matcher, decisions = make()
    feed(matcher, "provisional", [vec(0, 1, 0, 0), vec(1, 1, 0, 0)])
    matcher.process_frame([obs("final", vec(2, 1, 0, 0), previous_ids=["provisional"])])
    self.assertEqual(len(decisions), 1)
    self.assertEqual(decisions[0]["track_id"], "final")
    self.assertEqual(matcher.stats["tracks_renamed"], 1)


class TestWrites(unittest.TestCase):

  def test_shadow_mode_never_writes(self):
    matcher, _ = make()
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    matcher.process_frame([])  # track leaves -> flush
    self.assertEqual(matcher.adapter.writes, [])
    self.assertEqual(matcher.stats["shadow_writes"], 1)
    self.assertEqual(matcher.stats["shadow_vectors"], 3)

  def test_write_on_track_exit(self):
    matcher, decisions = make(write_enabled=True)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    matcher.process_frame([])
    ((gid, rvid, category, vectors, _),) = matcher.adapter.writes
    self.assertEqual(gid, decisions[0]["gid"])
    self.assertEqual((rvid, category, len(vectors)), ("t1", "person", 3))

  def test_post_decision_embeddings_enhance_pending_write(self):
    matcher, _ = make(write_enabled=True)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)] + [vec(9, 9, 0, 0)])
    matcher.process_frame([])
    self.assertEqual(len(matcher.adapter.writes[0][3]), 4)

  def test_slicing(self):
    matcher, _ = make(write_enabled=True, feature_slice_size=2, minimum_feature_count=4)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(4)])
    matcher.process_frame([])
    self.assertEqual(len(matcher.adapter.writes[0][3]), 2)

  def test_exact_rematch_vectors_are_not_rewritten(self):
    # Every query vector is already stored (score 1.0) -> nothing new to write.
    matcher, _ = make(FakeAdapter(all_match("gid-A", 1.0)), write_enabled=True)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    feed(matcher, "t1", [vec(2, 1, 0, 0)])
    matcher.process_frame([])
    self.assertEqual(matcher.adapter.writes, [])

  def test_exact_rematch_accepts_new_vectors_for_cosine_and_l2(self):
    for metric, score in (('COSINE', 1.0), ('L2', 0.0)):
      with self.subTest(metric=metric):
        matcher, _ = make(FakeAdapter(all_match('gid-A', score)),
                          write_enabled=True, similarity_metric=metric)
        query_vectors = [vec(i, 1, 0, 0) for i in range(3)]
        new_vector = vec(9, 9, 0, 0)
        feed(matcher, 't1', query_vectors)
        feed(matcher, 't1', query_vectors + [new_vector, new_vector])

        matcher.process_frame([])

        self.assertEqual(len(matcher.adapter.writes), 1)
        vectors = matcher.adapter.writes[0][3]
        self.assertEqual(len(vectors), 1)
        np.testing.assert_array_equal(vectors[0], new_vector)

  def test_mixed_rematch_keeps_non_exact_and_new_vectors(self):
    def results(vectors):
      return [[{'uuid': 'gid-A', '_distance': score}] for score in (1.0, 0.8, 1.0)]

    matcher, _ = make(FakeAdapter(results), write_enabled=True)
    query_vectors = [vec(i, 1, 0, 0) for i in range(3)]
    new_vector = vec(9, 9, 0, 0)
    feed(matcher, 't1', query_vectors)
    feed(matcher, 't1', query_vectors + [new_vector])

    matcher.process_frame([])

    vectors = matcher.adapter.writes[0][3]
    self.assertEqual(len(vectors), 2)
    np.testing.assert_array_equal(vectors[0], query_vectors[1])
    np.testing.assert_array_equal(vectors[1], new_vector)

  def test_exact_rematch_preserves_local_camera_enrollment(self):
    matcher, _ = make(FakeAdapter(all_match('gid-A', 1.0)), write_enabled=True)
    query_vectors = [vec(i, 1, 0, 0) for i in range(3)]
    feed(matcher, 't1', query_vectors, bbox_px_area=8000)
    feed(matcher, 't1', [query_vectors[-1]], bbox_px_area=8000)

    matcher.process_frame([])

    self.assertEqual(len(matcher.adapter.writes), 1)
    self.assertEqual(len(matcher.adapter.writes[0][3]), 3)

  def test_exact_rematch_repeat_is_not_written_on_stale_flush(self):
    now = [0.0]
    matcher, _ = make(FakeAdapter(all_match('gid-A', 1.0)), write_enabled=True,
                      clock=lambda: now[0], stale_feature_timeout_secs=5.0)
    feed(matcher, 't1', [vec(i, 1, 0, 0) for i in range(3)])
    now[0] = 6.0

    feed(matcher, 't1', [vec(2, 1, 0, 0)])

    self.assertEqual(matcher.adapter.writes, [])
    self.assertEqual(matcher._pending, {})

  def test_stale_flush(self):
    now = [0.0]
    matcher, _ = make(write_enabled=True, clock=lambda: now[0], stale_feature_timeout_secs=5.0)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    now[0] = 6.0
    matcher.process_frame([obs("t1", vec(5, 5, 0, 0))])  # still present
    self.assertEqual(len(matcher.adapter.writes), 1)

  def test_write_failure_disables_further_writes(self):
    adapter = FakeAdapter()
    adapter.write_error = RuntimeError("disk full")
    matcher, _ = make(adapter, write_enabled=True)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    matcher.process_frame([])
    self.assertFalse(matcher.write_healthy)
    adapter.write_error = None
    feed(matcher, "t2", [vec(i, 3, 0, 0) for i in range(3)])
    matcher.process_frame([])
    self.assertEqual(adapter.writes, [])

  def test_partial_write_confirms_and_disables(self):
    adapter = FakeAdapter()
    adapter.write_error = ReidPartialWriteError("1 of 3 failed")
    matcher, _ = make(adapter, write_enabled=True)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    matcher.process_frame([])
    self.assertFalse(matcher.write_healthy)
    self.assertTrue(matcher.write_confirmed)

  def test_no_valid_vectors_keeps_writes_healthy(self):
    adapter = FakeAdapter()
    adapter.write_error = ReidNoValidVectorsError("all skipped")
    matcher, _ = make(adapter, write_enabled=True)
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    matcher.process_frame([])
    self.assertTrue(matcher.write_healthy)


class TestConfig(unittest.TestCase):

  def test_from_reid_config(self):
    cfg = MatcherConfig.from_reid_config({
      "feature_accumulation_threshold": 8, "similarity_metric": "L2",
      "feature_slice_size": 4, "stale_feature_timeout_secs": 2})
    self.assertEqual((cfg.minimum_feature_count, cfg.similarity_metric,
                      cfg.similarity_threshold, cfg.feature_slice_size),
                     (8, "L2", 40.0, 4))

  def test_cosine_maps_to_ip_on_adapter(self):
    matcher, _ = make()
    self.assertEqual(matcher.adapter.similarity_metric, "IP")

  def test_invalid_cosine_threshold(self):
    with self.assertRaises(ValueError):
      MatcherConfig.from_reid_config({"similarity_threshold": 3})


class TestEmbeddingDiagnostics(unittest.TestCase):

  def test_frozen_embedding_is_counted(self):
    matcher, _ = make()
    frozen = vec(1, 0, 0, 0)
    feed(matcher, "t1", [frozen] * 4)
    matcher.process_frame([])
    self.assertEqual(matcher.stats["embeddings_changed"], 1)
    self.assertEqual(matcher.stats["embeddings_repeated"], 3)
    self.assertEqual(matcher.stats["tracks_single_embedding"], 1)

  def test_changing_embeddings_are_counted(self):
    matcher, _ = make()
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    matcher.process_frame([])
    self.assertEqual(matcher.stats["embeddings_changed"], 3)
    self.assertEqual(matcher.stats["embeddings_repeated"], 0)
    self.assertEqual(matcher.stats["tracks_single_embedding"], 0)


class TestDecisionDiagnostics(unittest.TestCase):

  def test_no_match_reports_best_score(self):
    matcher, decisions = make(FakeAdapter(all_match("gid-A", 0.3)))
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    (d,) = decisions
    self.assertFalse(d["matched"])
    self.assertAlmostEqual(d["best_score"], 0.3, places=6)
    self.assertEqual(d["best_gid"], "gid-A")
    self.assertEqual(d["threshold"], 0.5)

  def test_empty_gallery_has_no_best_score(self):
    matcher, decisions = make()
    feed(matcher, "t1", [vec(i, 1, 0, 0) for i in range(3)])
    self.assertIsNone(decisions[0]["best_score"])


if __name__ == "__main__":
  unittest.main()
