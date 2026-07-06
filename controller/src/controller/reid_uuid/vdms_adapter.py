# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import socket
import threading

import numpy as np
import vdms

from controller.reid_uuid.database import ReIDDatabase
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
    """Send query to VDMS and normalize response payload structure."""
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
    """Core attempt-first schema setup shared by connect() and ensureSchema()."""
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
      self.dimensions = requested_dimensions
      return

    # Non-zero: set likely already exists - now safe to probe with FindDescriptorSet
    log.debug(f"{caller}: AddDescriptorSet status={response[0].get('status')}; "
              f"set may already exist, probing metadata.")
    schema_exists, schema_dimensions, schema_metric = self.findSchemaMetadata(self.set_name)

    if not schema_exists:
      raise RuntimeError(
          f"{caller}: AddDescriptorSet failed and set not found. "
          f"Response: {response[0]}")
    if schema_dimensions is None:
      raise RuntimeError(
          f"{caller}: '{self.set_name}' exists but returned no dimensions. "
          "Recreate the descriptor set to continue.")
    if schema_metric is None:
      raise RuntimeError(
          f"{caller}: '{self.set_name}' exists but returned no metric. "
          "Recreate the descriptor set to continue.")
    if str(schema_metric).strip().upper() != expected_metric:
      raise RuntimeError(
          f"{caller}: '{self.set_name}' uses metric {schema_metric}, "
          f"expected {expected_metric}. "
          "Recreate the descriptor set with matching metric.")
    if schema_dimensions != requested_dimensions:
      raise RuntimeError(
          f"{caller}: '{self.set_name}' has {schema_dimensions} dimensions, "
          f"expected {requested_dimensions}. "
          "Recreate the descriptor set with matching dimensions.")

    log.info(f"{caller}: Verified existing descriptor set '{self.set_name}' "
             f"({schema_dimensions}D, {schema_metric})")
    self.dimensions = requested_dimensions

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

  def addEntry(self, uuid, rvid, object_type, reid_vectors, set_name=SCHEMA_NAME, **metadata):
    """Add entries to database with visual embeddings and optional semantic metadata."""
    # Build properties with standard fields
    properties = {
      "uuid": f"{uuid}",
      "rvid": f"{rvid}",
      "type": f"{object_type}"
    }

    for key, value in metadata.items():
      if isinstance(value, dict):
        if 'label' in value:
          properties[key] = str(value['label'])
          log.debug(f"[VDMS] addEntry: Extracted label '{value['label']}' from {key} metadata dict")
        else:
          properties[key] = json.dumps(value)
          log.debug(f"[VDMS] addEntry: Serialized {key} as JSON (no label field)")
      else:
        properties[key] = str(value)

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
      add_query.append({
        "AddDescriptor": {
          "set": f"{set_name}",
          "properties": properties.copy()
        }
      })

    if not add_query:
      log.warning("addEntry: No valid vectors to add (all skipped due to dimension mismatch or uninitialized dimensions)")
      return

    response, _ = self.sendQuery(add_query, descriptor_blobs)
    if response:
      for item in response:
        if item.get('status') != 0:
          log.warning(
            f"Failed to add the descriptor to the database. Received response {item}")
    else:
      log.error(f"addEntry: No response from VDMS when adding {len(add_query)} vectors")
    return

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
    """Build TIER 1 query constraints from high-confidence metadata."""
    query_constraints = {
      "type": ["==", f"{object_type}"]
    }

    log.debug(f"[VDMS] Building constraints for object_type={object_type}, threshold={self.confidence_threshold}")
    log.debug(f"[VDMS] Input constraints: {constraints}")

    if constraints:
      for key, value in constraints.items():
        if value is None:
          log.debug(f"[VDMS] Skipping {key}: value is None")
          continue

        actual_value = value
        confidence = None

        if isinstance(value, dict) and 'label' in value:
          actual_value = value['label']
          confidence = value.get('confidence', None)
          log.debug(f"[VDMS] {key}: dict format - label={actual_value}, confidence={confidence}")
        else:
          log.debug(f"[VDMS] {key}: non-dict or no label - value={value}, type={type(value)}")

        try:
          if confidence is not None:
            conf_value = float(confidence)
            if conf_value >= self.confidence_threshold:
              query_constraints[key] = ["==", str(actual_value)]
              log.debug(f"[VDMS] ADDED: {key}={actual_value} (confidence={conf_value} >= {self.confidence_threshold})")
            else:
              log.debug(f"[VDMS] IGNORED: {key} (confidence={conf_value} < {self.confidence_threshold}, will use TIER 2)")
          else:
            log.debug(f"[VDMS] IGNORED: {key} (no confidence available, will use TIER 2)")
        except (ValueError, TypeError):
          log.debug(f"[VDMS] IGNORED: {key} (confidence not convertible to float)")
          pass

    log.debug(f"[VDMS] Final TIER 1 query_constraints: {query_constraints}")
    return query_constraints

  def findMatches(self, object_type, reid_vectors, set_name=SCHEMA_NAME,
                  k_neighbors=K_NEIGHBORS, **constraints):
    """2-Tier hybrid search: metadata filtering + vector similarity."""
    log.debug(f"[VDMS] findMatches called: object_type={object_type}, k_neighbors={k_neighbors}")
    log.debug(f"[VDMS] findMatches constraints received: {constraints}")

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

    blob = []
    normalize_embeddings = self._usesInnerProductMetric()
    for reid_vector in reid_vectors:
      vec_array = self.prepareReidVector(
        reid_vector,
        self.dimensions,
        normalize_embeddings=normalize_embeddings)
      if vec_array is None:
        continue
      blob.append(vec_array.tobytes())

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
        result.append(valid_entities)

      log.debug(
        "[VDMS] findMatches returned %d per-vector result item(s) from %d valid "
        "query vector(s); VDMS response items=%d, input vectors=%d",
        len(result), len(blob), len(response), len(reid_vectors))

      return result
    log.debug("[VDMS] findMatches returned None (no response from VDMS)")
    return None
