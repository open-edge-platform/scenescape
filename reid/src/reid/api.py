# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Thin, backend-neutral service facade over the Re-ID adapter contract."""

from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import threading
import time
import uuid

import numpy as np

from scene_common.reid_constants import SCHEMA_MARKER_COLLECTION, SCHEMA_NAME, is_inner_product_metric
from reid.reid_registry import create_reid_database

SCHEMA_CACHE_TTL_SECS = 30.0
SCHEMA_CACHE_MAX_SETS = 128


class CollectionSchemaConflictError(Exception):
  """The named collection exists with a different or unverifiable schema."""


class PoiNotFoundError(Exception):
  """No enrolled POI with the requested identifier exists in the collection."""


class ReIDService:
  """Delegate baseline Re-ID operations to one configured adapter."""

  def __init__(self, database=None, adapter=None, connect=True, ingest=None, collection_factory=None):
    self.adapter = adapter or create_reid_database(database, dimensions=None)
    self.adapter.raise_on_backend_error = True
    self.ingest = ingest
    self.collection_factory = collection_factory or self._new_collection_adapter
    self._schema_cache = OrderedDict()
    self._schema_lock = threading.Lock()
    if connect:
      # Adapters log and swallow connection errors; health() reports the result.
      self.adapter.connect()

  def _is_connected(self):
    # Qdrant sets adapter.connected; the VDMS client tracks it on adapter.db.
    if hasattr(self.adapter, "connected"):
      return bool(self.adapter.connected)
    db = getattr(self.adapter, "db", None)
    return bool(getattr(db, "connected", False))

  def health(self):
    """Return liveness and backend readiness using a fresh read-only probe."""
    connected = (self.adapter.backendAvailable() if hasattr(self.adapter, "backendAvailable")
                 else self._is_connected())
    return {
        "status": "ok" if connected else "degraded",
        "ready": connected,
        "backend": self.adapter.__class__.__name__,
        "connected": connected,
        "ingest_enabled": self.ingest is not None,
    }

  def find_matches(self, request):
    """Run the existing adapter findMatches operation for a request mapping."""
    validate_request(request, {"object_type", "reid_vectors", "set_name", "constraints", "k_neighbors"},
                     required=("reid_vectors", "object_type"))
    validate_name(request["object_type"], "object_type")
    validate_name(request.get("set_name"), "set_name", optional=True)
    set_name = request.get("set_name") or self.adapter.set_name
    dimensions = (self.adapter.dimensions if set_name == self.adapter.set_name else None)
    metric = getattr(self.adapter, "similarity_metric", "IP")
    vectors = validate_vectors(request["reid_vectors"], dimensions, metric)
    constraints = request.get("constraints", {})
    reserved = {"set_name", "k_neighbors", "object_type", "reid_vectors", "operation", "confidence_threshold"}
    if not isinstance(constraints, dict) or reserved & constraints.keys():
      raise ValueError("constraints must be an object of metadata filters")
    options = {}
    if "k_neighbors" in request:
      neighbors = request["k_neighbors"]
      if (isinstance(neighbors, bool) or not isinstance(neighbors, (int, float))
              or not 1 <= neighbors <= 1000 or int(neighbors) != neighbors):
        raise ValueError("k_neighbors must be an integer from 1 to 1000")
      options["k_neighbors"] = int(neighbors)
    dimensions = self._queryDimensions(set_name)
    if dimensions is None:
      return {"matches": [[] for _ in vectors]}
    vectors = validate_vectors(vectors, dimensions, metric)
    matches = self._backend_call(self.adapter.findMatches, request["object_type"], vectors,
                                 set_name=request.get("set_name"), **options, **constraints)
    return {"matches": matches}

  def _queryDimensions(self, set_name):
    """Cache existing schema widths; never cache absence or backend failures."""
    with self._schema_lock:
      now = time.monotonic()
      cached = self._schema_cache.get(set_name)
      if cached is not None and now - cached[0] < SCHEMA_CACHE_TTL_SECS:
        return cached[1]
      self._schema_cache.pop(set_name, None)
      exists, dimensions, _ = self._backend_call(self.adapter.findSchemaMetadata, set_name)
      if not exists:
        return None
      if type(dimensions) is not int or dimensions <= 0:
        raise ConnectionError("ReID backend schema dimensions unavailable")
      self._schema_cache[set_name] = (now, dimensions)
      if len(self._schema_cache) > SCHEMA_CACHE_MAX_SETS:
        self._schema_cache.popitem(last=False)
      return dimensions

  def find_schema_metadata(self, request):
    """Return existing adapter schema metadata for a descriptor set."""
    validate_request(request, {"set_name"})
    validate_name(request.get("set_name"), "set_name", optional=True)
    set_name = request.get("set_name") or self.adapter.set_name
    return {"metadata": self._backend_call(self.adapter.findSchemaMetadata, set_name)}

  def _new_collection_adapter(self, collection_name, metric):
    """Create an independently configured adapter for a non-live collection."""
    adapter = type(self.adapter)(
      set_name=collection_name,
      similarity_metric=metric,
      dimensions=None,
      descriptor_ttl_secs=0,
    )
    adapter.raise_on_backend_error = True
    adapter.connect()
    return adapter

  def create_collection(self, request):
    """Create or verify an explicitly named POI collection schema."""
    collection_name, dimensions, metric = self._validate_collection_declaration(request)
    adapter = self.collection_factory(collection_name, metric)
    adapter.raise_on_backend_error = True
    if not adapter.backendAvailable():
      raise ConnectionError("ReID backend unavailable")
    try:
      exists, current_dimensions, current_metric = adapter.findSchemaMetadata(collection_name)
      if exists and (current_dimensions != dimensions or
                     str(current_metric).strip().upper() != metric):
        raise CollectionSchemaConflictError(
          f"Collection '{collection_name}' already has an incompatible schema")
      adapter.ensureSchema(dimensions)
    except CollectionSchemaConflictError:
      raise
    except RuntimeError as error:
      raise CollectionSchemaConflictError(
        f"Collection '{collection_name}' schema could not be verified") from error
    except Exception as error:
      raise ConnectionError("ReID backend operation failed") from error
    return {
      "collection_name": collection_name,
      "dimensions": dimensions,
      "metric": metric,
      "created": not exists,
    }

  def enroll_poi(self, request):
    """Enroll precomputed POI vectors with required attribution and an audit record."""
    validate_request(request, {"collection_name", "object_type", "reid_vectors",
                               "severity", "notes", "enrolled_by"},
                     required=("collection_name", "object_type", "reid_vectors",
                               "severity", "notes", "enrolled_by"))
    collection_name, adapter, dimensions, metric = self._poi_collection(
      request["collection_name"])
    object_type = validate_name(request["object_type"], "object_type")
    enrolled_by = validate_name(request["enrolled_by"], "enrolled_by")
    severity = validate_name(request["severity"], "severity")
    notes = validate_text(request["notes"], "notes", 2048)
    vectors = validate_poi_vectors(request["reid_vectors"], dimensions, metric)
    poi_id = str(uuid.uuid4())
    audit = self._poi_audit("enroll", enrolled_by, vectors)
    self._write_poi_vectors(adapter, poi_id, object_type, vectors, collection_name,
                            severity, notes, audit)
    return {"poi_id": poi_id, "collection_name": collection_name,
            "vector_count": len(vectors)}

  def append_poi_embeddings(self, request):
    """Append reference vectors to an enrolled POI without changing its prior audit."""
    validate_request(request, {"collection_name", "poi_id", "reid_vectors", "enrolled_by"},
                     required=("collection_name", "poi_id", "reid_vectors", "enrolled_by"))
    collection_name, adapter, dimensions, metric = self._poi_collection(
      request["collection_name"])
    poi_id = validate_name(request["poi_id"], "poi_id")
    enrolled_by = validate_name(request["enrolled_by"], "enrolled_by")
    vectors = validate_poi_vectors(request["reid_vectors"], dimensions, metric)
    profile = self._backend_call(adapter.getPersistedAttributes, poi_id, set_name=collection_name)
    if not profile or profile.get("poi_id") != poi_id:
      raise PoiNotFoundError(f"POI '{poi_id}' was not found in collection '{collection_name}'")
    severity = validate_name(profile.get("severity"), "stored severity")
    notes = validate_text(profile.get("notes", ""), "stored notes", 2048)
    object_type = validate_name(profile.get("object_type"), "stored object_type")
    audit = self._poi_audit("append_embeddings", enrolled_by, vectors)
    self._write_poi_vectors(adapter, poi_id, object_type, vectors, collection_name,
                            severity, notes, audit, profile=profile)
    return {"poi_id": poi_id, "collection_name": collection_name,
            "vector_count": len(vectors)}

  def _poi_collection(self, collection_name):
    validate_name(collection_name, "collection_name")
    if collection_name != collection_name.strip():
      raise ValueError("collection_name cannot contain surrounding whitespace")
    reserved = {str(self.adapter.set_name).casefold(), SCHEMA_NAME.casefold(),
                SCHEMA_MARKER_COLLECTION.casefold()}
    if collection_name.casefold() in reserved:
      raise ValueError("POI writes cannot target the live gallery or internal schema collection")
    adapter = self.collection_factory(collection_name, self.adapter.similarity_metric)
    adapter.raise_on_backend_error = True
    if not adapter.backendAvailable():
      raise ConnectionError("ReID backend unavailable")
    exists, dimensions, metric = self._backend_call(adapter.findSchemaMetadata, collection_name)
    if not exists or dimensions is None or metric is None:
      raise CollectionSchemaConflictError(
        f"POI collection '{collection_name}' must be declared before enrollment")
    return collection_name, adapter, int(dimensions), str(metric).strip().upper()

  @staticmethod
  def _poi_audit(action, enrolled_by, vectors):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
      "action": action,
      "audit_id": str(uuid.uuid4()),
      "enrolled_by": enrolled_by,
      "timestamp": timestamp,
      "vector_sha256": [hashlib.sha256(vector.tobytes()).hexdigest() for vector in vectors],
    }

  @staticmethod
  def _write_poi_vectors(adapter, poi_id, object_type, vectors, collection_name,
                         severity, notes, audit, profile=None):
    persist = {
      "timestamp": time.time(),
      "poi_id": poi_id,
      "object_type": object_type,
      "severity": severity,
      "notes": notes,
      "active": True if profile is None else profile.get("active", True),
    }
    try:
      adapter.addEntry(
        poi_id, None, object_type, vectors, set_name=collection_name, persist=persist,
        severity=severity, notes=notes, poi_enrollment_audit=audit)
    except Exception as error:
      raise ConnectionError("ReID backend operation failed to persist all POI vectors") from error

  def _validate_collection_declaration(self, request):
    """Validate and normalize a POI schema declaration without backend access."""
    validate_request(request, {"collection_name", "dimensions", "metric"},
                     required=("collection_name", "dimensions", "metric"))
    collection_name = request["collection_name"]
    validate_name(collection_name, "collection_name")
    if collection_name != collection_name.strip():
      raise ValueError("collection_name cannot contain surrounding whitespace")
    reserved_names = {
      str(self.adapter.set_name).casefold(), SCHEMA_NAME.casefold(),
      SCHEMA_MARKER_COLLECTION.casefold(),
    }
    if collection_name.casefold() in reserved_names:
      raise ValueError("The live gallery and internal schema collections cannot be declared here")

    dimensions = request["dimensions"]
    if (isinstance(dimensions, bool) or not isinstance(dimensions, (int, float)) or
      not np.isfinite(dimensions) or not 1 <= dimensions <= 4096 or int(dimensions) != dimensions):
      raise ValueError("dimensions must be an integer from 1 to 4096")
    dimensions = int(dimensions)
    metric = request["metric"]
    if not isinstance(metric, str) or metric.strip().upper() not in {"IP", "L2"}:
      raise ValueError("metric must be IP or L2")
    metric = metric.strip().upper()
    return collection_name, dimensions, metric

  def purge_expired(self):
    """Trigger the existing adapter purge operation."""
    return self._backend_call(self.adapter.purgeExpired)

  @staticmethod
  def _backend_call(operation, *args, **kwargs):
    try:
      return operation(*args, **kwargs)
    except Exception as error:
      raise ConnectionError("ReID backend operation failed") from error

  def ingest_stats(self):
    """Live-loop ingest counters, or {"enabled": False} when ingest is off."""
    if self.ingest is None:
      return {"enabled": False}
    return {"enabled": True, **self.ingest.snapshot()}


def validate_request(request, allowed, required=()):
  """Reject unknown fields rather than silently ignoring misspelled options."""
  if not isinstance(request, dict) or request.keys() - allowed:
    raise ValueError("Request contains unsupported fields")
  for field in required:
    if field not in request:
      raise KeyError(field)


def validate_name(value, field, optional=False):
  """Validate bounded nonempty class and descriptor-set names."""
  if optional and value is None:
    return
  if not isinstance(value, str) or not value.strip() or len(value) > 256 or "\0" in value:
    raise ValueError(f"{field} must be a nonempty string of at most 256 characters")
  return value


def validate_vectors(value, dimensions, metric):
  """Require a bounded finite float32 batch respecting metric normalization."""
  raw = np.asarray(value)
  if raw.dtype.kind not in "iuf" or raw.ndim != 2:
    raise ValueError("reid_vectors must be a rectangular numeric matrix")
  if not 1 <= raw.shape[0] <= 1024 or not 1 <= raw.shape[1] <= 4096:
    raise ValueError("reid_vectors supports 1-1024 rows and 1-4096 dimensions")
  if dimensions is not None and raw.shape[1] != dimensions:
    raise ValueError("reid_vectors dimensions do not match the configured model")
  with np.errstate(over="ignore", invalid="ignore"):
    vectors = raw.astype(np.float32)
  if not np.isfinite(vectors).all():
    raise ValueError("reid_vectors must contain finite float32 vectors")
  if is_inner_product_metric(metric) and not np.any(vectors != 0, axis=1).all():
    raise ValueError("inner-product reid_vectors must be nonzero")
  return vectors


def validate_poi_vectors(value, dimensions, metric):
  """Validate the bounded 1-5 reference-vector batch allowed for a POI write."""
  vectors = validate_vectors(value, dimensions, metric)
  if not 1 <= vectors.shape[0] <= 5:
    raise ValueError("POI writes require 1 to 5 embedding vectors")
  return vectors


def validate_text(value, field, maximum_length):
  """Validate bounded human-entered POI text, allowing empty notes only."""
  if (not isinstance(value, str) or len(value) > maximum_length or "\0" in value or
      (field != "notes" and not value.strip())):
    raise ValueError(f"{field} must be a string of at most {maximum_length} characters")
  return value
