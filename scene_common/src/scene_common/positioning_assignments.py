# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Reader for the deployment-owned `source_id -> resolver_id` assignment manifest.

Consumers (Controller, Tracker) use it only to learn which Resolver publishes the
session status for a PTZ source. Camera-to-scene membership stays in Manager.
"""

import json
from typing import Dict

from scene_common.positioning_config import PositioningConfigError

_FORBIDDEN_SEGMENT_CHARS = ("/", "+", "#", "\x00")
_MAX_SEGMENT_LENGTH = 256


def _is_topic_segment(value) -> bool:
  return (isinstance(value, str) and 0 < len(value) <= _MAX_SEGMENT_LENGTH
          and not any(char in value for char in _FORBIDDEN_SEGMENT_CHARS))


def parse_assignments(manifest) -> Dict[str, str]:
  """Validate a parsed manifest; keys starting with `$` (comments) are ignored.

  @raises PositioningConfigError for a non-object manifest or an invalid topic segment
  """
  if not isinstance(manifest, dict):
    raise PositioningConfigError("Positioning assignment manifest must be a JSON object")
  assignments = {}
  for source_id, resolver_id in manifest.items():
    if isinstance(source_id, str) and source_id.startswith("$"):
      continue
    if not _is_topic_segment(source_id) or not _is_topic_segment(resolver_id):
      raise PositioningConfigError(
        f"Assignment {source_id!r} must map a source_id to a resolver_id topic segment")
    assignments[source_id] = resolver_id
  return assignments


def load_assignments(path: str) -> Dict[str, str]:
  """@raises PositioningConfigError when the file is unreadable or invalid"""
  try:
    with open(path, "r", encoding="utf-8") as manifest_file:
      manifest = json.load(manifest_file)
  except (OSError, ValueError) as error:
    raise PositioningConfigError(
      f"Cannot read positioning assignment manifest {path}: {error}") from error
  return parse_assignments(manifest)
