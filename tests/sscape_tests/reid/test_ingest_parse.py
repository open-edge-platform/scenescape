# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Parsing of scene-track MQTT messages (shape taken from a live capture)."""

import base64
import json
import unittest
from collections import Counter

import numpy as np

from reid_service.ingest import parse_scene_message, parse_scene_topic


def _vector(seed, dims=256):
  return np.random.default_rng(seed).standard_normal(dims).astype(np.float32)


def _object(track_id, seed=1, dims=256, **extra):
  obj = {
    "category": "person",
    "confidence": 0.99,
    "id": track_id,
    "type": "person",
    "translation": [1.7, 4.5, 0.0],
    "size": [0.5, 0.5, 1.85],
    "velocity": [0.02, 0.03, 0.0],
    "rotation": [0, 0, 0, 1],
    "metadata": {
      "reid": {
        "embedding_vector": [_vector(seed, dims).tolist()],
        "embedding_dimensions": dims,
        "model_name": "torch-jit-export",
      },
    },
    "visibility": ["atag-qcam1", "atag-qcam2"],
    "similarity": None,
    "first_seen": "2026-10-14T15:25:08.831Z",
    "reid_state": "query_no_match",
  }
  obj.update(extra)
  return obj


def scene_message(objects, timestamp="2026-10-14T15:25:16.800Z"):
  return json.dumps({
    "debug_mac": "1b:a8:ae:6b:af:3b",
    "id": "1bee62fe-2fd2-4839-a929-efb7e0529de6",
    "timestamp": timestamp,
    "rate": 9.8,
    "objects": objects,
    "name": "Queuing",
    "unique_detection_count": 1,
  }).encode()


class TestTopic(unittest.TestCase):

  def test_scene_topic(self):
    self.assertEqual(
      parse_scene_topic("scenescape/data/scene/1bee62fe/person"), ("1bee62fe", "person"))

  def test_other_topics_ignored(self):
    self.assertIsNone(parse_scene_topic("scenescape/data/camera/cam1"))
    self.assertIsNone(parse_scene_topic("scenescape/external/1bee62fe/person"))
    self.assertIsNone(parse_scene_topic("scenescape/data/scene/1bee62fe"))


class TestMessage(unittest.TestCase):

  def test_parses_live_capture_shape(self):
    matched = _object(
      "0c34e67d-4307-4bd2-b30b-e196fc64ae1b", seed=2, similarity=1.0, reid_state="matched",
      previous_ids_chain=[{"id": "c6230452-abc7-4e3b-b630-5c0addc73bc2",
                           "timestamp": "2026-10-14T15:24:57.746Z", "similarity_score": 1.0}])
    ts, obs = parse_scene_message(
      scene_message([_object("bbd94e08-634b-44d6-960c-52e0e1e09440"), matched]))

    self.assertEqual(ts, "2026-10-14T15:25:16.800Z")
    self.assertEqual(len(obs), 2)
    first, second = obs
    self.assertEqual(first.track_id, "bbd94e08-634b-44d6-960c-52e0e1e09440")
    self.assertEqual(first.category, "person")
    self.assertEqual(first.embedding.shape, (1, 256))
    self.assertEqual(first.embedding.dtype, np.float32)
    np.testing.assert_allclose(first.embedding.reshape(-1), _vector(1), rtol=1e-6)
    self.assertEqual(first.cameras, ["atag-qcam1", "atag-qcam2"])
    self.assertIsNone(first.bbox_px_area)
    self.assertEqual(first.metadata, {})  # reid is not a semantic attribute
    self.assertEqual(first.upstream_reid_state, "query_no_match")
    self.assertEqual(second.upstream_reid_state, "matched")
    self.assertEqual(second.previous_ids, ["c6230452-abc7-4e3b-b630-5c0addc73bc2"])

  def test_base64_embedding_and_semantic_metadata(self):
    vec = _vector(3, 8)
    obj = _object("t1", dims=8)
    obj["metadata"] = {
      "reid": {"embedding_vector": base64.b64encode(vec.tobytes()).decode(),
               "embedding_dimensions": 8},
      "gender": {"label": "female", "confidence": 0.9},
    }
    _, (obs,) = parse_scene_message(scene_message([obj]))
    np.testing.assert_array_equal(obs.embedding.reshape(-1), vec)
    self.assertEqual(obs.metadata, {"gender": {"label": "female", "confidence": 0.9}})

  def test_pixel_bbox_area(self):
    obj = _object("t1", bounding_box_px={"x": 0, "y": 0, "width": 100, "height": 80})
    _, (obs,) = parse_scene_message(scene_message([obj]))
    self.assertEqual(obs.bbox_px_area, 8000.0)

  def test_object_without_embedding(self):
    obj = _object("t1")
    obj["metadata"] = {}
    _, (obs,) = parse_scene_message(scene_message([obj]))
    self.assertIsNone(obs.embedding)

  def test_malformed_embedding_is_counted_not_raised(self):
    obj = _object("t1")
    obj["metadata"]["reid"]["embedding_dimensions"] = 128  # 256 floats sent
    stats = Counter()
    _, (obs,) = parse_scene_message(scene_message([obj]), stats=stats)
    self.assertIsNone(obs.embedding)
    self.assertEqual(stats["embedding_decode_errors"], 1)

  def test_object_without_id_is_skipped(self):
    obj = _object("t1")
    del obj["id"]
    stats = Counter()
    _, obs = parse_scene_message(scene_message([obj]), stats=stats)
    self.assertEqual(obs, [])
    self.assertEqual(stats["objects_without_id"], 1)

  def test_empty_objects(self):
    _, obs = parse_scene_message(scene_message([]))
    self.assertEqual(obs, [])



TRACKER_MESSAGE = (
  b'{"id":"802d4e9a-3917-4334-b5aa-51ad8af52ed5","name":"Queuing",'
  b'"timestamp":"2026-10-14T16:11:47.410Z","objects":[{"id":"7b991d99-c141-4771-844c-86ac8c676bda",'
  b'"category":"person","translation":[1.0133798670948258,5.509819068170598,0.0],'
  b'"velocity":[-0.12729609314599617,0.16301011991687204,0.0],'
  b'"size":[0.7025958632569291,0.702595863256933,1.4820481635454506],'
  b'"rotation":[0.0,0.0,0.0,1.0],"confidence":0.9884886145591736}]}')


class TestTrackerServiceMessage(unittest.TestCase):
  """Captured from the Tracker service (tracker profile): no metadata at all."""

  def test_tracker_message_without_metadata(self):
    ts, (obs,) = parse_scene_message(TRACKER_MESSAGE)
    self.assertEqual(ts, "2026-10-14T16:11:47.410Z")
    self.assertEqual(obs.track_id, "7b991d99-c141-4771-844c-86ac8c676bda")
    self.assertEqual(obs.category, "person")
    self.assertIsNone(obs.embedding)
    self.assertEqual(obs.cameras, [])
    self.assertIsNone(obs.upstream_reid_state)
    self.assertEqual(obs.previous_ids, [])


if __name__ == "__main__":
  unittest.main()
