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
DEFAULT_CONFIDENCE_THRESHOLD = float(os.getenv("VDMS_CONFIDENCE_THRESHOLD", "0.8"))
DEFAULT_CA_CERT = os.getenv("VDMS_CA_CERT", "/run/secrets/certs/scenescape-ca.pem")
DEFAULT_CLIENT_CERT = os.getenv("VDMS_CLIENT_CERT", "/run/secrets/certs/scenescape-vdms-c.crt")
DEFAULT_CLIENT_KEY = os.getenv("VDMS_CLIENT_KEY", "/run/secrets/certs/scenescape-vdms-c.key")
DIMENSIONS = 256
K_NEIGHBORS = 1
SCHEMA_NAME = "reid_vector"
SIMILARITY_METRIC = "L2"
# Tolerance applied to the theoretical [-1, 1] IP score bounds to absorb
# float32 rounding errors from VDMS normalization and inner-product computation.
COSINE_SIMILARITY_TOLERANCE = 1e-6
SCHEMA_MARKER_CLASS = "ReidSchemaMarker"

class VDMSDatabase(ReIDDatabase):
  def __init__(self, set_name=SCHEMA_NAME,
               similarity_metric=SIMILARITY_METRIC, dimensions=DIMENSIONS,
               confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD,
               ca_cert=DEFAULT_CA_CERT, client_cert=DEFAULT_CLIENT_CERT,
               client_key=DEFAULT_CLIENT_KEY):
    self.db = vdms.vdms(
      use_tls=True,
      ca_cert_file=ca_cert,
      client_cert_file=client_cert,
      client_key_file=client_key
    )
    self.set_name = set_name
    self.similarity_metric = similarity_metric
    self.dimensions = dimensions
    self.confidence_threshold = confidence_threshold
    self.lock = threading.Lock()
    self._schema_lock = threading.Lock()
    self._schema_ready = False
    return

  def _usesInnerProductMetric(self):
    """Return True when descriptor metric is Inner Product."""
    metric = str(self.similarity_metric).strip().upper()
    return metric == "IP"

  def _isValidSimilarityScore(self, score):
    """Validate similarity score according to active metric semantics."""
    try:
      value = float(score)
    except (TypeError, ValueError):
      return False

    if not np.isfinite(value):
      return False

    # With normalized embeddings, Inner Product must stay within [-1, 1].
    # Allow a small tolerance to absorb float32 rounding from VDMS.
    if self._usesInnerProductMetric() and (value < -(1.0 + COSINE_SIMILARITY_TOLERANCE) or value > (1.0 + COSINE_SIMILARITY_TOLERANCE)):
      return False

    return True

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
        if not isinstance(response_data, dict):
          log.debug(f"sendQuery: Non-dict payload for {query_type}: {response_data!r}")
          response_data = {}
        responses.append(response_data)
    else:
      log.warning(f"Failed to send query to VDMS container: {query}")
    return responses, response_blob

  def connect(self, hostname=DEFAULT_HOSTNAME):
    try:
      self.db.connect(hostname)
      if self.dimensions is not None:
        with self._schema_lock:
          self.ensureSchemaInner(
              int(self.dimensions),
              str(self.similarity_metric).strip().upper(),
              "connect")
          self._schema_ready = True
    except RuntimeError as e:
      log.error(f"Failed to initialize VDMS schema: {e}")
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
    if not response:
      log.warning("addSchema: No response from VDMS when creating descriptor set")
      return False
    if response[0].get('status') != 0:
      log.warning(
        f"Failed to add the descriptor set to the database. Received response {response[0]}")
      return False
    return True

  def ensureSchemaInner(self, requested_dimensions, expected_metric, caller):
    """
    Core attempt-first schema setup shared by connect() and ensureSchema().
    Avoids FindDescriptorSet on a missing set (triggers a VDMS v2.12 bug):
    attempt AddDescriptorSet first; only probe schema metadata when
    AddDescriptorSet reports the set already exists.

    @param   requested_dimensions  Number of dimensions for the descriptor set
    @param   expected_metric       Similarity metric (e.g. 'L2', 'IP')
    @param   caller                Name of the calling method for log messages
    @raises  RuntimeError          On schema mismatch or unrecoverable VDMS error
    @return  None. Updates self.dimensions on success.
    """
    response, _ = self.sendQuery([{
        "AddDescriptorSet": {
            "name": self.set_name,
            "metric": expected_metric,
            "dimensions": requested_dimensions
        }
    }])

    if not response:
      raise RuntimeError(
          f"{caller}: No response from VDMS for descriptor set '{self.set_name}'.")

    if response[0].get('status') == 0:
      log.info(f"{caller}: Created descriptor set '{self.set_name}' "
          f"({requested_dimensions}D, {expected_metric})")
      self._writeSchemaMarker(requested_dimensions, expected_metric, skip_exists_check=True)
      self.dimensions = requested_dimensions
      return

    # Non-zero: set likely already exists — verify against the schema marker entity
    log.debug(f"{caller}: AddDescriptorSet status={response[0].get('status')}; "
              f"set may already exist, verifying against schema marker.")
    marker_exists, marker_dimensions, marker_metric = self._readSchemaMarker()

    if not marker_exists:
      # Backward-compat: descriptor set exists but marker is missing. Use FindDescriptorSet once
      # (safe here because AddDescriptorSet already indicated the set exists) to verify before
      # writing a marker that other controllers will treat as authoritative.
      schema_exists, schema_dimensions, schema_metric = self.findSchemaMetadata(self.set_name)
      if not schema_exists or schema_dimensions is None or schema_metric is None:
        raise RuntimeError(
            f"{caller}: '{self.set_name}' exists but no schema marker found, and descriptor set metadata "
            "could not be read for verification. Recreate the descriptor set to continue.")
      if str(schema_metric).strip().upper() != expected_metric:
        raise RuntimeError(
            f"{caller}: '{self.set_name}' uses metric {schema_metric}, expected {expected_metric}. "
            "Recreate the descriptor set with matching metric.")
      if schema_dimensions != requested_dimensions:
        raise RuntimeError(
            f"{caller}: '{self.set_name}' has {schema_dimensions} dimensions, expected {requested_dimensions}. "
            "Recreate the descriptor set with matching dimensions.")
      log.warning(
          f"{caller}: '{self.set_name}' exists but no schema marker found; writing marker for future instances.")
      self._writeSchemaMarker(requested_dimensions, expected_metric, skip_exists_check=True)
      self.dimensions = requested_dimensions
      return

    if marker_dimensions is None or marker_metric is None:
      raise RuntimeError(
          f"{caller}: '{self.set_name}' schema marker returned no dimensions "
          f"for verification (dimensions={marker_dimensions}, metric={marker_metric}). "
          "Cannot safely confirm compatibility.")

    if str(marker_metric).strip().upper() != expected_metric:
      raise RuntimeError(
          f"{caller}: '{self.set_name}' uses metric {marker_metric}, "
          f"expected {expected_metric}. "
          "Recreate the descriptor set with matching metric.")
    if marker_dimensions != requested_dimensions:
      raise RuntimeError(
          f"{caller}: '{self.set_name}' has {marker_dimensions} dimensions, "
          f"expected {requested_dimensions}. "
          "Recreate the descriptor set with matching dimensions.")

    log.info(f"{caller}: Verified existing descriptor set '{self.set_name}' "
             f"against schema marker ({marker_dimensions}D, {marker_metric})")
    self.dimensions = requested_dimensions

  def _writeSchemaMarker(self, dimensions, metric, skip_exists_check=False):
    """
    Record the descriptor set's dimensions and metric as a regular VDMS entity.
    This sidesteps FindDescriptorSet's unreliable metadata response (VDMS v2.12)
    by storing schema info through a query path that works reliably.

    Uses a find-then-add pattern since AddEntity does not support an inline
    "skip if exists" condition. A race between instances is possible but
    harmless since both would write the same configured values.

    @param  dimensions  Number of dimensions for the descriptor set
    @param  metric      Similarity metric used for the descriptor set
    @param  skip_exists_check   If True, skip the existence check and write the marker
                                unconditionally. Callers should only pass True when they
                                have already established the marker doesn't exist (e.g.
                                immediately after creating the descriptor set or after a
                                prior _readSchemaMarker() call came back empty), to avoid
                                a redundant duplicate query.
    """
    if not skip_exists_check:
      marker_exists, _, _ = self._readSchemaMarker()
      if marker_exists:
        log.debug(f"_writeSchemaMarker: Marker already exists for '{self.set_name}', skipping write")
        return
    query = [{"AddEntity": {"class": SCHEMA_MARKER_CLASS,
              "properties": {"set_name": self.set_name, "dimensions": dimensions, "metric": metric}}}]
    response, _ = self.sendQuery(query)
    if not response or response[0].get('status') != 0:
      log.warning(f"_writeSchemaMarker: Failed to write schema marker for '{self.set_name}'. Response: {response}")

  def _readSchemaMarker(self):
    """
    Read the schema marker entity for this descriptor set to verify
    dimensions/metric reliably, bypassing FindDescriptorSet.

    @return  (exists, dimensions, metric) tuple. (False, None, None) if not found.
    """
    query = [{
      "FindEntity": {
        "class": SCHEMA_MARKER_CLASS,
        "constraints": {"set_name": ["==", self.set_name]},
        "results": {"list": ["set_name", "dimensions", "metric"]}
      }
    }]
    response, _ = self.sendQuery(query)
    if not response or response[0].get('status') != 0:
      return False, None, None

    payload = response[0]
    marker_exists = payload.get('returned', 0) > 0 or bool(payload.get('entities'))
    if not marker_exists:
      return False, None, None

    dimensions = self._extractSchemaDimensions(payload)
    metric = self._extractSchemaMetric(payload)
    return True, dimensions, metric

  def ensureSchema(self, dimensions):
    with self._schema_lock:
      requested_dimensions = int(dimensions)
      if self._schema_ready:
        if int(self.dimensions) != requested_dimensions:
          raise ValueError(
            f"ReID schema already initialized with {self.dimensions} dimensions; "
            f"incoming vector has {requested_dimensions} dimensions. "
            "Restart the controller and flush the VDMS descriptor set to change dimensions.")
        return
      self.ensureSchemaInner(
          requested_dimensions,
          str(self.similarity_metric).strip().upper(),
          "ensureSchema")
      self._schema_ready = True

  def addEntry(self, uuid, rvid, object_type, reid_vectors, set_name=SCHEMA_NAME, persist=None, **metadata):
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

    # Store persist attributes as serialized JSON with timestamp
    if persist:
      persist = persist.copy()  # avoid mutating the caller's dict
      persist_timestamp = persist.pop('timestamp')
      properties["persist"] = json.dumps(persist)
      properties["persist_timestamp"] = persist_timestamp
      log.debug(f"[VDMS] addEntry: Storing persist keys={list(persist.keys())} for uuid={uuid}")

    # Add semantic metadata attributes (schema-less)
    # Metadata can include: age, gender, color, make, model, confidence_scores, etc.
    for key, value in metadata.items():
      if isinstance(value, dict):
        # For metadata dicts with 'label' and optional confidence, store ONLY the label
        # This ensures VDMS constraints can match properly (e.g., gender=['==', 'Male'])
        # Example: {'label': 'Male', 'confidence': 0.95} → store 'Male'
        if 'label' in value:
          properties[key] = str(value['label'])
          log.debug(f"[VDMS] addEntry: Extracted label '{value['label']}' from {key} metadata dict")
        else:
          # If no label, serialize as JSON
          properties[key] = json.dumps(value)
          log.debug(f"[VDMS] addEntry: Serialized {key} as JSON (no label field)")
      else:
        # Store as string
        properties[key] = str(value)

    # Convert vectors to JSON-serializable format (float32 -> float) and to bytes
    # VDMS API expects: query([q1, q2, ...], [blob1, blob2, ...])
    # Blobs are consumed sequentially, one per AddDescriptor query (flat list)
    descriptor_blobs = []
    add_query = []
    normalize_embeddings = self._usesInnerProductMetric()

    for reid_vector in reid_vectors:
      prepared_reid = self.prepareReidDict(
        reid_vector,
        self.dimensions,
        normalize_embeddings=normalize_embeddings)
      if prepared_reid is None:
        continue

      vec_array = prepared_reid["embedded_vector"]
      descriptor_blobs.append(vec_array.tobytes())
      # Create query dict for each vector
      add_query.append({
        "AddDescriptor": {
          "set": f"{set_name}",
          "properties": properties.copy()
        }
      })

    if not add_query:
      log.warning("addEntry: No valid vectors to add (all skipped due to dimension mismatch or uninitialized dimensions)")
      return

    response, _ = self.sendQuery(add_query, descriptor_blobs)  # Flat list of blobs
    if response:
      success_count = 0
      for item in response:
        if item.get('status') == 0:
          success_count += 1
        else:
          log.warning(
            f"Failed to add the descriptor to the database. Received response {item}")
    else:
      log.error(f"addEntry: No response from VDMS when adding {len(add_query)} vectors")
    return

  def getPersistedAttributes(self, uuid, set_name=SCHEMA_NAME):
    """
    Retrieve the most recent persist attributes stored for a given object UUID.

    Queries VDMS for all descriptor entries matching the UUID, filters to those
    with persist data, and returns the attributes from the entry with the latest
    persist_timestamp. This ensures that when an object is re-identified via ReID,
    its most up-to-date attributes from its previous appearance are restored.

    @param   uuid      The object UUID to look up
    @param   set_name  Name of the VDMS descriptor set to query
    @return  dict      Deserialized persist attributes from the most recent entry,
                       or empty dict if no entry or persist data is found
    """
    query = [{
      "FindDescriptor": {
        "set": f"{set_name}",
        "constraints": {
          "uuid": ["==", f"{uuid}"]
        },
        "results": {
          "list": ["uuid", "persist", "persist_timestamp"],
          "blob": False
        }
      }
    }]
    response, _ = self.sendQuery(query)
    if not response or response[0].get('status') != 0:
      log.debug(f"[VDMS] getPersistedAttributes: No entry found for uuid={uuid}")
      return {}

    entities = response[0].get('entities', [])
    if not entities:
      return {}

    # Sort by timestamp descending to get the most recent entry
    entities_with_persist = [
      e for e in entities
      if isinstance(e.get('persist'), str) and
         e.get('persist').strip() and
         e.get('persist') != 'Missing property'
    ]

    if not entities_with_persist:
      log.debug(f"[VDMS] getPersistedAttributes: No persist data found for uuid={uuid}")
      return {}

    latest = max(entities_with_persist, key=lambda e: e.get('persist_timestamp', 0))
    try:
      return json.loads(latest['persist'])
    except (json.JSONDecodeError, TypeError) as e:
      log.warning(f"[VDMS] getPersistedAttributes: Failed to deserialize persist for uuid={uuid}: {e}")
      return {}

  def findSchema(self, set_name):
    schema_exists, _ = self.findSchemaDetails(set_name)
    return schema_exists

  def findSchemaDetails(self, set_name):
    schema_exists, schema_dimensions, _ = self.findSchemaMetadata(set_name)
    return schema_exists, schema_dimensions

  def findSchemaMetadata(self, set_name):
    query = [{
      "FindDescriptorSet": {
        "set": f"{set_name}"
      }
    }]
    response, _ = self.sendQuery(query)
    if not response:
      return False, None, None
    first_response = response[0]
    if not first_response or first_response.get('status') != 0 or first_response.get('returned', 0) <= 0:
      return False, None, None

    schema_dimensions = self._extractSchemaDimensions(first_response)
    schema_metric = self._extractSchemaMetric(first_response)
    return True, schema_dimensions, schema_metric

  def _extractSchemaDimensions(self, find_descriptor_set_response):
    # VDMS responses may return descriptor set fields at the top level or nested under
    # common payload keys like "entities" or "content".
    payloads = [find_descriptor_set_response]
    for key in ['entities', 'entity', 'content', 'results', 'DescriptorSet']:
      value = find_descriptor_set_response.get(key)
      if isinstance(value, dict):
        payloads.append(value)
      elif isinstance(value, list):
        payloads.extend(item for item in value if isinstance(item, dict))

    for payload in payloads:
      for key in ['dimensions', 'dimension']:
        if key in payload:
          try:
            return int(payload[key])
          except (TypeError, ValueError):
            log.warning(
              f"findSchemaDetails: Could not parse descriptor dimensions from key '{key}' value '{payload[key]}'")
            return None
    return None

  def _extractSchemaMetric(self, find_descriptor_set_response):
    # VDMS responses may return descriptor set fields at the top level or nested under
    # common payload keys like "entities" or "content".
    payloads = [find_descriptor_set_response]
    for key in ['entities', 'entity', 'content', 'results', 'DescriptorSet']:
      value = find_descriptor_set_response.get(key)
      if isinstance(value, dict):
        payloads.append(value)
      elif isinstance(value, list):
        payloads.extend(item for item in value if isinstance(item, dict))

    for payload in payloads:
      for key in ['metric', 'distance_metric', 'similarity_metric']:
        if key in payload and payload[key] is not None:
          return str(payload[key])
    return None

  def _buildQueryConstraints(self, object_type, **constraints):
    """
    Build query constraints for TIER 1 metadata filtering.

    VDMS constraint model: Only supports AND operations between property constraints.
    Constraint format for each property: [operator, value] for single constraint,
    or [op1, val1, op2, val2] for range constraint (e.g. ">=5" AND "<=10").

    Constraint routing logic:
    - Object type is always AND constraint (required field)
    - If value is dict with 'confidence' key (new metadata format):
      - confidence >= threshold (0.8): AND constraints (strict filtering in TIER 1)
      - confidence < threshold (0.8): IGNORED (relies on TIER 2 vector similarity for flexible matching)
      - Extract 'label' field for VDMS query value
    - If value is non-dict or dict without confidence (legacy format):
      - IGNORED (relies on TIER 2 vector similarity for matching)
    - Non-numeric values: IGNORED (relies on TIER 2 vector similarity)

    Note: Low-confidence and unspecified constraints are intentionally omitted from TIER 1
    filtering, allowing TIER 2 vector similarity search to provide flexible,
    confidence-aware matching. This simplification avoids VDMS limitations with complex
    OR constraint expressions across multiple properties.

    @param   object_type  Class of the object (Person, Vehicle, etc.)
    @param   constraints  Optional metadata filters (key-value pairs, may be dicts with label/confidence)
    @return  query_constraints  Dictionary with "type" and optional high-confidence AND fields
    """
    # TIER 1: Build dynamic constraints for metadata filtering
    # Object type is always filtered (AND constraint - required)
    query_constraints = {
      "type": ["==", f"{object_type}"]
    }

    log.debug(f"[VDMS] Building constraints for object_type={object_type}, threshold={self.confidence_threshold}")
    log.debug(f"[VDMS] Input constraints: {constraints}")

    # Apply only high-confidence constraints
    if constraints:
      for key, value in constraints.items():
        if value is None:
          log.debug(f"[VDMS] Skipping {key}: value is None")
          continue

        # Extract actual value and confidence from metadata dict
        actual_value = value
        confidence = None

        # Handle new metadata format: {label: <data>, model_name: <model>, confidence: <score>}
        if isinstance(value, dict) and 'label' in value:
          actual_value = value['label']
          confidence = value.get('confidence', None)
          log.debug(f"[VDMS] {key}: dict format - label={actual_value}, confidence={confidence}")
        else:
          log.debug(f"[VDMS] {key}: non-dict or no label - value={value}, type={type(value)}")

        # Only apply high-confidence constraints (>= 0.8)
        try:
          # If confidence is available, check if it meets threshold
          if confidence is not None:
            conf_value = float(confidence)
            # If confidence >= threshold, treat as AND constraint (strict matching)
            if conf_value >= self.confidence_threshold:
              query_constraints[key] = ["==", str(actual_value)]
              log.debug(f"[VDMS] ✓ ADDED: {key}={actual_value} (confidence={conf_value} >= {self.confidence_threshold})")
            else:
              # If confidence < threshold, ignore (rely on TIER 2 vector similarity)
              log.debug(f"[VDMS] ✗ IGNORED: {key} (confidence={conf_value} < {self.confidence_threshold}, will use TIER 2)")
          else:
            # No confidence available - skip this constraint, rely on TIER 2
            log.debug(f"[VDMS] ✗ IGNORED: {key} (no confidence available, will use TIER 2)")
        except (ValueError, TypeError):
          # Confidence value not convertible to float, ignore
          log.debug(f"[VDMS] ✗ IGNORED: {key} (confidence not convertible to float)")
          pass

    log.debug(f"[VDMS] Final TIER 1 query_constraints: {query_constraints}")
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
    log.debug(f"[VDMS] findMatches called: object_type={object_type}, k_neighbors={k_neighbors}")
    log.debug(f"[VDMS] findMatches constraints received: {constraints}")

    # TIER 1: Build dynamic constraints for metadata filtering
    query_constraints = self._buildQueryConstraints(object_type, **constraints)

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

    log.debug(f"[VDMS] Executing TIER 1 find with constraints: {query_constraints}")

    # TIER 2: Vector similarity search on filtered candidates
    blob = []
    normalize_embeddings = self._usesInnerProductMetric()
    for reid_vector in reid_vectors:
      vec_array = self.prepareReidVector(
        reid_vector,
        self.dimensions,
        normalize_embeddings=normalize_embeddings)
      if vec_array is None:
        continue
      blob.append(vec_array.tobytes())  # Flat list of blobs

    if len(blob) == 0:
      log.warning("findMatches: No valid vectors for similarity search")
      return None

    query = [find_query] * len(blob)
    response, _ = self.sendQuery(query, blob)

    log.debug(f"[VDMS] Raw VDMS response (truncated): status={response[0].get('status') if response else 'None'}, returned={response[0].get('returned') if response else 'None'}")
    if response and len(response) > 0:
      log.debug(f"[VDMS] Full first response: {response[0]}")

    if response:
      result = []
      for item in response:
        if item.get('status') != 0 or item.get('returned') <= 0:
          continue

        valid_entities = []
        for entity in item.get('entities', []):
          similarity = entity.get('_distance')
          if self._isValidSimilarityScore(similarity):
            valid_entities.append(entity)
          else:
            log.warning(
              f"findMatches: Discarding entity with invalid similarity score "
              f"{similarity} for metric {self.similarity_metric}")

        # Preserve 1:1 correspondence between query vectors and per-vector responses.
        # A successful query response with only invalid entities should still count as
        # "no usable match" for downstream majority-vote logic.
        result.append(valid_entities)

      log.debug(
        "[VDMS] findMatches returned %d per-vector result item(s) from %d valid "
        "query vector(s); VDMS response items=%d, input vectors=%d",
        len(result), len(blob), len(response), len(reid_vectors))

      return result
    log.debug("[VDMS] findMatches returned None (no response from VDMS)")
    return None
