# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Thin, backend-neutral service facade over the Re-ID adapter contract."""

import numpy as np

from reid_service.reid_registry import create_reid_database


class ReIDService:
  """Delegate baseline Re-ID operations to one configured adapter."""

  def __init__(self, database=None, adapter=None):
    self.adapter = adapter or create_reid_database(database, dimensions=None)

  def health(self):
    """Return service health without changing adapter behavior."""
    return {"status": "ok", "backend": self.adapter.__class__.__name__}

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
