#!/usr/bin/env python

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


"""Functional tests for REST API authorization.

Covers:
  - Non-superuser can access resources via safe (read-only) endpoints
  - Non-superusers are denied write/delete access to protected endpoints
  - Deactivated user cannot obtain an authentication token
"""

import pytest
import requests
from http import HTTPStatus
from scene_common.rest_client import RESTClient
from tests.utils.log import get_logger
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

pytestmark = pytest.mark.preserve_db

_TEST_USER = "general_user"
_TEST_PASS = "general_pass"

POST_ENTITIES_SINGULAR = [
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
  "/save-geospatial-snapshot/",
]

POST_ENTITIES_PLURAL = [
  "/assets",
  "/calibrationmarkers",
  "/cameras",
  "/regions",
  "/scenes",
  "/sensors",
  "/tripwires",
  "/users",
  "/scenes/child",
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


@pytest.fixture
def non_superuser_client(rest, params):
  result = rest.createUser({"username": _TEST_USER, "password": _TEST_PASS})
  assert result.statusCode == HTTPStatus.CREATED, \
    f"Failed to create test user: {result.errors}"
  try:
    client = RESTClient(params["resturl"], rootcert=params["rootcert"])
    assert client.authenticate(_TEST_USER, _TEST_PASS), \
      "Non-superuser authentication failed"
    yield client
  finally:
    rest.deleteUser(_TEST_USER)


@pytest.mark.test_name("NEX-T10443")
def test_authz_non_superuser_can_list_entities(non_superuser_client, params, result_recorder):
  """Verify that an authenticated non-superuser can list entities
  like /scenes, /cameras, /users, ...etc"""

  failures = []
  for endpoint in GET_ENTITIES:
    response = requests.get(
      f"{params['resturl']}{endpoint}",
      headers={"Authorization": f"Token {non_superuser_client.token}"},
      verify=params["rootcert"],
    )
    if response.status_code != HTTPStatus.OK:
      failures.append(
        f"GET {endpoint}: expected 200 OK, got {response.status_code}")
  assert not failures, "Non-superuser access checks failed:\n" + "\n".join(failures)

  result_recorder.success()


@pytest.mark.test_name("NEX-T23089")
def test_authz_non_superuser_cannot_create_entities(non_superuser_client, params, result_recorder):
  """Verify that an authenticated non-superuser can't create entities
  and receives HTTP 403 for requests like POST /scene, /camera, /user, ...etc"""

  failures = []
  for endpoint in POST_ENTITIES_SINGULAR:
    response = requests.post(
      f"{params['resturl']}{endpoint}",
      headers={"Authorization": f"Token {non_superuser_client.token}"},
      verify=params["rootcert"],
    )
    if endpoint == "/auth":
      # username and password are required fields for /auth
      assert response.status_code == HTTPStatus.BAD_REQUEST, \
        f"Expected 400 BAD REQUEST for POST {endpoint}, got {response.status_code}: {response.text}"
    else:
      if response.status_code != HTTPStatus.FORBIDDEN:
        failures.append(
          f"POST {endpoint}: expected 403 Forbidden, got {response.status_code}"
        )

  assert not failures, "Non-superuser access checks failed:\n" + "\n".join(failures)

  result_recorder.success()


@pytest.mark.test_name("NEX-T26178")
def test_authz_non_superuser_cannot_create_via_plural_endpoints(non_superuser_client, params, result_recorder):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to create entities via plural endpoints (POST /scenes, /cameras, /users, etc.)."""

  failures = []
  for endpoint in POST_ENTITIES_PLURAL:
    response = requests.post(
      f"{params['resturl']}{endpoint}",
      headers={"Authorization": f"Token {non_superuser_client.token}"},
      json={},
      verify=params["rootcert"],
    )
    if response.status_code != HTTPStatus.METHOD_NOT_ALLOWED:
      failures.append(
        f"POST {endpoint}: expected 405 Method Not Allowed, got {response.status_code}"
      )
  assert not failures, "Non-superuser plural endpoint access checks failed:\n" + "\n".join(failures)

  result_recorder.success()


@pytest.mark.test_name("NEX-T23090")
def test_authz_non_superuser_cannot_update_scene(rest, non_superuser_client, params, result_recorder):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to update a scene via PUT /scene/{uid}."""

  scenes = rest.getScenes({'name': params['scene_name']})
  assert scenes['count'] > 0, \
    f"Scene '{params['scene_name']}' not found"
  scene_id = scenes['results'][0]['uid']
  log.info(f"Using scene '{params['scene_name']}' uid={scene_id}")

  response = requests.put(
    f"{params['resturl']}/scene/{scene_id}",
    headers={"Authorization": f"Token {non_superuser_client.token}"},
    json={"name": "Modified Scene"},
    verify=params["rootcert"],
  )
  assert response.status_code == HTTPStatus.FORBIDDEN, \
    f"Expected 403 Forbidden for non-superuser scene update, got {response.status_code}"

  result_recorder.success()


@pytest.mark.test_name("NEX-T23091")
def test_authz_non_superuser_cannot_delete_scene(rest, non_superuser_client, params, result_recorder):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to delete a scene via DELETE /scene/{uid}."""

  scenes = rest.getScenes({'name': params['scene_name']})
  assert scenes['count'] > 0, \
    f"Scene '{params['scene_name']}' not found"
  scene_id = scenes['results'][0]['uid']
  log.info(f"Using scene '{params['scene_name']}' uid={scene_id}")

  response = requests.delete(
    f"{params['resturl']}/scene/{scene_id}",
    headers={"Authorization": f"Token {non_superuser_client.token}"},
    verify=params["rootcert"],
  )
  assert response.status_code == HTTPStatus.FORBIDDEN, \
    f"Expected 403 Forbidden for non-superuser scene delete, got {response.status_code}"

  result_recorder.success()


@pytest.mark.test_name("NEX-T23092")
def test_authz_non_superuser_cannot_create_user(non_superuser_client, params, result_recorder):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to create another user account via POST /user."""

  response = requests.post(
    f"{params['resturl']}/user",
    headers={"Authorization": f"Token {non_superuser_client.token}"},
    json={"username": "new_user", "password": "new_password"},
    verify=params["rootcert"],
  )
  assert response.status_code == HTTPStatus.FORBIDDEN, \
    f"Expected 403 Forbidden for non-superuser user creation, got {response.status_code}"

  result_recorder.success()


@pytest.mark.test_name("NEX-T23093")
def test_authz_non_superuser_cannot_update_user(non_superuser_client, params, result_recorder):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to update a user account via PUT /user/{username}, including their own account."""

  response = requests.put(
    f"{params['resturl']}/user/{_TEST_USER}",
    headers={"Authorization": f"Token {non_superuser_client.token}"},
    json={"first_name": "Updated"},
    verify=params["rootcert"],
  )
  assert response.status_code == HTTPStatus.FORBIDDEN, \
    f"Expected 403 Forbidden for non-superuser user update, got {response.status_code}"

  result_recorder.success()


@pytest.mark.test_name("NEX-T23094")
def test_authz_non_superuser_cannot_delete_user(non_superuser_client, params, result_recorder):
  """Verify that an authenticated non-superuser receives HTTP 403 when attempting
  to delete a user account via DELETE /user/{username}, including their own account."""

  response = requests.delete(
    f"{params['resturl']}/user/{_TEST_USER}",
    headers={"Authorization": f"Token {non_superuser_client.token}"},
    verify=params["rootcert"],
  )
  assert response.status_code == HTTPStatus.FORBIDDEN, \
    f"Expected 403 Forbidden for non-superuser user delete, got {response.status_code}"

  result_recorder.success()


@pytest.mark.test_name("NEX-T23095")
def test_authz_deactivated_user_cannot_authenticate(rest, params, result_recorder):
  """Verify that a deactivated (is_active=False) user cannot obtain an
  authentication token and POST /auth returns HTTP 400."""

  result = rest.createUser({"username": _TEST_USER, "password": _TEST_PASS})
  assert result.statusCode == HTTPStatus.CREATED, \
    f"Failed to create inactive test user: {result.errors}"

  try:
    res = rest.updateUser(_TEST_USER, {"is_active": False})
    assert res.statusCode == HTTPStatus.OK, \
      f"Admin failed to deactivate user: {res.errors}"

    response = requests.post(
      f"{params['resturl']}/auth",
      data={"username": _TEST_USER, "password": _TEST_PASS},
      verify=params["rootcert"],
    )
    assert response.status_code == HTTPStatus.BAD_REQUEST, \
      f"Expected 400 Bad Request for deactivated user, got {response.status_code}"

    result_recorder.success()
  finally:
    rest.deleteUser(_TEST_USER)
