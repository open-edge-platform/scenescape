# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import socket
import time

import vdms

from reid.reid import ReIDDatabase, ReidNoValidVectorsError, ReidPartialWriteError
from scene_common.reid_constants import (
  K_NEIGHBORS,
  SCHEMA_NAME,
  SIMILARITY_METRIC,
  VDMS_EXPIRATION_KEY,
)
from reid.reid_env import (
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
RECONNECT_INTERVAL_SECS = 5.0
BACKEND_TIMEOUT_SECS = 5.0

class VDMSDatabase(ReIDDatabase):
  def __init__(self, set_name=SCHEMA_NAME,
               similarity_metric=SIMILARITY_METRIC, dimensions=None,
               confidence_threshold=None,
               ca_cert=None, client_cert=None,
               client_key=None, use_tls=None,
               descriptor_ttl_secs=None):
    super().__init__(
      set_name=set_name,
      similarity_metric=similarity_metric,
      dimensions=dimensions,
      confidence_threshold=confidence_threshold,
      descriptor_ttl_secs=descriptor_ttl_secs)
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
    self._last_connect_attempt = float("-inf")
    return

  def _schemaResourceLabel(self):
    return "VDMS descriptor set"

  def backendAvailable(self):
    """Probe read-only, reconnecting at most once per retry interval."""
    if self._probeBackend():
      return True
    with self.lock:
      if not self._reconnectClient():
        return False
    return self._probeBackend()

  def _reconnectClient(self):
    """Reconnect under self.lock, sharing the retry budget with normal queries."""
    now = time.monotonic()
    if now - self._last_connect_attempt < RECONNECT_INTERVAL_SECS:
      return False
    self._last_connect_attempt = now
    try:
      self.db.disconnect()
      self._connectClient(self.hostname)
    except (OSError, RuntimeError) as error:
      log.warning(f"VDMS reconnect failed: {error}")
      return False
    return True

  def _connectClient(self, hostname):
    try:
      self.db.connect(hostname, port=self.port)
      self.db.conn.settimeout(BACKEND_TIMEOUT_SECS)
    except Exception:
      self.db.disconnect()
      raise

  def _probeBackend(self):
    try:
      response, _ = self.sendQuery([{"FindEntity": {"class": SCHEMA_MARKER_CLASS,
                                                  "results": {"list": ["set_name"]}}}])
      return bool(response and response[0].get("status") == 0)
    except Exception as error:
      log.warning(f"VDMS readiness probe failed: {error}")
      return False

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
    with self.lock:
      if not self.db.connected and not self._reconnectClient():
        log.warning("Cannot send query to VDMS: reconnect unavailable")
        self._backendFailure()
        return [], []
      try:
        if blob:
          query_response = self.db.query(query, blob)
        else:
          query_response = self.db.query(query)
      except Exception:
        # A late or partial reply must never be consumed by the next query.
        self.db.disconnect()
        log.warning("VDMS query raised; disconnected to discard pending replies")
        raise
      if not query_response or query_response == "NOT CONNECTED":
        self.db.disconnect()
        log.warning("Failed to receive a complete VDMS query response")
        self._backendFailure()
        return [], []
    return self._parseQueryResponses(query, query_response[0]), query_response[1]

  def _parseQueryResponses(self, query, raw_responses):
    if len(raw_responses) == 1 and 'FailedCommand' in raw_responses[0]:
      return self._transactionResponses(query, raw_responses[0])
    if len(raw_responses) != len(query):
      self._backendFailure()
      return []
    responses = [response.get(next(iter(command)), {})
                 for command, response in zip(query, raw_responses)]
    responses = [item if isinstance(item, dict) else {} for item in responses]
    self._validateQueryResponses(query, responses)
    return responses

  def _transactionResponses(self, query, failure):
    if (query and all(item == failure["FailedCommand"] for item in query)
        and self._isEmptyLookup(query[0], failure)):
      return [failure.copy() for _ in query]
    log.warning(f"VDMS transaction failed: {failure}")
    self._backendFailure()
    return []

  def _validateQueryResponses(self, query, responses):
    """Distinguish documented empty lookups from failed transactions."""
    if len(responses) != len(query):
      self._backendFailure()
      return
    if any(item.get("status") != 0 and next(iter(command)) != "AddDescriptorSet"
           and not self._isEmptyLookup(command, item)
           for command, item in zip(query, responses)):
      self._backendFailure()

  @staticmethod
  def _isEmptyLookup(command, response):
    name = next(iter(command))
    absent = {
      "FindDescriptor": {
        "DescriptorSet Not Found!", "Set Not Found", "Not Found!",
        "Descriptors Not Found", "Descriptor Not Found in graph!",
      },
      "FindDescriptorSet": {"DescriptorSet Not Found!", "Set Not Found"},
    }
    return response.get("status") == -1 and response.get("info") in absent.get(name, set())

  def connect(self, hostname=None):
    if hostname is None:
      hostname = self.hostname
    self.hostname = hostname
    self._last_connect_attempt = time.monotonic()
    try:
      with self.lock:
        self._connectClient(hostname)
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

  def _readSchemaMarker(self, set_name=None):
    """
    Read the schema marker entity for this descriptor set to verify
    dimensions/metric reliably, bypassing FindDescriptorSet.

    @return  (exists, dimensions, metric) tuple. (False, None, None) if not found.
    """
    query = [{
      "FindEntity": {
        "class": SCHEMA_MARKER_CLASS,
        "constraints": {"set_name": ["==", self._resolveSetName(set_name)]},
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
    for vec_array in self._prepareVectorsForAddEntry(reid_vectors):
      descriptor_blobs.append(vec_array.tobytes())
      add_query.append({
        "AddDescriptor": {
          "set": f"{set_name}",
          "properties": properties.copy()
        }
      })

    if not add_query:
      raise ReidNoValidVectorsError(
        "addEntry: No valid vectors to add (all skipped due to dimension mismatch "
        "or uninitialized dimensions)")

    response, _ = self.sendQuery(add_query, descriptor_blobs)
    if not response:
      raise RuntimeError(
        f"addEntry: No response from VDMS when adding {len(add_query)} vectors")
    failures = [item for item in response if item.get('status') != 0]
    if failures:
      successes = len(response) - len(failures)
      detail = (
        f"addEntry: Failed to add {len(failures)}/{len(response)} descriptor(s) "
        f"to VDMS. First failure: {failures[0]}")
      if successes > 0:
        raise ReidPartialWriteError(detail)
      raise RuntimeError(detail)
    return

  def _applyRetentionProperties(self, properties):
    """
    Stamp VDMS-native _expiration as a TTL duration in seconds.

    VDMS computes expiry as (server insert time) + (_expiration duration).
    Pass the TTL duration itself — never an absolute timestamp.
    """
    if not self.retentionEnabled():
      return
    properties[VDMS_EXPIRATION_KEY] = int(self.descriptor_ttl_secs)
    return

  def purgeExpired(self):
    """
    Ask VDMS to delete descriptors whose native expiration timestamp is past.

    Invoked by the shared controller purge timer (REID_PURGE_INTERVAL_SECS).
    Descriptors remain matchable until this reclaim runs.
    """
    if not self.retentionEnabled():
      return 0
    response, _ = self.sendQuery([{"DeleteExpired": {}}])
    if not response:
      log.warning("purgeExpired: No response from VDMS for DeleteExpired")
      return None
    if response[0].get('status') != 0:
      log.warning(
        f"purgeExpired: DeleteExpired failed. Response: {response[0]}")
      return None
    deleted = response[0].get('deleted', response[0].get('returned'))
    log.debug(f"purgeExpired: VDMS DeleteExpired completed deleted={deleted}")
    return deleted if deleted is not None else 0

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
    # FindDescriptorSet raises an internal JSON error for absent sets in VDMS 2.12.
    query = [{
      "FindEntity": {
        "class": "VD:DESCSET",
        "constraints": {"VD:name": ["==", set_name]},
        "results": {"list": ["VD:name", "VD:dimensions"]}
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
    if schema_metric is None:
      marker_exists, _, schema_metric = self._readSchemaMarker(set_name)
      if not marker_exists:
        schema_metric = None
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
      for key in ['dimensions', 'dimension', 'VD:dimensions', 'VD:dimension']:
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
      for key in ['metric', 'distance_metric', 'similarity_metric',
                  'VD:metric', 'VD:distance_metric', 'VD:similarity_metric']:
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
