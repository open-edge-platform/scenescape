# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Deployment-owned PTZ source configuration and single-owner assignment checks.

Device endpoints and credential file paths belong to deployment configuration;
credentials themselves are read from mounted secrets, never from this config.
"""

import json
import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union

from positioning.onvif import OnvifPtzDevice, load_credentials
from positioning.ptz_poller import MOVE_STATUS_MODES, MoveEventMonitor, PTZPoller

DEFAULT_POLL_INTERVAL_S = 0.2
DEFAULT_REQUEST_TIMEOUT_S = 1.0
SOURCE_TYPE_ONVIF_PTZ = "onvif_ptz"

_TOP_LEVEL_KEYS = {"resolver_id", "poll_interval_s", "sources"}
_SOURCE_KEYS = {
  "type", "host", "port", "scheme", "profile_token", "credentials_file", "tls_ca_file",
  "request_timeout_s", "move_status", "move_event",
}
_MOVE_EVENT_KEYS = {"topic", "data_item"}
_FORBIDDEN_HOST_CHARS = set(" \t\r\n/\\@?#")


class SourceConfigError(ValueError):
  """Invalid source configuration or source-to-resolver assignment."""


@dataclass(frozen=True)
class MoveEventConfig:
  topic: str
  data_item: str


@dataclass(frozen=True)
class OnvifSourceConfig:
  source_id: str
  host: str
  port: int
  scheme: str
  profile_token: Optional[str]
  credentials_file: str
  tls_verify: Union[bool, str]
  request_timeout_s: float
  move_status: str
  move_event: Optional[MoveEventConfig]


def _is_topic_segment(value):
  return isinstance(value, str) and bool(value) and not any(char in value for char in "/+#")


def _positive_number(value, name):
  if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
      or value <= 0:
    raise SourceConfigError(f"{name} must be a positive finite number")
  return float(value)


def _non_empty_string(value, name):
  if not isinstance(value, str) or not value.strip():
    raise SourceConfigError(f"{name} must be a non-empty string")
  return value.strip()


def _check_keys(mapping, allowed, where):
  unknown = sorted(key for key in mapping if key not in allowed and not key.startswith("$"))
  if unknown:
    raise SourceConfigError(f"Unknown keys in {where}: {', '.join(unknown)}")


def _parse_source(source_id, raw):
  where = f"source '{source_id}'"
  if not isinstance(raw, dict):
    raise SourceConfigError(f"{where} must be an object")
  _check_keys(raw, _SOURCE_KEYS, where)
  if raw.get("type") != SOURCE_TYPE_ONVIF_PTZ:
    raise SourceConfigError(f"{where}: type must be '{SOURCE_TYPE_ONVIF_PTZ}'")
  host = _non_empty_string(raw.get("host"), f"{where} host")
  if _FORBIDDEN_HOST_CHARS.intersection(host):
    raise SourceConfigError(f"{where}: host must be a bare hostname or IP address")
  port = raw.get("port", 80)
  if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
    raise SourceConfigError(f"{where}: port must be an integer in 1..65535")
  scheme = raw.get("scheme", "http")
  if scheme not in ("http", "https"):
    raise SourceConfigError(f"{where}: scheme must be 'http' or 'https'")
  profile_token = raw.get("profile_token")
  if profile_token is not None:
    profile_token = _non_empty_string(profile_token, f"{where} profile_token")
  tls_ca_file = raw.get("tls_ca_file")
  if tls_ca_file is not None and scheme != "https":
    raise SourceConfigError(f"{where}: tls_ca_file requires scheme 'https'")
  move_status = raw.get("move_status", "get_status")
  if move_status not in MOVE_STATUS_MODES:
    raise SourceConfigError(f"{where}: move_status must be one of {', '.join(MOVE_STATUS_MODES)}")
  move_event = None
  if raw.get("move_event") is not None:
    event = raw["move_event"]
    if not isinstance(event, dict):
      raise SourceConfigError(f"{where}: move_event must be an object")
    _check_keys(event, _MOVE_EVENT_KEYS, f"{where} move_event")
    move_event = MoveEventConfig(
      _non_empty_string(event.get("topic"), f"{where} move_event.topic").strip("/"),
      _non_empty_string(event.get("data_item"), f"{where} move_event.data_item"))
  if move_status == "event" and move_event is None:
    raise SourceConfigError(f"{where}: move_status 'event' requires move_event")
  return OnvifSourceConfig(
    source_id=source_id,
    host=host,
    port=port,
    scheme=scheme,
    profile_token=profile_token,
    credentials_file=_non_empty_string(raw.get("credentials_file"), f"{where} credentials_file"),
    tls_verify=_non_empty_string(tls_ca_file, f"{where} tls_ca_file") if tls_ca_file else True,
    request_timeout_s=_positive_number(
      raw.get("request_timeout_s", DEFAULT_REQUEST_TIMEOUT_S), f"{where} request_timeout_s"),
    move_status=move_status,
    move_event=move_event)


def parse_sources(config) -> Tuple[float, Dict[str, OnvifSourceConfig]]:
  """Return `(poll_interval_s, sources)` from the Positioning config object."""
  if not isinstance(config, dict):
    raise SourceConfigError("Positioning config must be a JSON object")
  _check_keys(config, _TOP_LEVEL_KEYS, "Positioning config")
  poll_interval_s = _positive_number(
    config.get("poll_interval_s", DEFAULT_POLL_INTERVAL_S), "poll_interval_s")
  raw_sources = config.get("sources", {})
  if not isinstance(raw_sources, dict):
    raise SourceConfigError("sources must be an object keyed by source_id")
  sources = {}
  for source_id, raw in raw_sources.items():
    if source_id.startswith("$"):
      continue
    if not _is_topic_segment(source_id):
      raise SourceConfigError(f"source_id '{source_id}' must be a single MQTT topic segment")
    sources[source_id] = _parse_source(source_id, raw)
  return poll_interval_s, sources


def load_assignments(path):
  """Read the shared `source_id -> resolver_id` manifest."""
  with open(path, "r", encoding="utf-8") as manifest_file:
    try:
      manifest = json.load(manifest_file)
    except json.JSONDecodeError as error:
      raise SourceConfigError(f"Assignment manifest is not valid JSON: {path}") from error
  if not isinstance(manifest, dict):
    raise SourceConfigError("Assignment manifest must be a JSON object")
  assignments = {}
  for source_id, resolver_id in manifest.items():
    if source_id.startswith("$"):
      continue
    if not _is_topic_segment(source_id) or not _is_topic_segment(resolver_id):
      raise SourceConfigError(
        f"Assignment '{source_id}' must map a source_id to a resolver_id topic segment")
    assignments[source_id] = resolver_id
  return assignments


def validate_assignments(resolver_id, sources, assignments):
  """Every configured source must be owned by this resolver, and vice versa."""
  errors = []
  for source_id in sorted(sources):
    owner = assignments.get(source_id)
    if owner is None:
      errors.append(f"configured source '{source_id}' is missing from the assignment manifest")
    elif owner != resolver_id:
      errors.append(f"configured source '{source_id}' is assigned to resolver '{owner}'")
  for source_id in sorted(assignments):
    if assignments[source_id] == resolver_id and source_id not in sources:
      errors.append(f"source '{source_id}' is assigned to this resolver but not configured")
  if errors:
    raise SourceConfigError("; ".join(errors))


def device_factory(source: OnvifSourceConfig, credentials):
  def create():
    return OnvifPtzDevice(source.host, source.port, credentials, scheme=source.scheme,
                          timeout_s=source.request_timeout_s, verify=source.tls_verify,
                          profile_token=source.profile_token)
  return create


def build_pollers(sources, poll_interval_s, sink):
  """Create one poller (plus optional move-event monitor) per configured source."""
  pollers = []
  for source in sources.values():
    try:
      credentials = load_credentials(source.credentials_file)
    except (OSError, ValueError) as error:
      raise SourceConfigError(
        f"source '{source.source_id}': cannot read credentials_file: {error}") from None
    factory = device_factory(source, credentials)
    monitor = None
    if source.move_event is not None:
      monitor = MoveEventMonitor(source.source_id, factory, source.move_event.topic,
                                 source.move_event.data_item)
    pollers.append(PTZPoller(source.source_id, factory, sink, poll_interval_s,
                             source.move_status, monitor))
  return pollers
