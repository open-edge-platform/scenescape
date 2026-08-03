#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for shared ReID environment variable resolution."""

import pytest

from controller import reid_env

_REID_ENV_NAMES = (
  "REID_DATABASE", "REID_HOSTNAME", "REID_PORT", "REID_USE_TLS", "REID_API_KEY",
  "REID_CONFIDENCE_THRESHOLD", "REID_CA_CERT", "REID_CLIENT_CERT", "REID_CLIENT_KEY",
)

_RETIRED_ENV_NAMES = (
  "VDMS_HOSTNAME", "VDMS_PORT", "VDMS_USE_TLS", "VDMS_CONFIDENCE_THRESHOLD",
  "VDMS_CA_CERT", "VDMS_CLIENT_CERT", "VDMS_CLIENT_KEY",
  "QDRANT_HOSTNAME", "QDRANT_PORT", "QDRANT_USE_TLS", "QDRANT_API_KEY",
  "QDRANT_CONFIDENCE_THRESHOLD",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
  """Isolate from developer shell env so defaults are deterministic."""
  for name in _REID_ENV_NAMES + _RETIRED_ENV_NAMES:
    monkeypatch.delenv(name, raising=False)
  reid_env._SERVICE_LINK_WARNED.clear()
  yield
  reid_env._SERVICE_LINK_WARNED.clear()


class TestReidEnvDefaults:
  def test_default_database_is_vdms(self):
    assert reid_env.get_reid_database() == "VDMS"

  def test_shared_connection_defaults(self):
    assert reid_env.get_reid_hostname() == "reid.scenescape.intel.com"
    assert reid_env.get_reid_port() == 55555
    assert reid_env.get_reid_use_tls() is True
    assert reid_env.get_reid_client_cert().endswith("scenescape-reid.crt")
    assert reid_env.get_reid_client_key().endswith("scenescape-reid.key")

  def test_confidence_threshold_default(self):
    assert reid_env.get_reid_confidence_threshold() == 0.8

  def test_api_key_defaults_to_none(self):
    assert reid_env.get_reid_api_key() is None


class TestReidEnvCanonicalNames:
  def test_reid_hostname_override(self, monkeypatch):
    monkeypatch.setenv("REID_HOSTNAME", "custom.example.com")
    assert reid_env.get_reid_hostname() == "custom.example.com"

  def test_reid_database_does_not_change_connection_defaults(self, monkeypatch):
    monkeypatch.setenv("REID_DATABASE", "QDRANT")
    assert reid_env.get_reid_database() == "QDRANT"
    assert reid_env.get_reid_hostname() == "reid.scenescape.intel.com"
    assert reid_env.get_reid_port() == 55555
    assert reid_env.get_reid_use_tls() is True

  def test_reid_confidence_threshold(self, monkeypatch):
    monkeypatch.setenv("REID_CONFIDENCE_THRESHOLD", "0.91")
    assert reid_env.get_reid_confidence_threshold() == 0.91

  def test_reid_use_tls_accepts_false_values(self, monkeypatch):
    monkeypatch.setenv("REID_USE_TLS", "false")
    assert reid_env.get_reid_use_tls() is False

  def test_values_are_trimmed(self, monkeypatch):
    monkeypatch.setenv("REID_HOSTNAME", "  spaced.example.com  ")
    monkeypatch.setenv("REID_PORT", " 6543 ")
    assert reid_env.get_reid_hostname() == "spaced.example.com"
    assert reid_env.get_reid_port() == 6543

  def test_blank_values_fall_back_to_defaults(self, monkeypatch):
    monkeypatch.setenv("REID_HOSTNAME", "   ")
    monkeypatch.setenv("REID_PORT", "")
    assert reid_env.get_reid_hostname() == "reid.scenescape.intel.com"
    assert reid_env.get_reid_port() == 55555


class TestStrictParsing:
  """Malformed values must fail loudly instead of silently using a default."""

  @pytest.mark.parametrize("value", ["5555o", "6543.0", "port", "-1", "0", "65536"])
  def test_invalid_port_is_rejected(self, monkeypatch, value):
    monkeypatch.setenv("REID_PORT", value)
    with pytest.raises(ValueError) as excinfo:
      reid_env.get_reid_port()
    message = str(excinfo.value)
    assert "REID_PORT" in message
    assert value in message
    assert "between 1 and 65535" in message

  @pytest.mark.parametrize("value", ["1", "55555", "65535"])
  def test_port_boundaries_are_accepted(self, monkeypatch, value):
    monkeypatch.setenv("REID_PORT", value)
    assert reid_env.get_reid_port() == int(value)

  @pytest.mark.parametrize("value", ["0.8.1", "high", "5.0", "-0.1", "nan", "inf"])
  def test_invalid_confidence_threshold_is_rejected(self, monkeypatch, value):
    monkeypatch.setenv("REID_CONFIDENCE_THRESHOLD", value)
    with pytest.raises(ValueError) as excinfo:
      reid_env.get_reid_confidence_threshold()
    message = str(excinfo.value)
    assert "REID_CONFIDENCE_THRESHOLD" in message
    assert value in message
    assert "between 0.0 and 1.0" in message

  @pytest.mark.parametrize("value", ["0", "0.0", "0.5", "1", "1.0"])
  def test_confidence_threshold_boundaries_are_accepted(self, monkeypatch, value):
    monkeypatch.setenv("REID_CONFIDENCE_THRESHOLD", value)
    assert reid_env.get_reid_confidence_threshold() == float(value)

  @pytest.mark.parametrize("value", ["disabled", "enabled", "tru", "2", "none"])
  def test_unrecognized_tls_value_does_not_silently_disable_tls(
      self, monkeypatch, value):
    """A typo must not quietly drop the connection to plaintext."""
    monkeypatch.setenv("REID_USE_TLS", value)
    with pytest.raises(ValueError) as excinfo:
      reid_env.get_reid_use_tls()
    message = str(excinfo.value)
    assert "REID_USE_TLS" in message
    assert value in message

  def test_blank_tls_value_keeps_secure_default(self, monkeypatch):
    monkeypatch.setenv("REID_USE_TLS", "  ")
    assert reid_env.get_reid_use_tls() is True

  @pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on"])
  def test_true_spellings(self, monkeypatch, value):
    monkeypatch.setenv("REID_USE_TLS", value)
    assert reid_env.get_reid_use_tls() is True

  @pytest.mark.parametrize("value", ["0", "false", "FALSE", "No", "off"])
  def test_false_spellings(self, monkeypatch, value):
    monkeypatch.setenv("REID_USE_TLS", value)
    assert reid_env.get_reid_use_tls() is False


class TestKubernetesServiceLinks:
  """A Service named "reid" injects REID_PORT=tcp://<ip>:<port> into the pod."""

  def test_service_link_port_falls_back_to_default(self, monkeypatch):
    monkeypatch.setenv("REID_PORT", "tcp://10.96.145.86:55555")
    assert reid_env.get_reid_port() == 55555

  def test_service_link_hostname_falls_back_to_default(self, monkeypatch):
    monkeypatch.setenv("REID_HOSTNAME", "tcp://10.96.145.86:55555")
    assert reid_env.get_reid_hostname() == "reid.scenescape.intel.com"

  def test_service_link_is_warned_once_per_variable(self, monkeypatch):
    monkeypatch.setenv("REID_PORT", "tcp://10.96.145.86:55555")
    reid_env.get_reid_port()
    reid_env.get_reid_port()
    assert reid_env._SERVICE_LINK_WARNED == {"REID_PORT"}

  def test_explicit_port_still_wins_over_service_link_shape(self, monkeypatch):
    """An operator-set value is unaffected by the service-link guard."""
    monkeypatch.setenv("REID_PORT", "6543")
    assert reid_env.get_reid_port() == 6543
    assert reid_env._SERVICE_LINK_WARNED == set()

  def test_malformed_port_still_raises(self, monkeypatch):
    """The guard must not swallow genuine typos."""
    monkeypatch.setenv("REID_PORT", "tcp:/typo")
    with pytest.raises(ValueError):
      reid_env.get_reid_port()


class TestRetiredBackendSpecificNames:
  """Backend-prefixed names were removed; only REID_* is honored."""

  def test_legacy_hostname_names_are_ignored(self, monkeypatch):
    monkeypatch.setenv("VDMS_HOSTNAME", "legacy-vdms.example.com")
    monkeypatch.setenv("QDRANT_HOSTNAME", "legacy-qdrant.example.com")
    assert reid_env.get_reid_hostname() == "reid.scenescape.intel.com"

  def test_legacy_port_and_tls_names_are_ignored(self, monkeypatch):
    monkeypatch.setenv("QDRANT_PORT", "6334")
    monkeypatch.setenv("QDRANT_USE_TLS", "false")
    assert reid_env.get_reid_port() == 55555
    assert reid_env.get_reid_use_tls() is True

  def test_legacy_confidence_and_cert_names_are_ignored(self, monkeypatch):
    monkeypatch.setenv("VDMS_CONFIDENCE_THRESHOLD", "0.75")
    monkeypatch.setenv("VDMS_CA_CERT", "/tmp/legacy-ca.pem")
    monkeypatch.setenv("QDRANT_API_KEY", "legacy-key")
    assert reid_env.get_reid_confidence_threshold() == 0.8
    assert reid_env.get_reid_ca_cert() == "/run/secrets/certs/scenescape-ca.pem"
    assert reid_env.get_reid_api_key() is None
