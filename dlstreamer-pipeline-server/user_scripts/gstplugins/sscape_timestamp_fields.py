# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Names and selection for camera-frame timestamp clocks.

MQTT ``timestamp`` is the selected clock. The others stay on the message for
audit. ``timestamp_src`` is the field name of that selected clock so a
consumer can do ``payload[payload["timestamp_src"]]``.
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

TS_RTCP = "timestamp_rtcp"
TS_POST_DECODE = "timestamp_post_decode"
TIMESTAMP_SOURCES = (TS_RTCP, TS_POST_DECODE)

_ALIASES = {
  "rtcp": TS_RTCP,
  "early": TS_RTCP,
  "ntp": TS_RTCP,
  TS_RTCP: TS_RTCP,
  "post_decode": TS_POST_DECODE,
  "post-decode": TS_POST_DECODE,
  "late": TS_POST_DECODE,
  TS_POST_DECODE: TS_POST_DECODE,
  "true": TS_RTCP,
  "false": TS_POST_DECODE,
  "1": TS_RTCP,
  "0": TS_POST_DECODE,
}


def normalize_timestamp_source(value, default: str = TS_POST_DECODE) -> str:
  """Map UI/env aliases onto a timestamp_* field name."""
  if value is True:
    return TS_RTCP
  if value is False or value is None:
    return default if value is None else TS_POST_DECODE
  text = str(value).strip()
  if not text:
    return default
  mapped = _ALIASES.get(text) or _ALIASES.get(text.lower())
  if mapped in TIMESTAMP_SOURCES:
    return mapped
  return default


def select_timestamp(clocks: dict, wanted: str) -> tuple[str, str]:
  """Return ``(iso_timestamp, timestamp_src)`` with fallback to post-decode.

  *clocks* maps field name to an ISO timestamp string (or None if missing).
  """
  source = normalize_timestamp_source(wanted)
  selected = clocks.get(source)
  if selected:
    return selected, source
  post = clocks.get(TS_POST_DECODE)
  if post:
    return post, TS_POST_DECODE
  return "", TS_POST_DECODE


def format_unix_iso(unix_seconds: float) -> str:
  """UTC millisecond ISO-8601 with Z suffix."""
  dt_utc = datetime.fromtimestamp(float(unix_seconds), tz=dt_timezone.utc)
  return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def format_epoch_ms_iso(epoch_ms) -> str | None:
  """ISO-8601 from millisecond unix epoch, or None if *epoch_ms* is unusable."""
  try:
    return format_unix_iso(int(epoch_ms) / 1000.0)
  except (TypeError, ValueError, OverflowError, OSError):
    return None
