# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Status contract helpers for the Positioning service shell."""

import datetime


def status_topic(resolver_id):
  """Return the retained status topic for a resolver identity."""
  if not isinstance(resolver_id, str) or not resolver_id or any(char in resolver_id for char in "/+#"):
    raise ValueError("resolver_id must be a non-empty single MQTT topic segment")
  return f"scenescape/positioning/status/{resolver_id}"


def status_payload(resolver_id, status, timestamp=None):
  """Build the v1 liveness payload; LWT timestamps represent session start."""
  if status not in ("online", "offline"):
    raise ValueError("status must be 'online' or 'offline'")
  if timestamp is None:
    timestamp = datetime.datetime.now(datetime.timezone.utc)
  if isinstance(timestamp, datetime.datetime):
    if timestamp.tzinfo is None:
      raise ValueError("timestamp must include a timezone")
    timestamp = timestamp.astimezone(datetime.timezone.utc).isoformat(timespec="milliseconds")
    timestamp = timestamp.replace("+00:00", "Z")
  if not isinstance(timestamp, str) or not timestamp:
    raise ValueError("timestamp must be a non-empty string or timezone-aware datetime")
  status_topic(resolver_id)
  return {"resolver_id": resolver_id, "status": status, "timestamp": timestamp}