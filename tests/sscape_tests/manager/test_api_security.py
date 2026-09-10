# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import Mock, patch

import pytest
from rest_framework.test import APIRequestFactory

from manager import api


TEST_NAME = "NEX-T00000"


@pytest.mark.parametrize(
  ("remote_addr", "expected"),
  [
    ("127.0.0.1", True),
    ("::1", True),
    ("192.0.2.1", False),
    ("not-an-ip", False),
    (None, False),
  ],
)
def test_is_loopback_request(remote_addr, expected):
  request = APIRequestFactory().get(
    "/api/v1/health",
    **({"REMOTE_ADDR": remote_addr} if remote_addr else {}),
  )
  # handle the case where REMOTE_ADDR is not set in request.META
  if not remote_addr:
    request.META.pop("REMOTE_ADDR", None)

  assert api.is_loopback_request(request) is expected


@pytest.mark.parametrize("view_class", [api.ServiceHealth, api.DatabaseReady])
def test_internal_endpoints_reject_non_loopback_requests(view_class):
  request = APIRequestFactory().get(
    "/api/v1/health",
    REMOTE_ADDR="192.0.2.1",
  )

  with patch.object(view_class, "checkDatabase") as check_database:
    response = view_class.as_view()(request)

  assert response.status_code == 403
  check_database.assert_not_called()


def test_database_ready_allows_loopback_request():
  request = APIRequestFactory().get(
    "/api/v1/database-ready",
    REMOTE_ADDR="127.0.0.1",
  )
  database_status = Mock(is_ready=True)

  with patch.object(api.DatabaseReady, "checkDatabase", return_value=True), \
       patch.object(api.DatabaseStatus.objects, "first", return_value=database_status), \
       patch.object(api.User.objects, "count", return_value=1):
    response = api.DatabaseReady.as_view()(request)

  assert response.status_code == 200
  assert response.data == {"databaseReady": True}


def test_service_health_allows_loopback_request():
  request = APIRequestFactory().get(
    "/api/v1/health",
    REMOTE_ADDR="127.0.0.1",
  )
  database_status = Mock(is_ready=True)

  with patch.object(api.ServiceHealth, "checkDatabase", return_value=True), \
       patch.object(api.DatabaseStatus.objects, "first", return_value=database_status), \
       patch.object(api.User.objects, "count", return_value=1):
    response = api.ServiceHealth.as_view()(request)

  assert response.status_code == 200
  assert response.data["status"] == "healthy"
