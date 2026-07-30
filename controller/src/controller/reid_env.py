# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared ReID environment variable resolution.

Connection and tuning knobs use REID_* names and are backend-agnostic.
Only REID_DATABASE selects which adapter runs.

Every getter runs while the adapter is being constructed, so a malformed value
raises at controller startup rather than degrading behaviour at query time.
"""

import os

from scene_common import log

DEFAULT_DATABASE = "VDMS"
DEFAULT_HOSTNAME = "reid.scenescape.intel.com"
DEFAULT_PORT = 55555
DEFAULT_USE_TLS = True
DEFAULT_CONFIDENCE_THRESHOLD = 0.8
DEFAULT_CA_CERT = "/run/secrets/certs/scenescape-ca.pem"
DEFAULT_CLIENT_CERT = "/run/secrets/certs/scenescape-reid.crt"
DEFAULT_CLIENT_KEY = "/run/secrets/certs/scenescape-reid.key"
# Descriptor lifetime in seconds (0 disables retention). 86400 = 24 hours.
DEFAULT_DESCRIPTOR_TTL_SECS = 86400
# How often the controller asks the active backend to purge expired descriptors.
DEFAULT_PURGE_INTERVAL_SECS = 300

PORT_RANGE = (1, 65535)
CONFIDENCE_THRESHOLD_RANGE = (0.0, 1.0)
# Upper bound is generous (about 10 years) so operators can tune long-lived demos.
DESCRIPTOR_TTL_RANGE = (0, 315360000)
PURGE_INTERVAL_RANGE = (1, 86400)

_TRUE_VALUES = ("1", "true", "yes", "on")
_FALSE_VALUES = ("0", "false", "no", "off")

# Kubernetes injects service-link variables for every Service in the namespace.
# A Service named "reid" produces REID_PORT=tcp://<clusterIP>:<port>, which
# lands in this module's namespace. Such a value is never operator config, so
# treat it as unset instead of failing to parse it.
_SERVICE_LINK_SCHEMES = ("tcp://", "udp://")

_SERVICE_LINK_WARNED = set()


def _parse_error(name, value, expected):
  """Build a ValueError naming the variable, its value, and the accepted form."""
  return ValueError(f"Invalid {name}='{value}': expected {expected}")


def _is_service_link(name, value):
  """Report whether value is a Kubernetes service-link URL rather than config."""
  if not value.startswith(_SERVICE_LINK_SCHEMES):
    return False
  if name not in _SERVICE_LINK_WARNED:
    _SERVICE_LINK_WARNED.add(name)
    log.warning(
      f"Ignoring {name}='{value}': this looks like a Kubernetes service-link "
      f"variable, not ReID configuration. Set enableServiceLinks: false on the "
      f"pod, or set {name} explicitly to override the default.")
  return True


def _env_value(name, default=None):
  """Return the trimmed value of name, or default when unset or blank."""
  value = os.getenv(name)
  if value is None or str(value).strip() == "":
    return default
  value = str(value).strip()
  if _is_service_link(name, value):
    return default
  return value


def _env_int(name, default, value_range):
  """Return an integer env value, rejecting non-numeric or out-of-range input."""
  raw = _env_value(name)
  if raw is None:
    return int(default)

  low, high = value_range
  expected = f"an integer between {low} and {high}"
  try:
    parsed = int(raw)
  except ValueError:
    raise _parse_error(name, raw, expected) from None
  if not low <= parsed <= high:
    raise _parse_error(name, raw, expected)
  return parsed


def _env_float(name, default, value_range):
  """Return a float env value, rejecting non-numeric, NaN, or out-of-range input."""
  raw = _env_value(name)
  if raw is None:
    return float(default)

  low, high = value_range
  expected = f"a number between {low} and {high}"
  try:
    parsed = float(raw)
  except ValueError:
    raise _parse_error(name, raw, expected) from None
  # NaN fails every comparison, so this also rejects it.
  if not low <= parsed <= high:
    raise _parse_error(name, raw, expected)
  return parsed


def _env_bool(name, default):
  """Return a boolean env value, rejecting words that are neither true nor false."""
  raw = _env_value(name)
  if raw is None:
    return bool(default)

  lowered = raw.lower()
  if lowered in _TRUE_VALUES:
    return True
  if lowered in _FALSE_VALUES:
    return False
  raise _parse_error(
    name, raw,
    f"one of {', '.join(_TRUE_VALUES)} (true) or {', '.join(_FALSE_VALUES)} (false)")


def get_reid_database():
  """Return selected ReID backend name (uppercase).

  Membership is validated by controller.reid_registry, which owns the set of
  available adapters.
  """
  return _env_value("REID_DATABASE", DEFAULT_DATABASE).upper()


def get_reid_hostname():
  """Return shared ReID database hostname."""
  return _env_value("REID_HOSTNAME", DEFAULT_HOSTNAME)


def get_reid_port():
  """Return shared ReID database port."""
  return _env_int("REID_PORT", DEFAULT_PORT, PORT_RANGE)


def get_reid_use_tls():
  """Return whether TLS should be used for the ReID database connection."""
  return _env_bool("REID_USE_TLS", DEFAULT_USE_TLS)


def get_reid_api_key():
  """Return optional ReID API key (used by backends that support it)."""
  return _env_value("REID_API_KEY")


def get_reid_confidence_threshold():
  """Return TIER 1 metadata confidence threshold."""
  return _env_float(
    "REID_CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD,
    CONFIDENCE_THRESHOLD_RANGE)


def get_reid_ca_cert():
  """Return CA certificate path for TLS backends."""
  return _env_value("REID_CA_CERT", DEFAULT_CA_CERT)


def get_reid_client_cert():
  """Return client certificate path for mTLS backends."""
  return _env_value("REID_CLIENT_CERT", DEFAULT_CLIENT_CERT)


def get_reid_client_key():
  """Return client key path for mTLS backends."""
  return _env_value("REID_CLIENT_KEY", DEFAULT_CLIENT_KEY)


def get_reid_descriptor_ttl_secs():
  """Return descriptor time-to-live in seconds (0 disables retention)."""
  return _env_int(
    "REID_DESCRIPTOR_TTL_SECS", DEFAULT_DESCRIPTOR_TTL_SECS,
    DESCRIPTOR_TTL_RANGE)


def get_reid_purge_interval_secs():
  """Return how often the controller triggers backend purgeExpired()."""
  return _env_int(
    "REID_PURGE_INTERVAL_SECS", DEFAULT_PURGE_INTERVAL_SECS,
    PURGE_INTERVAL_RANGE)
