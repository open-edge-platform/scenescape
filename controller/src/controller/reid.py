# SPDX-FileCopyrightText: (C) 2024 - 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
import json
import threading

import numpy as np

from scene_common.reid_constants import (
  RESERVED_ENTRY_KEYS,
  SCHEMA_NAME,
  SIMILARITY_METRIC,
  is_inner_product_metric,
  normalize_similarity_score,
)
from controller.reid_constraints import build_query_constraints
from controller.reid_env import (
  get_reid_confidence_threshold,
  get_reid_descriptor_ttl_secs,
)
from scene_common import log


class ReidNoValidVectorsError(ValueError):
  """Raised when addEntry has nothing valid to write (e.g. all vectors skipped).

  Hierarchy write-health must not sticky-clear on this — it is a per-batch data
  problem, not proof that the database write path is down.
  """


class ReidWriteSupersededError(RuntimeError):
  """In-flight enrollment dropped after write-epoch/health changed; do not confirm."""


class ReidPartialWriteError(RuntimeError):
  """Some vectors landed before others failed; treat as confirmed + unhealthy."""


class ReIDDatabase(ABC):
  def __init__(self, set_name=SCHEMA_NAME, similarity_metric=SIMILARITY_METRIC,
               dimensions=None, confidence_threshold=None,
               descriptor_ttl_secs=None):
    """Establish the backend-agnostic state shared by every ReID adapter.

    Subclasses must call this before using any inherited helper, since
    similarity scoring, schema lifecycle, and TIER 1 constraint building
    read these attributes.
    """
    self.set_name = set_name
    self.similarity_metric = similarity_metric
    self.dimensions = dimensions
    self.confidence_threshold = (
      get_reid_confidence_threshold() if confidence_threshold is None
      else confidence_threshold)
    self.descriptor_ttl_secs = (
      get_reid_descriptor_ttl_secs() if descriptor_ttl_secs is None
      else int(descriptor_ttl_secs))
    if self.descriptor_ttl_secs < 0:
      raise ValueError(
        f"descriptor_ttl_secs must be >= 0, got {self.descriptor_ttl_secs}")
    self.lock = threading.Lock()
    self._schema_lock = threading.Lock()
    self._schema_ready = False
    self._schema_metric = None
    return

  def _resolveSetName(self, set_name=None):
    """Resolve an optional set_name override to the adapter's configured set."""
    if set_name is None:
      return self.set_name
    return set_name

  def _usesInnerProductMetric(self, metric=None):
    """Return True when descriptor metric is Inner Product."""
    if metric is None:
      metric = self.similarity_metric
    return is_inner_product_metric(metric)

  def _normalizeSimilarityScore(self, score):
    """Return a canonical float score for the active metric, or None if invalid."""
    return normalize_similarity_score(score, self.similarity_metric)

  def _isValidSimilarityScore(self, score):
    """Validate similarity score according to active metric semantics."""
    return self._normalizeSimilarityScore(score) is not None

  def _buildQueryConstraints(self, object_type, **constraints):
    """Build TIER 1 metadata filtering constraints for this adapter."""
    return build_query_constraints(
      object_type,
      confidence_threshold=self.confidence_threshold,
      **constraints)

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

    try:
      vec_array = np.asarray(embedding_vector, dtype="float32").reshape(-1)
    except (TypeError, ValueError) as e:
      log.warning(f"prepareReidDict: Could not convert embedding to float32 array: {e}")
      return None

    inferred_dimensions = int(vec_array.shape[0])
    if inferred_dimensions <= 0:
      log.warning("prepareReidDict: Zero-length embedding vector, skipping this vector")
      return None

    expected_dimensions = inferred_dimensions if dimensions is None else int(dimensions)
    if expected_dimensions <= 0:
      log.warning(
        f"prepareReidDict: Invalid expected dimensions ({expected_dimensions}), "
        "skipping this vector")
      return None

    if inferred_dimensions != expected_dimensions:
      log.warning(
        f"prepareReidDict: Expected vector shape ({expected_dimensions},) but got "
        f"{vec_array.shape}, skipping this vector")
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

  def _prepareReidVectors(self, reid_vectors, dimensions=None):
    """Prepare valid float32 vectors for the active metric; skip invalid ones."""
    if dimensions is None:
      dimensions = self.dimensions
    normalize_embeddings = self._usesInnerProductMetric()
    prepared = []
    for reid_vector in reid_vectors:
      vec_array = self.prepareReidVector(
        reid_vector,
        dimensions,
        normalize_embeddings=normalize_embeddings)
      if vec_array is None:
        continue
      prepared.append(vec_array)
    return prepared

  def _dedupePreparedVectors(self, prepared_vectors):
    """Drop exact byte-identical prepared vectors while preserving order."""
    seen = set()
    unique = []
    for vec in prepared_vectors:
      key = vec.tobytes()
      if key in seen:
        continue
      seen.add(key)
      unique.append(vec)
    return unique

  def _prepareVectorsForAddEntry(self, reid_vectors):
    """Prepare vectors and drop exact duplicates within this add batch."""
    return self._dedupePreparedVectors(self._prepareReidVectors(reid_vectors))

  def _buildEntryProperties(self, uuid_value, rvid, object_type, persist=None, **metadata):
    """Build shared entry properties with reserved-key protection and retention."""
    properties = {
      "uuid": f"{uuid_value}",
      "rvid": f"{rvid}",
      "type": f"{object_type}",
    }
    self._applyRetentionProperties(properties)

    if persist:
      if not isinstance(persist, dict):
        raise TypeError("persist must be a dict when provided")
      persist = persist.copy()
      if "timestamp" not in persist:
        raise ValueError("persist dict requires a 'timestamp' field")
      persist_timestamp = persist.pop("timestamp")
      properties["persist"] = json.dumps(persist)
      properties["persist_timestamp"] = persist_timestamp
      log.debug(
        f"addEntry: Storing persist keys={list(persist.keys())} for uuid={uuid_value}")

    for key, value in metadata.items():
      if key in RESERVED_ENTRY_KEYS:
        log.warning(
          f"addEntry: Ignoring metadata key '{key}' because it is reserved")
        continue
      if isinstance(value, dict):
        if "label" in value:
          properties[key] = str(value["label"])
          log.debug(
            f"addEntry: Extracted label '{value['label']}' from {key} metadata dict")
        else:
          properties[key] = json.dumps(value)
          log.debug(f"addEntry: Serialized {key} as JSON (no label field)")
      else:
        properties[key] = str(value)

    return properties

  def _applyRetentionProperties(self, properties):
    """
    Attach store-native retention metadata when TTL is enabled.

    Retention is a coarse memory-bounding hint: descriptors remain matchable
    until physically purged. Adapters override this to write whatever the
    backend needs for `purgeExpired()` (for example Qdrant `expires_at` or
    VDMS `_expiration`).
    """
    return

  def retentionEnabled(self):
    """Return True when descriptors are written with a finite TTL."""
    return int(self.descriptor_ttl_secs) > 0

  def purgeExpired(self):
    """
    Physically remove descriptors whose retention window has elapsed.

    Default is a no-op. Adapters that need client-driven cleanup override this.
    Do not use this path to hide expired rows from search; reclaim only.

    @return  int | None  Number of purged entries when known, else None
    """
    return 0

  def _decodeLatestPersist(self, records, uuid_value, missing_sentinels=()):
    """
    Select and deserialize the latest persist payload from normalized records.

    Each record must be a dict with optional 'persist' and 'persist_timestamp'.
    """
    missing = set(missing_sentinels)
    records_with_persist = [
      record for record in records
      if isinstance(record, dict) and
      isinstance(record.get("persist"), str) and
      record.get("persist").strip() and
      record.get("persist") not in missing
    ]

    if not records_with_persist:
      log.debug(f"getPersistedAttributes: No persist data found for uuid={uuid_value}")
      return {}

    latest = max(
      records_with_persist,
      key=lambda record: record.get("persist_timestamp", 0))
    try:
      return json.loads(latest["persist"])
    except (json.JSONDecodeError, TypeError, KeyError) as e:
      log.warning(
        f"getPersistedAttributes: Failed to deserialize persist for "
        f"uuid={uuid_value}: {e}")
      return {}

  def _entitiesFromNormalizedScores(self, entities):
    """Filter entities to those with canonical float _distance values."""
    valid_entities = []
    for entity in entities:
      score = self._normalizeSimilarityScore(entity.get("_distance"))
      if score is None:
        log.warning(
          f"findMatches: Discarding entity with invalid similarity score "
          f"{entity.get('_distance')} for metric {self.similarity_metric}")
        continue
      normalized = dict(entity)
      normalized["_distance"] = score
      valid_entities.append(normalized)
    return valid_entities

  @abstractmethod
  def _schemaResourceLabel(self):
    """Human-readable name for this backend's schema resource (for logs/errors)."""
    return

  @abstractmethod
  def _tryCreateSchema(self, dimensions, metric):
    """
    Attempt to create the schema resource for self.set_name.

    @param   dimensions  Embedding dimensionality
    @param   metric      Backend similarity metric (e.g. 'L2', 'IP')
    @return  bool        True if the schema was newly created; False if it
                         already existed. Raise on unrecoverable failure.
    """
    return

  @abstractmethod
  def _readSchemaMarker(self):
    """
    Read the schema marker for self.set_name.

    @return  (exists, dimensions, metric)  (False, None, None) when missing.
    """
    return

  @abstractmethod
  def _persistSchemaMarker(self, dimensions, metric):
    """Write the schema marker for self.set_name (unconditional). Raise on failure."""
    return

  def _writeSchemaMarker(self, dimensions, metric, skip_exists_check=False):
    """Write schema marker, optionally skipping a prior existence probe."""
    if not skip_exists_check:
      marker_exists, _, _ = self._readSchemaMarker()
      if marker_exists:
        log.debug(
          f"_writeSchemaMarker: Marker already exists for '{self.set_name}', skipping write")
        return
    self._persistSchemaMarker(dimensions, metric)

  def _afterSchemaVerified(self):
    """Optional hook after an existing schema is verified (e.g. ensure indexes)."""
    return

  def _acceptSchema(self, requested_dimensions, expected_metric):
    """Record successful schema dimensions/metric for subsequent ready checks."""
    self.dimensions = requested_dimensions
    self._schema_metric = str(expected_metric).strip().upper()

  def ensureSchemaInner(self, requested_dimensions, expected_metric, caller):
    """
    Core attempt-first schema setup shared by connect() and ensureSchema().

    Attempt creation first; verify against the schema marker when the resource
    already exists. Backends differ only in create/marker I/O hooks.
    """
    label = self._schemaResourceLabel()
    expected_metric = str(expected_metric).strip().upper()
    created = self._tryCreateSchema(requested_dimensions, expected_metric)
    if created:
      log.info(
        f"{caller}: Created {label} '{self.set_name}' "
        f"({requested_dimensions}D, {expected_metric})")
      self._writeSchemaMarker(requested_dimensions, expected_metric, skip_exists_check=True)
      self._acceptSchema(requested_dimensions, expected_metric)
      return

    log.debug(
      f"{caller}: '{self.set_name}' already exists; "
      "verifying against schema marker.")
    marker_exists, marker_dimensions, marker_metric = self._readSchemaMarker()

    if not marker_exists:
      # Backward-compat: resource exists but marker is missing. Probe native
      # metadata once (safe here because create already indicated existence)
      # before writing a marker that other controllers will treat as authoritative.
      schema_exists, schema_dimensions, schema_metric = self.findSchemaMetadata(self.set_name)
      if not schema_exists or schema_dimensions is None or schema_metric is None:
        raise RuntimeError(
          f"{caller}: '{self.set_name}' exists but no schema marker found, and {label} "
          f"metadata could not be read for verification. Recreate the {label} to continue.")
      if str(schema_metric).strip().upper() != expected_metric:
        raise RuntimeError(
          f"{caller}: '{self.set_name}' uses metric {schema_metric}, expected {expected_metric}. "
          f"Recreate the {label} with matching metric.")
      if schema_dimensions != requested_dimensions:
        raise RuntimeError(
          f"{caller}: '{self.set_name}' has {schema_dimensions} dimensions, "
          f"expected {requested_dimensions}. "
          f"Recreate the {label} with matching dimensions.")
      log.warning(
        f"{caller}: '{self.set_name}' exists but no schema marker found; "
        "writing marker for future instances.")
      self._writeSchemaMarker(requested_dimensions, expected_metric, skip_exists_check=True)
      self._afterSchemaVerified()
      self._acceptSchema(requested_dimensions, expected_metric)
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
        f"Recreate the {label} with matching metric.")
    if marker_dimensions != requested_dimensions:
      raise RuntimeError(
        f"{caller}: '{self.set_name}' has {marker_dimensions} dimensions, "
        f"expected {requested_dimensions}. "
        f"Recreate the {label} with matching dimensions.")

    log.info(
      f"{caller}: Verified existing {label} '{self.set_name}' "
      f"against schema marker ({marker_dimensions}D, {marker_metric})")
    self._afterSchemaVerified()
    self._acceptSchema(requested_dimensions, expected_metric)

  def _initializeSchemaOnConnect(self):
    """Shared connect-time schema initialization when dimensions are known."""
    if self.dimensions is None:
      return
    with self._schema_lock:
      self.ensureSchemaInner(
        int(self.dimensions),
        str(self.similarity_metric).strip().upper(),
        "connect")
      self._schema_ready = True

  def ensureSchema(self, dimensions):
    """Ensure ReID schema exists and matches the requested dimensions/metric."""
    with self._schema_lock:
      requested_dimensions = int(dimensions)
      expected_metric = str(self.similarity_metric).strip().upper()
      if self._schema_ready:
        ready_metric = str(self._schema_metric or self.similarity_metric).strip().upper()
        if (int(self.dimensions) != requested_dimensions or
            ready_metric != expected_metric):
          label = self._schemaResourceLabel()
          raise ValueError(
            f"ReID schema already initialized with {self.dimensions}D/{ready_metric}; "
            f"incoming request is {requested_dimensions}D/{expected_metric}. "
            f"Restart the controller and flush the {label} to change schema.")
        return
      self.ensureSchemaInner(
        requested_dimensions,
        expected_metric,
        "ensureSchema")
      self._schema_ready = True

  def findSchema(self, set_name=None):
    """Return True when a schema with the given name exists."""
    schema_exists, _ = self.findSchemaDetails(self._resolveSetName(set_name))
    return schema_exists

  def findSchemaDetails(self, set_name=None):
    """Return (exists, dimensions) for the named schema."""
    schema_exists, schema_dimensions, _ = self.findSchemaMetadata(
      self._resolveSetName(set_name))
    return schema_exists, schema_dimensions

  @abstractmethod
  def findSchemaMetadata(self, set_name):
    """
    Return native schema metadata for the named set/collection.

    @param   set_name  Name of the schema resource
    @return  (exists, dimensions, metric)
    """
    return

  @abstractmethod
  def connect(self, hostname):
    """
    Connect to the database using the specified hostname

    @param   hostname  Hostname of the database
    @return  None
    """
    return

  @abstractmethod
  def addEntry(self, uuid, rvid, object_type, reid_vectors, set_name=None,
               persist=None, **metadata):
    """
    Adds entries to the database for the Re-ID vectors with optional metadata

    @param   uuid         Unique ID for the object
    @param   rvid         ID of the object from the motion tracker
    @param   object_type  Class of the object (Person, Vehicle, etc.)
    @param   reid_vectors Re-ID embeddings produced by a detection model
    @param   set_name     Optional override; defaults to self.set_name
    @param   persist      Optional dict with required 'timestamp' plus attributes
    @param   metadata     Optional semantic attributes (age, gender, color, etc.)
    @return  None
    @raises  ReidNoValidVectorsError when every input vector is skipped (callers
             should not treat this as sticky write-unhealthy)
    @raises  Exception when a database write is attempted and fails (callers /
             Future callbacks treat this as write-unhealthy for hierarchy claims)
    """
    return

  @abstractmethod
  def getPersistedAttributes(self, uuid, set_name=None):
    """
    Retrieve the most recently stored persist attributes for a given UUID.

    @param   uuid      The object UUID to look up
    @param   set_name  Optional override; defaults to self.set_name
    @return  dict      Deserialized persist attributes, or empty dict if not found
    """
    return

  @abstractmethod
  def findMatches(self, object_type, reid_vectors, set_name=None,
                  k_neighbors=None, **constraints):
    """
    Search the database for entries with the closest similarity scores.

    Returns a list with one list of entity dicts per valid query vector.
    Failed or empty searches still contribute an empty inner list so majority
    voting keeps a stable denominator.

    @param   object_type  Class of the source of the reid vector
    @param   reid_vectors Re-ID embeddings produced by a detection model
    @param   set_name     Optional override; defaults to self.set_name
    @param   k_neighbors  Number of similar entries to return
    @param   constraints  Optional metadata filters
    @return  list[list[dict]] | None
    """
    return
