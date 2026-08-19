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

@pytest.fixture(autouse=True)
def oversized_upload_file(request):
  """Generate a >100MB dummy .mp4 for the mapping payload-too-large (413) test.

  Scoped to mapping_api scenarios only (via the scenario's _source_file). The
  mapping service caps requests at 100MB (MAX_CONTENT_LENGTH) and rejects
  oversized uploads before decoding, so the file only needs to exceed that
  size; its contents are never parsed. It is created at runtime as a sparse
  file to avoid committing a large binary, and removed afterwards.
  """
  callspec = getattr(request.node, "callspec", None)
  scenario = callspec.params.get("test_case") if callspec else None
  is_mapping = isinstance(scenario, dict) and scenario.get("_source_file") == "mapping_api"

  target = ROOT_DIR / "tests" / "api" / "test_media" / "LargeVideoForTest.mp4"
  created = False
  if is_mapping and not target.exists():
    target.parent.mkdir(parents=True, exist_ok=True)
    # Minimal ftyp box so the file is recognizably an MP4 container.
    ftyp = (
      b"\x00\x00\x00\x20ftyp"
      b"isom\x00\x00\x02\x00"
      b"isomiso2avc1mp41"
    )
    size = 101 * 1024 * 1024  # 101MB, just over the 100MB server limit
    with open(target, "wb") as f:
      f.write(ftyp)
      f.truncate(size)
    created = True
  yield target
  if created:
    target.unlink(missing_ok=True)

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
    "calculateintrinsics": http_client,
    "sensor": http_client,
    "region": http_client,
    "tripwire": http_client,
    "user": http_client,
    "asset": http_client,
    "child": http_client,
    "aclcheck": http_client,
    "autocalibration": autocalib_client,
    "mapping": mapping_client,
}
