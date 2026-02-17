# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import json
import socket
import threading

import numpy as np
import vdms

from controller.reid import ReIDDatabase
from scene_common import log

DEFAULT_HOSTNAME = os.getenv("VDMS_HOSTNAME", "vdms.scenescape.intel.com")
DIMENSIONS = 256
K_NEIGHBORS = 1
SCHEMA_NAME = "reid_vector"
SIMILARITY_METRIC = "L2"

class VDMSDatabase(ReIDDatabase):
  def __init__(self, set_name=SCHEMA_NAME,
               similarity_metric=SIMILARITY_METRIC, dimensions=DIMENSIONS):
    # Initialize VDMS without TLS to avoid PMGD initialization issues in containerized environment
    # TLS can be re-enabled after VDMS resolves container compatibility issues
    self.db = vdms.vdms()
    self.set_name = set_name
    self.similarity_metric = similarity_metric
    self.dimensions = dimensions
    self.lock = threading.Lock()
    return

  def sendQuery(self, query, blob=None):
    """
    Helper function for handling the responses from sending queries to VDMS. There are three
    possible responses from VDMS when sending the query.
      - "NOT CONNECTED", if the database connection is not active
      - None, if the response fails to receive a packet
      - (response, res_arr), if query gets a response from VDMS

    @param   query      The list of queries to send to VDMS
    @param   blob       Blobs of data to send with queries (optional)
    @return  responses  The response dict from VDMS
    """
    responses = []
    response_blob = []
    with self.lock:
      if blob:
        query_response = self.db.query(query, blob)
      else:
        query_response = self.db.query(query)
    if query_response and query_response != "NOT CONNECTED":
      response_blob = query_response[1]
      # Check for transaction-level failure
      if (len(query_response[0]) == 1
          and isinstance(query_response[0][0], dict)
          and 'FailedCommand' in query_response[0][0]):
        log.warning(f"VDMS transaction failed: {query_response[0][0]}")
        return responses, response_blob
      for (item, response) in zip(query, query_response[0]):
        query_type = next(iter(item))
        response_data = response.get(query_type, {})
        responses.append(response_data)
    else:
      log.warning(f"Failed to send query to VDMS container: {query}")
    return responses, response_blob

  def connect(self, hostname=DEFAULT_HOSTNAME):
    try:
      self.db.connect(hostname)
      if not self.findSchema(self.set_name):
        self.addSchema(self.set_name, self.similarity_metric, self.dimensions)
    except socket.error as e:
      log.warning(f"Failed to connect to VDMS container: {e}")
    return

  def addSchema(self, set_name, similarity_metric, dimensions):
    query = [{
      "AddDescriptorSet": {
        "name": f"{set_name}",
        "metric": f"{similarity_metric}",
        "dimensions": dimensions
      }
    }]
    response, _ = self.sendQuery(query)
    if response and response[0].get('status') != 0:
      log.warning(
        f"Failed to add the descriptor set to the database. Recieved response {response[0]}")
    return

  def addEntry(self, uuid, rvid, object_type, reid_vectors, set_name=SCHEMA_NAME, **metadata):
    """
    Add entries to database with visual embeddings and optional semantic metadata.
    Implements schema-less metadata storage for flexible attribute evolution.

    @param   uuid         Unique ID for the object
    @param   rvid         ID of the object from the motion tracker
    @param   object_type  Class of the object (Person, Vehicle, etc.)
    @param   reid_vectors Re-ID embeddings produced by a detection model
    @param   set_name     Name of the set to add the new entry to
    @param   metadata     Optional semantic attributes (age, gender, color, etc.)
    @return  None
    """
    # Build properties with standard fields
    properties = {
      "uuid": f"{uuid}",
      "rvid": f"{rvid}",
      "type": f"{object_type}"
    }

    # Add semantic metadata attributes (schema-less)
    # Metadata can include: age, gender, color, make, model, confidence_scores, etc.
    for key, value in metadata.items():
      if isinstance(value, dict):
        # Serialize dict as JSON string
        properties[key] = json.dumps(value)
      else:
        # Store as string
        properties[key] = str(value)

    query = {
      "AddDescriptor": {
        "set": f"{set_name}",
        "properties": properties
      }
    }
    # Convert vectors to JSON-serializable format (float32 -> float) and to bytes
    # VDMS API expects: query([q1, q2, ...], [blob1, blob2, ...])
    # Blobs are consumed sequentially, one per AddDescriptor query (flat list)
    descriptor_blobs = []
    add_query = []
    for reid_vector in reid_vectors:
      # Ensure vector is float32, then convert to bytes for VDMS
      vec_array = np.array(reid_vector, dtype="float32")
      descriptor_blobs.append(vec_array.tobytes())
      # Create query dict for each vector
      add_query.append({
        "AddDescriptor": {
          "set": f"{set_name}",
          "properties": properties.copy()
        }
      })

    response, _ = self.sendQuery(add_query, descriptor_blobs)  # Flat list of blobs
    if response:
      for item in response:
        if item.get('status') != 0:
          log.warning(
            f"Failed to add the descriptor to the database. Received response {item}")
    return

  def findSchema(self, set_name):
    query = [{
      "FindDescriptorSet": {
        "set": f"{set_name}"
      }
    }]
    response, _ = self.sendQuery(query)
    if response and response[0].get('status') == 0 and response[0].get('returned') > 0:
      return True
    return False

  def _build_query_constraints(self, object_type, **constraints):
    """
    Build query constraints for TIER 1 metadata filtering.

    Constraint routing logic:
    - Object type is always AND constraint (required field)
    - If value is dict with 'confidence' key (new metadata format):
      - confidence >= 0.8: AND constraints (all must match - strict)
      - confidence < 0.8: OR constraints (at least one must match - flexible)
      - Extract 'value' field for VDMS query
    - If value is non-dict or dict without confidence (legacy format):
      - OR constraints (at least one must match - flexible)
    - Non-numeric values: OR constraints (default to flexible)

    @param   object_type  Class of the object (Person, Vehicle, etc.)
    @param   constraints  Optional metadata filters (key-value pairs, may be dicts with value/confidence)
    @return  query_constraints  Dictionary with "type", optional AND fields, and optional "or" array
    """
    # TIER 1: Build dynamic constraints for metadata filtering
    # Object type is always filtered (AND constraint - required)
    query_constraints = {
      "type": ["==", f"{object_type}"]
    }

    # Separate constraints by confidence level
    and_constraints = {}
    or_constraints = []

    if constraints:
      for key, value in constraints.items():
        if value is not None:
          # Extract actual value and confidence from metadata dict
          actual_value = value
          confidence = None

          # Handle new metadata format: {value: <data>, model_name: <model>, confidence: <score>}
          if isinstance(value, dict) and 'value' in value:
            actual_value = value['value']
            confidence = value.get('confidence')

          # Determine constraint type based on confidence
          try:
            # Use extracted confidence if available
            if confidence is not None:
              conf_value = float(confidence)
              # If confidence >= 0.8, treat as AND constraint (strict matching)
              if conf_value >= 0.8:
                and_constraints[key] = ["==", str(actual_value)]
              # If confidence < 0.8, treat as OR constraint (flexible matching)
              else:
                or_constraints.append({key: ["==", str(actual_value)]})
            else:
              # No confidence available, check if actual_value itself is numeric
              try:
                conf_value = float(actual_value) if isinstance(actual_value, (int, float, str)) else None
                if conf_value is not None and conf_value >= 0.8:
                  and_constraints[key] = ["==", str(actual_value)]
                else:
                  or_constraints.append({key: ["==", str(actual_value)]})
              except (ValueError, TypeError):
                # Not numeric, treat as OR constraint (flexible)
                or_constraints.append({key: ["==", str(actual_value)]})
          except (ValueError, TypeError):
            # Confidence value not convertible to float, treat as OR constraint
            or_constraints.append({key: ["==", str(actual_value)]})

      # Add AND constraints directly to query_constraints
      query_constraints.update(and_constraints)

      # Add OR constraints if any exist
      if or_constraints:
        query_constraints["or"] = or_constraints

    return query_constraints

  def findMatches(self, object_type, reid_vectors, set_name=SCHEMA_NAME,
                   k_neighbors=K_NEIGHBORS, **constraints):
    """
    2-Tier Hybrid Search: TIER 1 (metadata filtering) + TIER 2 (vector similarity)

    @param   object_type  Class of the source of the reid vector (Person, Vehicle, etc.)
    @param   reid_vectors Re-ID embeddings produced by a detection model
    @param   set_name     Name of the set to find similarity scores
    @param   k_neighbors  Number of similar entries to return
    @param   constraints  Optional metadata filters built as VDMS constraint expressions
    @return  result       Entries with the closest similarity scores
    """
    # TIER 1: Build dynamic constraints for metadata filtering
    query_constraints = self._build_query_constraints(object_type, **constraints)

    find_query = {
      "FindDescriptor": {
        "set": f"{set_name}",
        "constraints": query_constraints,
        "k_neighbors": k_neighbors,
        "results": {
          "list": [
            "uuid",
            "rvid",
            "_distance",
          ],
          "blob": False
        }
      }
    }

    # TIER 2: Vector similarity search on filtered candidates
    blob = []
    for reid_vector in reid_vectors:
      # Ensure vector is float32, then convert to bytes for VDMS
      vec_array = np.array(reid_vector, dtype="float32")
      blob.append(vec_array.tobytes())  # Flat list of blobs

    query = [find_query] * len(reid_vectors)
    response, _ = self.sendQuery(query, blob)

    if response:
      result = [
        item.get('entities')
        for item in response
        if (item.get('status') == 0 and item.get('returned') > 0)
      ]
      return result
    return None
