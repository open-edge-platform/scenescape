# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the standalone Re-ID service facade."""

from reid_service.api import ReIDService

TEST_NAME = "NEX-T00000"


class FakeAdapter:
  """Capture facade calls without requiring a vector database."""

  def findMatches(self, object_type, vectors, set_name=None, **constraints):
    return [{"object_type": object_type, "count": len(vectors),
             "set_name": set_name, "constraints": constraints}]

  def findSchemaMetadata(self, set_name):
    return True, 256, "IP"

  def purgeExpired(self):
    return 2


def test_facade_delegates_baseline_operations():
  service = ReIDService(adapter=FakeAdapter())

  assert service.health()["status"] == "ok"
  assert service.find_matches({
    "object_type": "person",
    "reid_vectors": [[0.1, 0.2]],
    "set_name": "gallery",
    "constraints": {"camera_id": "cam1"},
  })["matches"][0]["count"] == 1
  assert service.find_schema_metadata({"set_name": "gallery"})["metadata"] == (
    True, 256, "IP")
  assert service.purge_expired() == 2


def test_facade_rejects_missing_query_fields():
  service = ReIDService(adapter=FakeAdapter())

  try:
    service.find_matches({"object_type": "person"})
  except KeyError as error:
    assert error.args == ("reid_vectors",)
  else:
    raise AssertionError("missing vectors should be rejected")
