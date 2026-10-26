# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Thin, backend-neutral service facade over the Re-ID adapter contract."""

import numpy as np

from scene_common.reid_constants import SCHEMA_MARKER_COLLECTION, SCHEMA_NAME, is_inner_product_metric
from reid.reid_registry import create_reid_database


class CollectionSchemaConflictError(Exception):
  """The named collection exists with a different or unverifiable schema."""


class ReIDService:
  """Delegate baseline Re-ID operations to one configured adapter."""

  def __init__(self, database=None, adapter=None, connect=True, ingest=None, collection_factory=None):
    self.adapter = adapter or create_reid_database(database, dimensions=None)
    self.adapter.raise_on_backend_error = True
    self.ingest = ingest
    self.collection_factory = collection_factory or self._new_collection_adapter
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
    vectors = validate_vectors(request["reid_vectors"], getattr(self.adapter, "dimensions", None),
                   getattr(self.adapter, "similarity_metric", "IP"))
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
    matches = self._backend_call(self.adapter.findMatches, request["object_type"], vectors,
                                 set_name=request.get("set_name"), **options, **constraints)
    return {"matches": matches}

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
