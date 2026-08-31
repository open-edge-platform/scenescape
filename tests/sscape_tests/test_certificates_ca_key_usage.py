#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression checks for Scenescape root CA extensions required by OpenSSL 3.2+/Python 3.14."""

import subprocess
from pathlib import Path

import pytest

TEST_NAME = "NEX-T28254"

REPO_ROOT = Path(__file__).resolve().parents[2]
CA_PEM = REPO_ROOT / "manager" / "secrets" / "certs" / "scenescape-ca.pem"
WEB_CRT = REPO_ROOT / "manager" / "secrets" / "certs" / "scenescape-web.crt"
OPENSSL_CA_CNF = REPO_ROOT / "tools" / "certificates" / "openssl-ca.cnf"


def test_openssl_ca_cnf_declares_key_usage():
  """Positive: CA openssl config requires critical keyCertSign/cRLSign."""
  text = OPENSSL_CA_CNF.read_text(encoding="utf-8")
  assert "keyUsage" in text
  assert "keyCertSign" in text
  assert "cRLSign" in text
  assert "basicConstraints" in text


def test_generated_ca_includes_key_usage_extension():
  """Positive: minted root CA includes Key Usage (Certificate Sign, CRL Sign)."""
  if not CA_PEM.is_file():
    pytest.skip("CA not generated yet (run make init-secrets)")
  result = subprocess.run(
    ["openssl", "x509", "-in", str(CA_PEM), "-noout", "-text"],
    capture_output=True, text=True, check=False,
  )
  assert result.returncode == 0, result.stderr
  assert "X509v3 Key Usage" in result.stdout
  assert "Certificate Sign" in result.stdout
  assert "CRL Sign" in result.stdout


def test_openssl_verify_web_cert_against_ca():
  """Positive: leaf web cert chains to CA under current OpenSSL."""
  if not (CA_PEM.is_file() and WEB_CRT.is_file()):
    pytest.skip("certs not generated yet (run make init-secrets)")
  result = subprocess.run(
    ["openssl", "verify", "-CAfile", str(CA_PEM), str(WEB_CRT)],
    capture_output=True, text=True, check=False,
  )
  assert result.returncode == 0, result.stderr or result.stdout
  assert "OK" in result.stdout


def test_negative_ca_config_requires_critical_basic_constraints():
  """Negative: CA config must mark basicConstraints CA:TRUE as critical."""
  text = OPENSSL_CA_CNF.read_text(encoding="utf-8")
  assert "basicConstraints = critical, CA:TRUE" in text
