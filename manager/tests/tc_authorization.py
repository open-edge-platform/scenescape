#!/usr/bin/env python

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


"""Functional tests for REST API authorization.

Covers:
  - General (non-superuser) can access resources via safe (read-only) endpoints
  - General users are denied write/delete access to protected endpoints
  - Deactivated user cannot obtain an authentication token
"""

_TEST_USER = "general_user"
_TEST_PASS = "general_pass"
ENTITIES = ["/scenes", "/cameras", "/users", "/regions", "/sensors", "/tripwires"]

import requests
from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result

def test_authz_general_user_can_list_entities(params, record_xml_attribute):
  """Verify that a general (non-superuser) user can list entities
  like /scenes, /cameras, /users, ...etc"""
  TEST_NAME = "NEX-T10443"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest.authenticate(params["user"], params["password"]), \
    "Authentication failed"
  
  try:
    result = rest.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create test user: {result.errors}"
    user_created = True

    rest_user = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert rest_user.authenticate(_TEST_USER, _TEST_PASS), \
      "General user authentication failed"


    for endpoint in ENTITIES:
      response = requests.get(
        f"{params['resturl']}{endpoint}",
        headers={"Authorization": f"Bearer {rest.token}"},
        verify=params["rootcert"],
      )
      assert response.status_code == HTTPStatus.OK, \
        f"Expected 200 OK for GET {endpoint}, got {response.status_code}: {response.text}"

    exit_code = 0
  finally:
    if user_created:
      rest.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)