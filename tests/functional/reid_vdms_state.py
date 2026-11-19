#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Seed and snapshot VDMS ReID schema state from the host for multi-controller tests."""

import json
from collections import Counter
from contextlib import contextmanager

import numpy as np

from controller.vdms_adapter import SCHEMA_MARKER_CLASS

DESCRIPTOR_SET_CLASS = "VD:DESCSET"


@contextmanager
def vdms_client(set_name="reid_vector", similarity_metric="IP",
                hostname=None, port=None):
  """Yield a connected host-side VDMS adapter that does not initialize any schema.

  Controllers create descriptor sets with IP even when reid-config.json says
  COSINE, so IP is the metric a matching schema carries.
  """
  from controller.reid_registry import create_reid_database
  from tests.functional.reid_backend import configure_host_reid_certs, connect_reid_database

  configure_host_reid_certs()
  db = create_reid_database(
    "VDMS", set_name=set_name, similarity_metric=similarity_metric, dimensions=None)
  if hostname is not None:
    db.hostname = hostname
  if port is not None:
    db.port = int(port)
  connect_reid_database(db, use_tls=True)
  try:
    yield db
  finally:
    db.db.disconnect()


def _send(db, query, blobs=None):
  responses, _ = db.sendQuery(query, blobs)
  return responses


def _require_ok(responses, command, expected):
  if len(responses) != expected or any(r.get("status") != 0 for r in responses):
    raise RuntimeError(f"{command} failed: {responses}")


def seed_descriptor_set(db, set_name, dimensions, metric, descriptors=0,
                        object_type="person", seed=0):
  """Create a descriptor set and fill it with random unit-scale descriptors.

  @return  The seeded descriptor uuids.
  """
  _require_ok(_send(db, [{"AddDescriptorSet": {
    "name": set_name, "metric": metric, "dimensions": dimensions}}]),
    "AddDescriptorSet", 1)
  if descriptors <= 0:
    return []

  uuids = [f"seed-{set_name}-{i}" for i in range(descriptors)]
  vectors = np.random.default_rng(seed).standard_normal(
    (descriptors, dimensions)).astype(np.float32)
  query = [{"AddDescriptor": {"set": set_name, "properties": {
    "uuid": uuid, "rvid": f"seed-track-{i}", "type": object_type}}}
    for i, uuid in enumerate(uuids)]
  _require_ok(_send(db, query, [v.tobytes() for v in vectors]),
              "AddDescriptor", descriptors)
  return uuids


def seed_schema_marker(db, set_name, dimensions=None, metric=None):
  """Write a ReidSchemaMarker row; a None dimensions or metric leaves the marker incomplete."""
  properties = {"set_name": set_name}
  if dimensions is not None:
    properties["dimensions"] = dimensions
  if metric is not None:
    properties["metric"] = metric
  _require_ok(_send(db, [{"AddEntity": {
    "class": SCHEMA_MARKER_CLASS, "properties": properties}}]), "AddEntity", 1)


def _canonical(entity):
  return json.dumps(entity, sort_keys=True)


def _sorted_entities(entities):
  return sorted(entities, key=_canonical)


def _find_entities(db, entity_class, properties):
  responses = _send(db, [{"FindEntity": {
    "class": entity_class, "results": {"list": properties}}}])
  if len(responses) != 1 or responses[0].get("status") != 0:
    raise RuntimeError(f"FindEntity {entity_class} failed: {responses}")
  return _sorted_entities(responses[0].get("entities") or [])


def _find_descriptors(db, set_name):
  command = {"FindDescriptor": {
    "set": set_name, "results": {"list": ["uuid", "rvid", "type"], "blob": False}}}
  responses = _send(db, [command])
  if len(responses) != 1:
    raise RuntimeError(f"FindDescriptor {set_name} failed: {responses}")
  if db._isEmptyLookup(command, responses[0]):
    return []
  if responses[0].get("status") != 0:
    raise RuntimeError(f"FindDescriptor {set_name} failed: {responses}")
  return _sorted_entities(responses[0].get("entities") or [])


def snapshot_vdms_state(db, set_name):
  """Capture every descriptor set, every schema marker row and the named set's descriptors.

  VDMS 2.12 does not expose a descriptor set's metric, so the metric is only
  visible through the marker rows.
  """
  return {
    "descriptor_sets": _find_entities(db, DESCRIPTOR_SET_CLASS, ["VD:name", "VD:dimensions"]),
    "markers": _find_entities(db, SCHEMA_MARKER_CLASS, ["set_name", "dimensions", "metric"]),
    "descriptors": _find_descriptors(db, set_name),
  }


def snapshot_diff(before, after):
  """List the rows removed from or added to each snapshot section, duplicates counted."""
  lines = []
  for section in sorted(set(before) | set(after)):
    old = Counter(_canonical(e) for e in before.get(section, []))
    new = Counter(_canonical(e) for e in after.get(section, []))
    lines += [f"{section}: removed {row} x{n}" for row, n in (old - new).items()]
    lines += [f"{section}: added {row} x{n}" for row, n in (new - old).items()]
  return lines


def assert_snapshots_equal(before, after):
  diff = snapshot_diff(before, after)
  assert not diff, "VDMS state changed:\n" + "\n".join(f"  {line}" for line in diff)
