#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Helpers for functional ReID tests across VDMS and Qdrant backends."""

import time

from controller.reid_constants import SCHEMA_NAME
from controller.reid_registry import create_reid_database, normalize_backend_name
from tests.utils.log import get_logger

log = get_logger(__name__)

REID_DATABASE = normalize_backend_name()


def get_reid_profile_module(semantic=False):
  from tests.utils import profiles
  if REID_DATABASE == "QDRANT":
    return profiles.REID_SEMANTIC_QDRANT if semantic else profiles.REID_QDRANT
  return profiles.REID_SEMANTIC if semantic else profiles.REID


def connect_reid_database(db, use_tls=True):
  if REID_DATABASE == "QDRANT":
    db.connect()
    assert db.connected, "Failed to connect to Qdrant. Is the Qdrant service running?"
    return

  if not use_tls:
    from controller.vdms_adapter import vdms
    db.db = vdms.vdms(use_tls=False)
  db.connect()
  assert db.db.connected, "Failed to connect to VDMS. Is the VDMS service running?"


def wait_for_reid_backend_ready(use_tls=False, max_attempts=30, retry_interval=1):
  backend_name = REID_DATABASE
  for attempt in range(max_attempts):
    try:
      db = create_reid_database()
      connect_reid_database(db, use_tls=use_tls)
      if REID_DATABASE == "QDRANT":
        db.client.get_collections()
      else:
        query = [{
          "FindDescriptor": {
            "set": SCHEMA_NAME,
            "constraints": {
              "type": ["==", "person"]
            },
            "results": {
              "list": ["uuid"],
              "blob": False
            }
          }
        }]
        db.db.query(query)
      log.info(f"{backend_name} is ready (attempt {attempt + 1})")
      return True
    except Exception as e:
      log.debug(f"{backend_name} health check attempt {attempt + 1}/{max_attempts}: {e}")

    if attempt < max_attempts - 1:
      time.sleep(retry_interval)

  log.warning(f"{backend_name} not ready after {max_attempts} attempts")
  return False


def ensure_reid_schema(dimensions=256, similarity_metric="L2"):
  """Ensure the default ReID schema exists with the requested dimensions/metric."""
  db = create_reid_database(similarity_metric=similarity_metric, dimensions=None)
  connect_reid_database(db, use_tls=False)
  db.ensureSchema(dimensions)
  log.info(
    f"Ensured ReID schema '{db.set_name}' "
    f"({dimensions}D, {db.similarity_metric})")


def query_reid_count(object_type="person"):
  db = create_reid_database()
  connect_reid_database(db, use_tls=False)

  if REID_DATABASE == "QDRANT":
    from qdrant_client.http import models
    query_filter = models.Filter(must=[
      models.FieldCondition(
        key="type",
        match=models.MatchValue(value=str(object_type)),
      )
    ])
    count_result = db.client.count(
      collection_name=SCHEMA_NAME,
      count_filter=query_filter,
      exact=True,
    )
    return int(count_result.count)

  query = [{
    "FindDescriptor": {
      "set": SCHEMA_NAME,
      "constraints": {
        "type": ["==", object_type]
      },
      "results": {
        "list": ["uuid", "rvid", "type"],
        "blob": False
      }
    }
  }]

  result = db.db.query(query)
  if isinstance(result, tuple) and len(result) == 2:
    response, _ = result
  else:
    log.error(f"VDMS query returned unexpected result type: {type(result)}")
    return 0

  if response and len(response) > 0:
    find_result = response[0].get("FindDescriptor", {})
    entities = find_result.get("entities", [])
    return len(entities)
  return 0
