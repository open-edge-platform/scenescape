#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Helpers for functional ReID tests across VDMS and Qdrant backends."""

import os
import time
from pathlib import Path

from controller.reid_constants import SCHEMA_NAME
from controller.reid_registry import create_reid_database, normalize_backend_name
from tests.utils.log import get_logger

log = get_logger(__name__)

REID_DATABASE = normalize_backend_name()


def configure_host_reid_certs():
  """Point ReID TLS env vars at host secrets so adapters can reach container VDMS/Qdrant."""
  secrets = Path(os.environ.get("SECRETSDIR") or "manager/secrets")
  certs = secrets / "certs"
  os.environ.setdefault("REID_CA_CERT", str(certs / "scenescape-ca.pem"))
  os.environ.setdefault("REID_CLIENT_CERT", str(certs / "scenescape-reid.crt"))
  os.environ.setdefault("REID_CLIENT_KEY", str(certs / "scenescape-reid.key"))
  os.environ.setdefault("REID_USE_TLS", "true")


def get_reid_profile_module(semantic=False):
  from tests.utils import profiles
  if REID_DATABASE == "QDRANT":
    return profiles.REID_SEMANTIC_QDRANT if semantic else profiles.REID_QDRANT
  return profiles.REID_SEMANTIC if semantic else profiles.REID


def get_reid_core_profile_module():
  """ReID stack without DLStreamer/GPU video (MQTT-injected detections only)."""
  from tests.utils import profiles
  if REID_DATABASE == "QDRANT":
    return profiles.REID_CORE_QDRANT
  return profiles.REID_CORE


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


def _apply_reid_endpoint(db, hostname=None, port=None):
  """Override adapter hostname/port for multi-VDMS hierarchy topologies."""
  if hostname is not None:
    db.hostname = hostname
  if port is not None:
    db.port = int(port)


def wait_for_reid_backend_ready(use_tls=True, max_attempts=30, retry_interval=1,
                                hostname=None, port=None):
  configure_host_reid_certs()
  backend_name = REID_DATABASE
  endpoint = f" @ {hostname}:{port}" if hostname else ""
  for attempt in range(max_attempts):
    try:
      db = create_reid_database()
      _apply_reid_endpoint(db, hostname=hostname, port=port)
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
      log.info(f"{backend_name} is ready{endpoint} (attempt {attempt + 1})")
      return True
    except Exception as e:
      log.debug(
        f"{backend_name} health check{endpoint} "
        f"attempt {attempt + 1}/{max_attempts}: {e}")

    if attempt < max_attempts - 1:
      time.sleep(retry_interval)

  log.warning(f"{backend_name} not ready{endpoint} after {max_attempts} attempts")
  return False


def ensure_reid_schema(dimensions=256, similarity_metric="IP",
                       hostname=None, port=None):
  """Ensure the default ReID schema exists with the requested dimensions/metric."""
  configure_host_reid_certs()
  db = create_reid_database(similarity_metric=similarity_metric, dimensions=None)
  _apply_reid_endpoint(db, hostname=hostname, port=port)
  connect_reid_database(db, use_tls=True)
  db.ensureSchema(dimensions)
  log.info(
    f"Ensured ReID schema '{db.set_name}' "
    f"({dimensions}D, {db.similarity_metric}"
    f"{f' @ {hostname}:{port}' if hostname else ''})")


def query_reid_count(object_type="person", hostname=None, port=None):
  configure_host_reid_certs()
  db = create_reid_database()
  _apply_reid_endpoint(db, hostname=hostname, port=port)
  connect_reid_database(db, use_tls=True)

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


def count_near_exact_uuids(embedding, object_type="person",
                           score_threshold=0.95, k_neighbors=20,
                           hostname=None, port=None):
  """Count distinct enrolled UUIDs that nearly-exactly match *embedding*.

  Used by hierarchy enrollment tests to detect parent-side double enrollment of
  a child crop. Controllers store descriptors under IP/COSINE (higher is better).

  @param hostname  Optional ReID host override (multi-VDMS topologies).
  @param port      Optional ReID port override.
  @return  Tuple (unique_uuid_count, matching_entities)
  """
  import numpy as np
  from controller.reid_constants import is_higher_better_metric

  configure_host_reid_certs()
  db = create_reid_database()
  _apply_reid_endpoint(db, hostname=hostname, port=port)
  connect_reid_database(db, use_tls=True)
  vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
  matches = db.findMatches(
    object_type, [vector], k_neighbors=k_neighbors)
  entities = matches[0] if matches else []
  higher_better = is_higher_better_metric(db.similarity_metric)

  matched = []
  uuids = set()
  for entity in entities:
    score = entity.get("_distance")
    if score is None:
      continue
    if higher_better:
      keep = score >= score_threshold
    else:
      keep = score <= score_threshold
    if not keep:
      continue
    matched.append(entity)
    uid = entity.get("uuid")
    if uid is not None:
      uuids.add(uid)

  log.info(
    f"Near-exact ReID matches for injected embedding"
    f"{f' @ {hostname}:{port}' if hostname else ''}: "
    f"{len(matched)} descriptor(s), {len(uuids)} unique uuid(s), "
    f"metric={db.similarity_metric}, threshold={score_threshold}")
  return len(uuids), matched
