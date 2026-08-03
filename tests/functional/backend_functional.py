# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import random

import numpy as np

from tests.functional import FunctionalTest
from tests.functional.reid_backend import (
  REID_DATABASE,
  connect_reid_database,
  create_reid_database,
)
from tests.utils.log import get_logger

log = get_logger(__name__)


class BackendFunctionalTest(FunctionalTest):
  def reid_connect(self, use_tls=True):
    self.vdb = create_reid_database()
    connect_reid_database(self.vdb, use_tls=use_tls)
    return

  def generate_random_vector(self, floor=-1, ceiling=1, vsize=256):
    return [random.uniform(floor, ceiling) for _ in range(vsize)]

  def get_similarity_comparison(self, reid_vectors=1, set_name="reid_vector"):
    """Get similarity comparison results for the configured ReID backend."""
    assert isinstance(reid_vectors, list) or isinstance(reid_vectors, int), \
      log.error("reid_vectors is neither a list nor an integer!")

    if type(reid_vectors) == int:
      iterations = reid_vectors
      reid_vectors = []
      for _ in range(iterations):
        values = [random.uniform(-1, 1) for _ in range(256)]
        reid_vectors.append(values)

    if REID_DATABASE == "QDRANT":
      # Query the adapter's configured set; callers that need a custom collection
      # should bind the adapter to that set_name before searching.
      if set_name != self.vdb.set_name:
        self.vdb.set_name = set_name
      response = []
      for reid_vector in reid_vectors:
        matches = self.vdb.findMatches(
          "person",
          [reid_vector],
          k_neighbors=20)
        entities = matches[0] if matches else []
        response.append({
          "status": 0,
          "returned": len(entities),
          "entities": entities,
        })
      return response, []

    blob = [[np.array(reid_vector, dtype="float32").tobytes()] for reid_vector in reid_vectors]
    find = [{
      "FindDescriptor": {
        "set": set_name,
        "k_neighbors": 20,
        "results": {
          "list": ["_distance"],
          "blob": True
        }
      }
    }]
    query = find * len(reid_vectors)
    return self.vdb.sendQuery(query, blob)

  def delete_descriptors(self, set_name, run_id):
    """Best-effort removal of descriptors created by a single test run."""
    if REID_DATABASE == "QDRANT":
      try:
        from qdrant_client.http import models
        self.vdb.client.delete(
          collection_name=set_name,
          points_selector=models.FilterSelector(
            filter=models.Filter(must=[
              models.FieldCondition(
                key="run_id",
                match=models.MatchValue(value=run_id),
              )
            ])
          ),
        )
      except Exception as exc:
        log.warning(f"Failed to delete Qdrant points for run {run_id}: {exc}")
      return

    query = [{
      "DeleteDescriptor": {
        "set": set_name,
        "constraints": {
          "run_id": ["==", run_id]
        }
      }
    }]
    try:
      response, _ = self.vdb.sendQuery(query)
      log.debug(f"delete_descriptors RESPONSE: {response}")
    except Exception as exc:
      log.warning(f"Failed to delete descriptors for run {run_id}: {exc}")
    return
