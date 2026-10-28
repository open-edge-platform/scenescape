#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Render the dedicated Positioning listener ACL from its ownership manifest."""

import argparse
import json
import os
import tempfile


POSITIONING_CERT_IDENTITY = "positioning.scenescape.intel.com"


def _topic_segment(value, label):
  if not isinstance(value, str) or not value or any(
      char in value for char in ("/", "+", "#", "\n", "\r", "\0", " ")):
    raise ValueError(f"{label} must be a non-empty MQTT topic segment")
  return value


def render_acl(assignments, resolver_id):
  """Return ACL entries limited to one Resolver and its owned camera topics."""
  resolver_id = _topic_segment(resolver_id, "resolver_id")
  if not isinstance(assignments, dict):
    raise ValueError("Positioning assignments must be a JSON object")

  sources = []
  for source_id, owner in assignments.items():
    # Matches the Positioning, Manager and Controller loaders: `$` keys are comments.
    if isinstance(source_id, str) and source_id.startswith("$"):
      continue
    source_id = _topic_segment(source_id, "source_id")
    owner = _topic_segment(owner, f"assignment for {source_id}")
    if owner == resolver_id:
      sources.append(source_id)

  lines = [
    f"user {POSITIONING_CERT_IDENTITY}",
    f"topic write scenescape/positioning/status/{resolver_id}",
  ]
  for source_id in sorted(sources):
    lines.extend((
      f"topic read scenescape/cmd/camera/config/{source_id}",
      f"topic write scenescape/positioning/pose/{source_id}",
    ))
  return "\n".join(lines) + "\n"


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--assignments", required=True, help="source_id -> resolver_id JSON file")
  parser.add_argument("--resolver-id", required=True)
  parser.add_argument("--output", required=True, help="ACL file destination")
  args = parser.parse_args()

  with open(args.assignments, encoding="utf-8") as assignments_file:
    assignments = json.load(assignments_file)
  acl = render_acl(assignments, args.resolver_id)

  output = os.path.abspath(args.output)
  os.makedirs(os.path.dirname(output), exist_ok=True)
  temporary = None
  try:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=os.path.dirname(output), delete=False) as acl_file:
      temporary = acl_file.name
      acl_file.write(acl)
    os.chmod(temporary, 0o644)
    os.replace(temporary, output)
  finally:
    if temporary and os.path.exists(temporary):
      os.unlink(temporary)


if __name__ == "__main__":
  main()
