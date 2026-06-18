# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
import requests
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
MAPPING_SRC_DIR = ROOT_DIR / "mapping" / "src"
AUTOCALIB_SRC_DIR = ROOT_DIR / "autocalibration" / "src"
from scene_common.client_factory import create_scenescape_clients
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
  """Fetch authentication token from the Scenescape API"""
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
def service_clients(token, base_url):
  return create_scenescape_clients(
      base_url=base_url,
      token=token,
      verify_ssl=False,
      service_src_dirs=[AUTOCALIB_SRC_DIR, MAPPING_SRC_DIR],
      strict_imports=True,
  )

@pytest.fixture(scope='session')
def http_client(service_clients) -> RESTClient:
  return service_clients.core

@pytest.fixture(scope='session')
def autocalib_client(service_clients):
  return service_clients.autocalibration

@pytest.fixture(scope='session')
def mapping_client(service_clients):
  return service_clients.mapping

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
