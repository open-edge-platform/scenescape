#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Functional tests for REST API authentication.

Covers:
  - POST /auth generates a valid token when given correct credentials
  - Token authorization grants access to protected endpoints
  - POST /auth rejects invalid passwords
  - POST /auth rejects requests with missing required fields
  - Protected endpoints reject requests without an authorization token
"""

import pytest
import requests
from http import HTTPStatus
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

_TEST_USER = "general_user"
_TEST_PASS = "general_pass"

POST_ENTITIES = [
  "/asset",
  "/auth",
  "/calibrationmarker",
  "/camera",
  "/child",
  "/region",
  "/scene",
  "/sensor",
  "/tripwire",
  "/user",
  "/calculateintrinsics",
  "/save-geospatial-snapshot",
]

GET_ENTITIES = [
  "/assets",
  "/calibrationmarkers",
  "/cameras",
  "/scenes/child",
  "/regions",
  "/scenes",
  "/sensors",
  "/tripwires",
  "/users",
]


@pytest.mark.test_name("NEX-T10481")
def test_auth_token_generation_with_valid_credentials(rest, params, result_recorder):
  """POST /auth returns HTTP 200 and a non-empty token for valid credentials."""
  result = rest.createUser({"username": _TEST_USER, "password": _TEST_PASS})
  assert result.statusCode == HTTPStatus.CREATED, \
    f"Failed to create test user: {result.errors}"

  try:
    response = requests.post(
      f"{params['resturl']}/auth",
      data={"username": _TEST_USER, "password": _TEST_PASS},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.OK, \
      f"Expected 200 OK, got {response.status_code}: {response.text}"

    body = response.json()
    assert "token" in body, \
      f"Response body missing 'token' field: {list(body.keys())}"
    assert body["token"], "Token field must not be empty"

    result_recorder.success()
  finally:
    rest.deleteUser(_TEST_USER)


@pytest.mark.test_name("NEX-T10467")
def test_auth_token_authorization_grants_access(rest, result_recorder):
  """A valid authorization token grants access to GET /scenes."""
  result = rest.getScenes(None)
  assert result.statusCode == HTTPStatus.OK, \
    f"Expected 200 OK with valid token, got {result.statusCode}: {result.errors}"

  result_recorder.success()


@pytest.mark.test_name("NEX-T23055")
def test_auth_invalid_password_is_rejected(rest, params, result_recorder):
  """POST /auth returns HTTP 400 for an incorrect password."""
  result = rest.createUser({"username": _TEST_USER, "password": _TEST_PASS})
  assert result.statusCode == HTTPStatus.CREATED, \
    f"Failed to create test user: {result.errors}"

  try:
    response = requests.post(
      f"{params['resturl']}/auth",
      data={"username": _TEST_USER, "password": "WrongPassword!"},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST, \
      f"Expected 400 Bad Request for wrong password, got {response.status_code}"

    result_recorder.success()
  finally:
    rest.deleteUser(_TEST_USER)


@pytest.mark.test_name("NEX-T23056")
def test_auth_missing_required_field_is_rejected(params, result_recorder):
  """POST /auth returns HTTP 400 when the required password field is absent."""
  response = requests.post(
    f"{params['resturl']}/auth",
    data={"username": _TEST_USER},
    verify=params["rootcert"],
  )
  assert response.status_code == HTTPStatus.BAD_REQUEST, \
    f"Expected 400 Bad Request for missing password, got {response.status_code}"

  result_recorder.success()


@pytest.mark.test_name("NEX-T23057")
def test_auth_unauthenticated_request_is_rejected(params, result_recorder):
  """Protected endpoints return HTTP 401 when no authorization token is provided."""
  failures = []

  for endpoint in GET_ENTITIES:
    response = requests.get(
      f"{params['resturl']}{endpoint}",
      verify=params["rootcert"],
    )
    if response.status_code != HTTPStatus.UNAUTHORIZED:
      failures.append(f"GET {endpoint}: expected 401, got {response.status_code}")

  for endpoint in POST_ENTITIES:
    response = requests.post(
      f"{params['resturl']}{endpoint}",
      verify=params["rootcert"],
    )
    if endpoint == "/auth":
      # username and password are required fields for /auth
      assert response.status_code == HTTPStatus.BAD_REQUEST, \
        f"Expected 400 BAD REQUEST for POST {endpoint}, got {response.status_code}: {response.text}"
    elif endpoint == "/save-geospatial-snapshot":
      # This endpoint uses SessionAuthentication (not TokenAuthentication), which
      # authenticates a cookie-less request as an anonymous user rather than
      # failing authentication outright, so IsAdminOrReadOnly denies it as a
      # permission failure (403), not an authentication failure (401).
      if response.status_code != HTTPStatus.FORBIDDEN:
        failures.append(f"POST {endpoint}: expected 403, got {response.status_code}")
    else:
      if response.status_code != HTTPStatus.UNAUTHORIZED:
        failures.append(f"POST {endpoint}: expected 401, got {response.status_code}")

  assert not failures, "Unauthenticated access checks failed:\n" + "\n".join(failures)

  result_recorder.success()
