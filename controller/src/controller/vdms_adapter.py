# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import socket

import vdms

from controller.reid import ReIDDatabase
from controller.reid_constants import (
  K_NEIGHBORS,
  SCHEMA_NAME,
  SIMILARITY_METRIC,
)
from controller.reid_env import (
  get_reid_ca_cert,
  get_reid_client_cert,
  get_reid_client_key,
  get_reid_hostname,
  get_reid_port,
  get_reid_use_tls,
)
from scene_common import log

# Retained for tests/tools that historically imported this module constant.
DIMENSIONS = 256
SCHEMA_MARKER_CLASS = "ReidSchemaMarker"

class VDMSDatabase(ReIDDatabase):
  def __init__(self, set_name=SCHEMA_NAME,
               similarity_metric=SIMILARITY_METRIC, dimensions=None,
               confidence_threshold=None,
               ca_cert=None, client_cert=None,
               client_key=None, use_tls=None):
    super().__init__(
      set_name=set_name,
      similarity_metric=similarity_metric,
      dimensions=dimensions,
      confidence_threshold=confidence_threshold)
    resolved_ca_cert = get_reid_ca_cert() if ca_cert is None else ca_cert
    resolved_client_cert = (
      get_reid_client_cert() if client_cert is None else client_cert)
    resolved_client_key = get_reid_client_key() if client_key is None else client_key
    resolved_use_tls = get_reid_use_tls() if use_tls is None else use_tls
    self.db = vdms.vdms(
      use_tls=resolved_use_tls,
      ca_cert_file=resolved_ca_cert,
      client_cert_file=resolved_client_cert,
      client_key_file=resolved_client_key
    )
    self.hostname = get_reid_hostname()
    self.port = get_reid_port()
    return

  def _schemaResourceLabel(self):
    return "VDMS descriptor set"

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

  def connect(self, hostname=None):
    if hostname is None:
      hostname = self.hostname
    try:
      self.db.connect(hostname, port=self.port)
      self._initializeSchemaOnConnect()
    except RuntimeError as e:
      log.error(f"Failed to initialize VDMS schema: {e}")
    except socket.error as e:
      log.warning(f"Failed to connect to VDMS container: {e}")
    return

  def _tryCreateSchema(self, dimensions, metric):
    """
    Attempt AddDescriptorSet first (avoids FindDescriptorSet on a missing set,
    which triggers a VDMS v2.12 bug). Return True on create, False if the set
    already appears to exist.
    """
    response, _ = self.sendQuery([{
      "AddDescriptorSet": {
        "name": self.set_name,
        "metric": metric,
        "dimensions": dimensions
      }
    }])

    if not response:
      raise RuntimeError(
        f"No response from VDMS for descriptor set '{self.set_name}'.")

    if response[0].get('status') == 0:
      return True

    log.debug(
      f"_tryCreateSchema: AddDescriptorSet status={response[0].get('status')}; "
      "set may already exist.")
    return False

  def _persistSchemaMarker(self, dimensions, metric):
    """
    Record dimensions/metric as a VDMS entity. Sidesteps FindDescriptorSet's
    unreliable metadata response (VDMS v2.12). A race between instances is
    harmless since both would write the same configured values.
    """
    query = [{"AddEntity": {"class": SCHEMA_MARKER_CLASS,
              "properties": {
                "set_name": self.set_name,
                "dimensions": dimensions,
                "metric": metric}}}]
    response, _ = self.sendQuery(query)
    if not response or response[0].get('status') != 0:
      raise RuntimeError(
        f"Failed to write schema marker for '{self.set_name}'. Response: {response}")

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

  def addEntry(self, uuid, rvid, object_type, reid_vectors, set_name=None,
               persist=None, **metadata):
    """
    Add entries to database with visual embeddings and optional semantic metadata.
    """
    set_name = self._resolveSetName(set_name)
    properties = self._buildEntryProperties(
      uuid, rvid, object_type, persist=persist, **metadata)

    # VDMS API expects: query([q1, q2, ...], [blob1, blob2, ...])
    descriptor_blobs = []
    add_query = []
    for vec_array in self._prepareReidVectors(reid_vectors):
      descriptor_blobs.append(vec_array.tobytes())
      add_query.append({
        "AddDescriptor": {
          "set": f"{set_name}",
          "properties": properties.copy()
        }
      })

    if not add_query:
      log.warning(
        "addEntry: No valid vectors to add (all skipped due to dimension mismatch "
        "or uninitialized dimensions)")
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

  def getPersistedAttributes(self, uuid, set_name=None):
    """
    Retrieve the most recent persist attributes stored for a given object UUID.
    """
    set_name = self._resolveSetName(set_name)
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

    return self._decodeLatestPersist(
      entities,
      uuid,
      missing_sentinels=("Missing property",))

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
    if (not first_response or first_response.get('status') != 0 or
        first_response.get('returned', 0) <= 0):
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
              f"findSchemaDetails: Could not parse descriptor dimensions from key "
              f"'{key}' value '{payload[key]}'")
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

  def findMatches(self, object_type, reid_vectors, set_name=None,
                   k_neighbors=K_NEIGHBORS, **constraints):
    """
    2-Tier Hybrid Search: TIER 1 (metadata filtering) + TIER 2 (vector similarity)

    Returns one result list per valid query vector (empty list when no usable match).
    """
    set_name = self._resolveSetName(set_name)
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

    blob = [vec.tobytes() for vec in self._prepareReidVectors(reid_vectors)]
    if not blob:
      log.warning("findMatches: No valid vectors for similarity search")
      return None

    query = [find_query] * len(blob)
    response, _ = self.sendQuery(query, blob)

    log.debug(
      f"[VDMS] Raw VDMS response (truncated): "
      f"status={response[0].get('status') if response else 'None'}, "
      f"returned={response[0].get('returned') if response else 'None'}")
    if response and len(response) > 0:
      log.debug(f"[VDMS] Full first response: {response[0]}")

    result = []
    for item in (response or []):
      if item.get('status') != 0 or item.get('returned', 0) <= 0:
        result.append([])
        continue
      result.append(self._entitiesFromNormalizedScores(item.get('entities', [])))

    while len(result) < len(blob):
      result.append([])

    log.debug(
      "[VDMS] findMatches returned %d per-vector result item(s) from %d valid "
      "query vector(s); VDMS response items=%d, input vectors=%d",
      len(result), len(blob), len(response or []), len(reid_vectors))
    return result
