# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Positioning source ownership for broker authorization.

The deployment manifest (`source_id -> resolver_id`, the file Positioning reads
with `--assignments`) is the only record of which resolver may publish poses for
a source. Manager reads the same file so pose writes can be bound to the
resolver's assigned sources. A missing, unreadable, or invalid manifest assigns
nothing, so pose writes are denied.
"""

import json
import os
import threading

from scene_common import log

ASSIGNMENTS_FILE_ENV = "POSITIONING_ASSIGNMENTS_FILE"
RESOLVER_ID_ENV = "POSITIONING_RESOLVER_ID"
DEFAULT_RESOLVER_ID = "positioning-default"

_lock = threading.Lock()
_cache = {"key": None, "assignments": {}}


def _is_topic_segment(value):
  return isinstance(value, str) and bool(value) and not any(char in value for char in "/+#")


def parse_assignments(manifest):
  """Same rules as Positioning's `load_assignments`; raises ValueError when invalid."""
  if not isinstance(manifest, dict):
    raise ValueError("assignment manifest must be a JSON object")
  assignments = {}
  for source_id, resolver_id in manifest.items():
    if source_id.startswith("$"):
      continue
    if not _is_topic_segment(source_id) or not _is_topic_segment(resolver_id):
      raise ValueError(
        f"assignment '{source_id}' must map a source_id to a resolver_id topic segment")
    assignments[source_id] = resolver_id
  return assignments


def load_assignments(path):
  """Return the manifest's assignments, re-reading the file only when it changes."""
  if not path:
    return {}
  try:
    stat = os.stat(path)
  except OSError as error:
    key = (path, None, str(error))
    stat = None
  else:
    key = (path, stat.st_mtime_ns, stat.st_size, stat.st_ino)
  with _lock:
    if _cache["key"] == key:
      return _cache["assignments"]
    assignments = {}
    if stat is None:
      log.warning(f"Positioning assignment manifest {path} is not readable; "
                  "denying pose writes")
    else:
      try:
        with open(path, "r", encoding="utf-8") as manifest_file:
          assignments = parse_assignments(json.load(manifest_file))
      except (OSError, ValueError) as error:
        log.warning(f"Positioning assignment manifest {path} is invalid ({error}); "
                    "denying pose writes")
    _cache.update(key=key, assignments=assignments)
    return assignments


def configured_resolver_id():
  return os.environ.get(RESOLVER_ID_ENV, DEFAULT_RESOLVER_ID)


def is_assigned(source_id, resolver_id):
  """True when the manifest assigns `source_id` to `resolver_id`."""
  if not _is_topic_segment(source_id):
    return False
  assignments = load_assignments(os.environ.get(ASSIGNMENTS_FILE_ENV))
  return assignments.get(source_id) == resolver_id
