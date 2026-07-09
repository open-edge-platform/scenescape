# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
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
    """
    Connect to the database using the specified hostname

    @param   hostname  Hostname of the database
    @return  None
    """
    return

  @abstractmethod
  def addSchema(self, set_name, similarity_metric, dimensions):
    """
    Add a schema to the database for storing the Re-ID vectors

    @param   set_name           Name of the schema to add
    @param   similarity_metric  Metric for computing the similary scores of the Re-ID vectors
    @param   dimensions         Dimensions of the Re-ID vectors to store
    @return  None
    """
    return

  @abstractmethod
  def addEntry(self, uuid, rvid, object_type, reid_vectors, set_name, persist=None, **metadata):
    """
    Adds entries to the database for the Re-ID vectors with optional metadata

    @param   uuid         Unique ID for the object
    @param   rvid         ID of the object from the motion tracker
    @param   object_type  Class of the object (Person, Vehicle, etc.)
    @param   reid_vectors Re-ID embeddings produced by a detection model
    @param   set_name     Name of the set to add the new entry to
    @param   persist      Optional dict of persistent attributes to store alongside vectors
    @param   metadata     Optional semantic attributes (age, gender, color, etc.)
    @return  None
    """
    return

  @abstractmethod
  def getPersistedAttributes(self, uuid, set_name=None):
    """
    Retrieve the most recently stored persist attributes for a given UUID.

    @param   uuid      The object UUID to look up
    @param   set_name  Optional name of the descriptor set to query
    @return  dict      Deserialized persist attributes, or empty dict if not found
    """
    return

  @abstractmethod
  def findSchema(self, set_name):
    """
    Check whether a schema with a given name already exists in the database

    @param   set_name  Name of the set to check for existence
    @return  bool      Returns True if a match exists in the database;
                       otherwise, returns False.
    """
    return

  @abstractmethod
  def findMatches(self, object_type, reid_vectors, set_name, k_neighbors, **constraints):
    """
    Search the database for entries with the closest similarity scores to the given vector
    using 2-tier hybrid search: TIER 1 (metadata filtering) + TIER 2 (vector similarity)

    @param   object_type  Class of the source of the reid vector (Person, Vehicle, etc.)
    @param   reid_vectors Re-ID embeddings produced by a detection model
    @param   set_name     Name of the set to find similarity scores
    @param   k_neighbors  Number of similar entries to return
    @param   constraints  Optional metadata filters (age, gender, color, etc.)
    @return  iterable     Entries with the closest similarity scores
    """
    return
