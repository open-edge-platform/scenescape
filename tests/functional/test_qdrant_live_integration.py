#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Live integration tests against a running Qdrant instance (no full compose stack)."""

import os
import uuid

import numpy as np
import pytest

from controller.qdrant_adapter import QdrantDatabase
from controller.reid_env import (
  DEFAULT_HOSTNAME,
  DEFAULT_PORT,
  get_reid_ca_cert,
)


def _connect_candidates():
  """Prefer shared TLS defaults (compose), then plain localhost for ad-hoc Qdrant."""
  secrets_dir = os.environ.get(
    "SECRETSDIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "manager", "secrets"),
  )
  ca_default = os.path.join(secrets_dir, "certs", "scenescape-ca.pem")
  ca_cert = get_reid_ca_cert()
  if ca_cert.startswith("/run/secrets/") and os.path.isfile(ca_default):
    ca_cert = ca_default

  yield {
    "hostname": DEFAULT_HOSTNAME,
    "port": int(DEFAULT_PORT),
    "use_tls": True,
    "ca_cert": ca_cert,
  }
  yield {
    "hostname": "localhost",
    "port": int(DEFAULT_PORT),
    "use_tls": False,
  }


@pytest.fixture
def qdrant_db():
  last_error = None
  for kwargs in _connect_candidates():
    db = QdrantDatabase(**kwargs)
    db.connect()
    if db.connected:
      return db
    last_error = kwargs
  pytest.skip(
    f"Qdrant is not available (tried TLS {DEFAULT_HOSTNAME}:{DEFAULT_PORT} "
    f"and plain localhost:{DEFAULT_PORT}; last={last_error})")


def test_live_schema_and_vector_operations(qdrant_db):
  set_name = f"reid_test_{uuid.uuid4().hex[:8]}"
  qdrant_db.set_name = set_name
  qdrant_db.similarity_metric = "L2"
  qdrant_db.ensureSchema(256)

  vec1 = np.random.rand(256).astype(np.float32)
  vec2 = vec1 + np.random.rand(256).astype(np.float32) * 0.01
  vec3 = np.random.rand(256).astype(np.float32)

  qdrant_db.addEntry(
    "uuid-1", "track-1", "person", [vec1], set_name=set_name,
    gender={"label": "Female", "confidence": 0.95},
    run_id="integration-test")
  qdrant_db.addEntry(
    "uuid-2", "track-2", "person", [vec3], set_name=set_name,
    gender={"label": "Male", "confidence": 0.95},
    run_id="integration-test")

  matches = qdrant_db.findMatches(
    "person", [vec2], set_name=set_name, k_neighbors=2,
    gender={"label": "Female", "confidence": 0.95})
  assert matches and matches[0]
  assert matches[0][0]["uuid"] == "uuid-1"


def test_live_persist_attributes(qdrant_db):
  set_name = f"reid_persist_{uuid.uuid4().hex[:8]}"
  qdrant_db.set_name = set_name
  qdrant_db.similarity_metric = "L2"
  qdrant_db.ensureSchema(256)

  vec = np.random.rand(256).astype(np.float32)
  qdrant_db.addEntry(
    "persist-uuid", "track-9", "person", [vec], set_name=set_name,
    persist={"gender": "Female", "timestamp": 100})
  qdrant_db.addEntry(
    "persist-uuid", "track-9", "person", [vec], set_name=set_name,
    persist={"gender": "Male", "timestamp": 200})

  attrs = qdrant_db.getPersistedAttributes("persist-uuid", set_name=set_name)
  assert attrs == {"gender": "Male"}
