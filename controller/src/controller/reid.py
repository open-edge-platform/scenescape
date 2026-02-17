# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod

class ReIDDatabase(ABC):
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
  def addEntry(self, uuid, rvid, object_type, reid_vectors, set_name, **metadata):
    """
    Adds entries to the database for the Re-ID vectors with optional metadata

    @param   uuid         Unique ID for the object
    @param   rvid         ID of the object from the motion tracker
    @param   object_type  Class of the object (Person, Vehicle, etc.)
    @param   reid_vectors Re-ID embeddings produced by a detection model
    @param   set_name     Name of the set to add the new entry to
    @param   metadata     Optional semantic attributes (age, gender, color, etc.)
    @return  None
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
