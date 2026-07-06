# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod

import numpy as np

from scene_common import log


class ReIDDatabase(ABC):
  def prepareReidDict(self, embedding_vector, dimensions=None,
                      normalize_embeddings=False):
    """Prepare a normalized/validated ReID payload from arbitrary vector shapes.

    Supports vectors shaped as (N,), (1, N), or any array-like object by
    flattening to 1D. If dimensions is None, dimensions are inferred from the
    flattened vector length.
    """
    if embedding_vector is None:
      log.warning("prepareReidDict: Empty embedding vector, skipping this vector")
      return None

    vec_array = np.asarray(embedding_vector, dtype="float32").reshape(-1)
    inferred_dimensions = int(vec_array.shape[0])
    expected_dimensions = inferred_dimensions if dimensions is None else int(dimensions)

    if inferred_dimensions != expected_dimensions:
      log.warning(
        f"prepareReidDict: Expected vector shape ({expected_dimensions},) but got {vec_array.shape}, skipping this vector")
      return None

    if not np.all(np.isfinite(vec_array)):
      log.warning("prepareReidDict: Vector contains non-finite values, skipping this vector")
      return None

    if normalize_embeddings:
      norm = np.linalg.norm(vec_array)
      if not np.isfinite(norm) or norm == 0.0:
        log.warning(f"prepareReidDict: Invalid vector norm ({norm}), skipping this vector")
        return None
      vec_array = vec_array / norm

    return {
      "embedded_vector": vec_array.astype("float32", copy=False),
      "dimensions": expected_dimensions,
    }

  def prepareReidVector(self, reid_vector, dimensions,
                        normalize_embeddings=False):
    """Backward-compatible wrapper returning only the prepared vector."""
    prepared_reid = self.prepareReidDict(
      reid_vector,
      dimensions,
      normalize_embeddings=normalize_embeddings)
    if prepared_reid is None:
      return None
    return prepared_reid["embedded_vector"]

  @abstractmethod
  def connect(self, hostname):
    """Connect to the database using the specified hostname."""
    return

  @abstractmethod
  def addSchema(self, set_name, similarity_metric, dimensions):
    """Add a schema to the database for storing Re-ID vectors."""
    return

  @abstractmethod
  def addEntry(self, uuid, rvid, object_type, reid_vectors, set_name, **metadata):
    """Add entries to the database for Re-ID vectors with optional metadata."""
    return

  @abstractmethod
  def findSchema(self, set_name):
    """Check whether a schema with a given name exists in the database."""
    return

  @abstractmethod
  def findMatches(self, object_type, reid_vectors, set_name, k_neighbors, **constraints):
    """Search database entries using hybrid metadata+vector matching."""
    return
