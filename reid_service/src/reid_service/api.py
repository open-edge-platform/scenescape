# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Thin, backend-neutral service facade over the Re-ID adapter contract."""

import numpy as np

from reid_service.reid_registry import create_reid_database


class ReIDService:
  """Delegate baseline Re-ID operations to one configured adapter."""

  def __init__(self, database=None, adapter=None, connect=True, ingest=None):
    self.adapter = adapter or create_reid_database(database, dimensions=None)
    self.ingest = ingest
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
    """Return service health without changing adapter behavior."""
    connected = self._is_connected()
    return {
      "status": "ok" if connected else "degraded",
      "backend": self.adapter.__class__.__name__,
      "connected": connected,
      "ingest_enabled": self.ingest is not None,
    }

  def find_matches(self, request):
    """Run the existing adapter findMatches operation for a request mapping."""
    vectors = np.asarray(request["reid_vectors"])
    matches = self.adapter.findMatches(
      request["object_type"],
      vectors,
      set_name=request.get("set_name"),
      **request.get("constraints", {}))
    return {"matches": matches}

  def find_schema_metadata(self, request):
    """Return existing adapter schema metadata for a descriptor set."""
    return {"metadata": self.adapter.findSchemaMetadata(request.get("set_name"))}

  def purge_expired(self):
    """Trigger the existing adapter purge operation."""
    return self.adapter.purgeExpired()

  def ingest_stats(self):
    """Live-loop ingest counters, or {"enabled": False} when ingest is off."""
    if self.ingest is None:
      return {"enabled": False}
    return {"enabled": True, **self.ingest.snapshot()}
