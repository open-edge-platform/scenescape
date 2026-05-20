#!/usr/bin/env python

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


"""Functional tests for REST API authorization.

Covers:
  - General (non-superuser) can access resources via safe (read-only) endpoints
  - Non-superusers are denied write/delete access to protected endpoints
  - Deactivated user cannot obtain an authentication token
"""

import requests
from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.common_test_utils import record_test_result
from scene_common import log

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
"/database-ready",
]

def test_authz_non_superuser_can_list_entities(params, record_xml_attribute):
  """Verify that an authenticated non-superuser can list entities
  like /scenes, /cameras, /users, ...etc"""

  TEST_NAME = "NEX-T10443"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest_admin = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_admin.authenticate(params["user"], params["password"]), \
    "Authentication failed"

  try:
    result = rest_admin.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create test user: {result.errors}"
    user_created = True

    rest_user = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert rest_user.authenticate(_TEST_USER, _TEST_PASS), \
      "Non-superuser authentication failed"


    for endpoint in GET_ENTITIES:
      response = requests.get(
        f"{params['resturl']}{endpoint}",
        headers={"Authorization": f"Token {rest_user.token}"},
        verify=params["rootcert"],
      )
      assert response.status_code == HTTPStatus.OK, \
        f"Expected 200 OK for GET {endpoint}, got {response.status_code}: {response.text}"

    exit_code = 0
  finally:
    if user_created:
      rest_admin.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)

def test_authz_non_superuser_cannot_create_entities(params, record_xml_attribute):
  """Verify that an authenticated non-superuser can't create entities
  and receives HTTP 403 for requests like POST /scene, /camera, /user, ...etc"""

  TEST_NAME = "NEX-T23089"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest_admin = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_admin.authenticate(params["user"], params["password"]), \
    "Authentication failed"

  try:
    result = rest_admin.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create test user: {result.errors}"
    user_created = True

    rest_user = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert rest_user.authenticate(_TEST_USER, _TEST_PASS), \
      "Non-superuser authentication failed"


    for endpoint in POST_ENTITIES:
      response = requests.post(
        f"{params['resturl']}{endpoint}",
        headers={"Authorization": f"Token {rest_user.token}"},
        verify=params["rootcert"],
      )
      if endpoint == "/auth":
        # username and password are required fields for /auth
        assert response.status_code == HTTPStatus.BAD_REQUEST, \
          f"Expected 400 BAD REQUEST for POST {endpoint}, got {response.status_code}: {response.text}"
      else:
        assert response.status_code == HTTPStatus.FORBIDDEN, \
          f"Expected 403 FORBIDDEN for POST {endpoint}, got {response.status_code}: {response.text}"

    exit_code = 0
  finally:
    if user_created:
      rest_admin.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)

def test_authz_non_superuser_cannot_update_scene(params, record_xml_attribute):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to update a scene via PUT /scene/{uid}."""

  TEST_NAME = "NEX-T23090"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest_admin = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_admin.authenticate(params["user"], params["password"]), \
    "Admin authentication failed"

  scenes = rest_admin.getScenes({'name': params['scene_name']})
  assert scenes['count'] > 0, \
    f"Scene '{params['scene_name']}' not found"
  scene_id = scenes['results'][0]['uid']
  log.info(f"Using scene '{params['scene_name']}' uid={scene_id}")

  try:
    result = rest_admin.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create general test user: {result.errors}"
    user_created = True

    rest_user = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert rest_user.authenticate(_TEST_USER, _TEST_PASS), \
      "Non-superuser authentication failed"

    response = requests.put(
      f"{params['resturl']}/scene/{scene_id}",
      headers={"Authorization": f"Token {rest_user.token}"},
      json={"name": "Modified Scene"},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.FORBIDDEN, \
      f"Expected 403 Forbidden for non-superuser scene update, got {response.status_code}"

    exit_code = 0
  finally:
    if user_created:
      rest_admin.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)

def test_authz_non_superuser_cannot_delete_scene(params, record_xml_attribute):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to delete a scene via DELETE /scene/{uid}.

  The permission check fires before resource lookup, so a placeholder UUID is
  sufficient to confirm the access control policy without requiring a real scene.
  """
  TEST_NAME = "NEX-T23091"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest_admin = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_admin.authenticate(params["user"], params["password"]), \
    "Admin authentication failed"

  scenes = rest_admin.getScenes({'name': params['scene_name']})
  assert scenes['count'] > 0, \
    f"Scene '{params['scene_name']}' not found"
  scene_id = scenes['results'][0]['uid']
  log.info(f"Using scene '{params['scene_name']}' uid={scene_id}")

  try:
    result = rest_admin.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create general test user: {result.errors}"
    user_created = True

    rest_user = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert rest_user.authenticate(_TEST_USER, _TEST_PASS), \
      "Non-superuser authentication failed"

    response = requests.delete(
      f"{params['resturl']}/scene/{scene_id}",
      headers={"Authorization": f"Token {rest_user.token}"},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.FORBIDDEN, \
      f"Expected 403 Forbidden for non-superuser scene delete, got {response.status_code}"

    exit_code = 0
  finally:
    if user_created:
      rest_admin.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)

def test_authz_non_superuser_cannot_create_user(params, record_xml_attribute):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to create another user account via POST /user."""
  TEST_NAME = "NEX-T23092"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest_admin = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_admin.authenticate(params["user"], params["password"]), \
    "Admin authentication failed"

  try:
    result = rest_admin.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create general test user: {result.errors}"
    user_created = True

    rest_user = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert rest_user.authenticate(_TEST_USER, _TEST_PASS), \
      "Non-superuser authentication failed"

    response = requests.post(
      f"{params['resturl']}/user",
      headers={"Authorization": f"Token {rest_user.token}"},
      json={"username": "new_user", "password": "new_password"},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.FORBIDDEN, \
      f"Expected 403 Forbidden for non-superuser user creation, got {response.status_code}"

    exit_code = 0
  finally:
    if user_created:
      rest_admin.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)

def test_authz_non_superuser_cannot_update_user(params, record_xml_attribute):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to update a user account via PUT /user/{username}, including their own account."""
  TEST_NAME = "NEX-T23093"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest_admin = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_admin.authenticate(params["user"], params["password"]), \
    "Admin authentication failed"

  try:
    result = rest_admin.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create general test user: {result.errors}"
    user_created = True

    rest_user = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert rest_user.authenticate(_TEST_USER, _TEST_PASS), \
      "Non-superuser authentication failed"

    response = requests.put(
      f"{params['resturl']}/user/{_TEST_USER}",
      headers={"Authorization": f"Token {rest_user.token}"},
      json={"first_name": "Updated"},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.FORBIDDEN, \
      f"Expected 403 Forbidden for non-superuser user update, got {response.status_code}"

    exit_code = 0
  finally:
    if user_created:
      rest_admin.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)

def test_authz_non_superuser_cannot_delete_user(params, record_xml_attribute):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to delete a user account via DELETE /user/{username}, including their own account."""
  TEST_NAME = "NEX-T23094"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest_admin = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_admin.authenticate(params["user"], params["password"]), \
    "Admin authentication failed"

  try:
    result = rest_admin.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create general test user: {result.errors}"
    user_created = True

    rest_user = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert rest_user.authenticate(_TEST_USER, _TEST_PASS), \
      "Non-superuser authentication failed"

    response = requests.delete(
      f"{params['resturl']}/user/{_TEST_USER}",
      headers={"Authorization": f"Token {rest_user.token}"},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.FORBIDDEN, \
      f"Expected 403 Forbidden for non-superuser user delete, got {response.status_code}"

    exit_code = 0
  finally:
    if user_created:
      rest_admin.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)

def test_authz_deactivated_user_cannot_authenticate(params, record_xml_attribute):
  """Verify that a deactivated (is_active=False) user cannot obtain an
  authentication token and POST /auth returns HTTP 400."""
  TEST_NAME = "NEX-T23095"
  record_xml_attribute("name", TEST_NAME)
  exit_code = 1
  user_created = False

  rest_admin = RESTClient(params["resturl"], rootcert=params["rootcert"])
  assert rest_admin.authenticate(params["user"], params["password"]), \
    "Admin authentication failed"

  try:
    result = rest_admin.createUser({"username": _TEST_USER, "password": _TEST_PASS})
    assert result.statusCode == HTTPStatus.CREATED, \
      f"Failed to create inactive test user: {result.errors}"
    user_created = True

    res = rest_admin.updateUser(_TEST_USER, {"is_active": False})
    assert res.statusCode == HTTPStatus.OK, \
      f"Admin failed to deactivate user: {res.errors}"

    response = requests.post(
      f"{params['resturl']}/auth",
      data={"username": _TEST_USER, "password": _TEST_PASS},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST, \
      f"Expected 400 Bad Request for deactivated user, got {response.status_code}"

    exit_code = 0
  finally:
    if user_created:
      rest_admin.deleteUser(_TEST_USER)
    record_test_result(TEST_NAME, exit_code)
