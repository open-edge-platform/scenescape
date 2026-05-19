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

import requests
from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result

_TEST_USER = "general_user"
_TEST_PASS = "general_pass"

def test_auth_token_generation_with_valid_credentials(params, record_xml_attribute):
  """Verify that POST /auth returns HTTP 200 and a non-empty token when
  called with valid credentials."""
  TEST_NAME = "NEX-T10481"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), \
    "Admin authentication failed"

  try:
    result = rest.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create test user: {result.errors}"
    user_created = True

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

    exit_code = 0
  finally:
    if user_created:
      rest.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)


def test_auth_token_authorization_grants_access(params, record_xml_attribute):
  """Verify that a valid authorization token grants access to a protected
  endpoint (GET /scenes returns HTTP 200)."""
  TEST_NAME = "NEX-T10467"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), \
    "Admin authentication failed"

  try:
    result = rest.getScenes(None)
    assert result.statusCode == HTTPStatus.OK, \
      f"Expected 200 OK with valid token, got {result.statusCode}: {result.errors}"

    exit_code = 0
  finally:
    record_test_result(TEST_NAME, exit_code)


def test_auth_invalid_password_is_rejected(params, record_xml_attribute):
  """Verify that POST /auth returns HTTP 400 when given an incorrect password."""
  TEST_NAME = "NEX-T23055"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), \
    "Admin authentication failed"

  try:
    result = rest.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create test user: {result.errors}"
    user_created = True

    response = requests.post(
      f"{params['resturl']}/auth",
      data={"username": _TEST_USER, "password": "WrongPassword!"},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST, \
      f"Expected 400 Bad Request for wrong password, got {response.status_code}"

    exit_code = 0
  finally:
    if user_created:
      rest.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)


def test_auth_missing_required_field_is_rejected(params, record_xml_attribute):
  """Verify that POST /auth returns HTTP 400 when the required password field
  is absent from the request body."""
  TEST_NAME = "NEX-T23056"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), \
    "Admin authentication failed"

  try:
    response = requests.post(
      f"{params['resturl']}/auth",
      data={"username": _TEST_USER},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST, \
      f"Expected 400 Bad Request for missing password, got {response.status_code}"

    exit_code = 0
  finally:
    record_test_result(TEST_NAME, exit_code)


def test_auth_unauthenticated_request_is_rejected(params, record_xml_attribute):
  """Verify that a protected endpoint (GET /scenes) returns HTTP 401 when no
  authorization token is provided."""
  TEST_NAME = "NEX-T23057"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1

  try:
    response = requests.post(
      f"{params['resturl']}/save-geospatial-snapshot",
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.UNAUTHORIZED, \
      f"Expected 401 Unauthorized with no token, got {response.status_code}"

    exit_code = 0
  finally:
    record_test_result(TEST_NAME, exit_code)
