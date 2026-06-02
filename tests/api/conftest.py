# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import requests
import os
from mapping_client import MappingClient
from scene_common.rest_client import RESTClient

def pytest_addoption(parser):
  parser.addoption("--file", default=None,
                   help="Specific scenario file to run (e.g., 'scenarios/scene.json')")
  parser.addoption("--test_case", default=None,
                   help="Specific test case name to run")

@pytest.fixture(scope='session')
def base_url():
  return os.environ.get("API_BASE_URL", "https://localhost")

@pytest.fixture(scope='session')
def username():
  return os.environ.get("API_USERNAME", "admin")

@pytest.fixture(scope='session')
def password():
  return os.environ.get("SUPASS", "admin")

@pytest.fixture(scope='session')
def token(base_url, username, password):
  """Fetch authentication token from the SceneScape API"""
  response = requests.post(
    f"{base_url}/api/v1/auth",
    data={"username": username, "password": password},
    verify=False,
    timeout=10,
  )
  response.raise_for_status()
  api_token = response.json()["token"]
  return api_token

@pytest.fixture(scope='session')
def http_client(token, base_url) -> RESTClient:
  return RESTClient(url=f"{base_url}/api/v1", token=token, verify_ssl=False)

@pytest.fixture(scope='session')
def autocalib_client(token, base_url) -> RESTClient:
  return RESTClient(url=f"{base_url}/v1", token=token, verify_ssl=False)

@pytest.fixture(scope='session')
def mapping_client(token, base_url) -> MappingClient:
  return MappingClient(url=f"{base_url}:8444", token=token, verify_ssl=False)

@pytest.fixture(scope='session')
def api_map(http_client, autocalib_client, mapping_client):
  """Map API names to their respective clients"""
  return {
    "scene": http_client,
    "camera": http_client,
    "sensor": http_client,
    "region": http_client,
    "tripwire": http_client,
    "user": http_client,
    "asset": http_client,
    "child": http_client,
    "autocalibration": autocalib_client,
    "mapping": mapping_client,
}
