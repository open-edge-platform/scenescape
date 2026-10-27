# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the standalone Re-ID service facade."""

from unittest import mock

import pytest

from reid.api import ReIDService

TEST_NAME = "NEX-T00000"


class FakeAdapter:
  """Capture facade calls without requiring a vector database."""

  def __init__(self):
    self.connected = False

  def connect(self, hostname=None):
    self.connected = True

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
  result = service.find_matches({
    "object_type": "person",
    "reid_vectors": [[0.1, 0.2]],
    "set_name": "gallery",
    "constraints": {"camera_id": "cam1"},
  })["matches"][0]
  assert result == {"object_type": "person", "count": 1,
                    "set_name": "gallery", "constraints": {"camera_id": "cam1"}}
  assert service.find_schema_metadata({"set_name": "gallery"})["metadata"] == (
    True, 256, "IP")
  assert service.purge_expired() == 2


def test_facade_rejects_missing_query_fields():
  service = ReIDService(adapter=FakeAdapter())

  with pytest.raises(KeyError, match="reid_vectors"):
    service.find_matches({"object_type": "person"})


def test_connect_called_on_init():
  adapter = mock.Mock()
  ReIDService(adapter=adapter)
  adapter.connect.assert_called_once_with()


def test_connect_can_be_skipped():
  adapter = mock.Mock()
  ReIDService(adapter=adapter, connect=False)
  adapter.connect.assert_not_called()


def test_health_reports_disconnected():
  adapter = mock.Mock(spec=["connect", "connected"])
  adapter.connected = False
  health = ReIDService(adapter=adapter).health()
  assert health["status"] == "degraded"
  assert health["connected"] is False


def test_health_reports_connected():
  adapter = mock.Mock(spec=["connect", "connected"])
  adapter.connected = True
  health = ReIDService(adapter=adapter).health()
  assert health["status"] == "ok"
  assert health["connected"] is True


def test_health_uses_vdms_client_state():
  adapter = mock.Mock(spec=["connect", "db"])
  adapter.db.connected = True
  assert ReIDService(adapter=adapter).health()["connected"] is True
