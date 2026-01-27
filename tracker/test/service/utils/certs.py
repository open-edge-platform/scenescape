#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
TLS certificate generation utilities for service tests.

Generates self-signed CA, server, and client certificates for testing
MQTT TLS connections. Uses the cryptography library.
"""

import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID


@dataclass
class CertificateBundle:
  """Container for certificate and key file paths."""

  cert_path: Path
  key_path: Path


@dataclass
class TlsTestCerts:
  """Complete set of test certificates."""

  ca: CertificateBundle
  server: CertificateBundle
  client: CertificateBundle
  temp_dir: Path


def generate_private_key() -> rsa.RSAPrivateKey:
  """Generate RSA private key."""
  return rsa.generate_private_key(
      public_exponent=65537,
      key_size=2048,
  )


def generate_ca_certificate(
    ca_key: rsa.RSAPrivateKey,
    validity_days: int = 365,
) -> x509.Certificate:
  """
  Generate a self-signed CA certificate.

  Args:
      ca_key: CA private key
      validity_days: Certificate validity period

  Returns:
      Self-signed CA certificate
  """
  subject = issuer = x509.Name([
      x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
      x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Oregon"),
      x509.NameAttribute(NameOID.LOCALITY_NAME, "Hillsboro"),
      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Intel Corporation"),
      x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Test CA"),
      x509.NameAttribute(NameOID.COMMON_NAME, "Tracker Test CA"),
  ])

  now = datetime.now(timezone.utc)
  cert = (
      x509.CertificateBuilder()
      .subject_name(subject)
      .issuer_name(issuer)
      .public_key(ca_key.public_key())
      .serial_number(x509.random_serial_number())
      .not_valid_before(now)
      .not_valid_after(now + timedelta(days=validity_days))
      .add_extension(
          x509.BasicConstraints(ca=True, path_length=0),
          critical=True,
      )
      .add_extension(
          x509.KeyUsage(
              digital_signature=True,
              content_commitment=False,
              key_encipherment=False,
              data_encipherment=False,
              key_agreement=False,
              key_cert_sign=True,
              crl_sign=True,
              encipher_only=False,
              decipher_only=False,
          ),
          critical=True,
      )
      .add_extension(
          x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
          critical=False,
      )
      .sign(ca_key, hashes.SHA256())
  )

  return cert


def generate_server_certificate(
    server_key: rsa.RSAPrivateKey,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    hostnames: list[str] = None,
    validity_days: int = 365,
) -> x509.Certificate:
  """
  Generate a server certificate signed by the CA.

  Args:
      server_key: Server private key
      ca_key: CA private key for signing
      ca_cert: CA certificate
      hostnames: List of hostnames for SAN (default: localhost, broker)
      validity_days: Certificate validity period

  Returns:
      Server certificate signed by CA
  """
  if hostnames is None:
    hostnames = ["localhost", "broker", "127.0.0.1"]

  subject = x509.Name([
      x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
      x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Oregon"),
      x509.NameAttribute(NameOID.LOCALITY_NAME, "Hillsboro"),
      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Intel Corporation"),
      x509.NameAttribute(NameOID.COMMON_NAME, "broker"),
  ])

  # Build SAN extension with DNS names and IP addresses
  san_entries = []
  for hostname in hostnames:
    # Check if it's an IP address
    try:
      import ipaddress
      ip = ipaddress.ip_address(hostname)
      san_entries.append(x509.IPAddress(ip))
    except ValueError:
      san_entries.append(x509.DNSName(hostname))

  now = datetime.now(timezone.utc)
  cert = (
      x509.CertificateBuilder()
      .subject_name(subject)
      .issuer_name(ca_cert.subject)
      .public_key(server_key.public_key())
      .serial_number(x509.random_serial_number())
      .not_valid_before(now)
      .not_valid_after(now + timedelta(days=validity_days))
      .add_extension(
          x509.BasicConstraints(ca=False, path_length=None),
          critical=True,
      )
      .add_extension(
          x509.KeyUsage(
              digital_signature=True,
              content_commitment=False,
              key_encipherment=True,
              data_encipherment=False,
              key_agreement=False,
              key_cert_sign=False,
              crl_sign=False,
              encipher_only=False,
              decipher_only=False,
          ),
          critical=True,
      )
      .add_extension(
          x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
          critical=False,
      )
      .add_extension(
          x509.SubjectAlternativeName(san_entries),
          critical=False,
      )
      .sign(ca_key, hashes.SHA256())
  )

  return cert


def generate_client_certificate(
    client_key: rsa.RSAPrivateKey,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    common_name: str = "tracker-client",
    validity_days: int = 365,
) -> x509.Certificate:
  """
  Generate a client certificate signed by the CA.

  Args:
      client_key: Client private key
      ca_key: CA private key for signing
      ca_cert: CA certificate
      common_name: Client common name
      validity_days: Certificate validity period

  Returns:
      Client certificate signed by CA
  """
  subject = x509.Name([
      x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
      x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Oregon"),
      x509.NameAttribute(NameOID.LOCALITY_NAME, "Hillsboro"),
      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Intel Corporation"),
      x509.NameAttribute(NameOID.COMMON_NAME, common_name),
  ])

  now = datetime.now(timezone.utc)
  cert = (
      x509.CertificateBuilder()
      .subject_name(subject)
      .issuer_name(ca_cert.subject)
      .public_key(client_key.public_key())
      .serial_number(x509.random_serial_number())
      .not_valid_before(now)
      .not_valid_after(now + timedelta(days=validity_days))
      .add_extension(
          x509.BasicConstraints(ca=False, path_length=None),
          critical=True,
      )
      .add_extension(
          x509.KeyUsage(
              digital_signature=True,
              content_commitment=False,
              key_encipherment=True,
              data_encipherment=False,
              key_agreement=False,
              key_cert_sign=False,
              crl_sign=False,
              encipher_only=False,
              decipher_only=False,
          ),
          critical=True,
      )
      .add_extension(
          x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
          critical=False,
      )
      .sign(ca_key, hashes.SHA256())
  )

  return cert


def write_cert(cert: x509.Certificate, path: Path) -> None:
  """Write certificate to PEM file."""
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def write_key(key: rsa.RSAPrivateKey, path: Path) -> None:
  """Write private key to PEM file (unencrypted)."""
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_bytes(
      key.private_bytes(
          encoding=serialization.Encoding.PEM,
          format=serialization.PrivateFormat.TraditionalOpenSSL,
          encryption_algorithm=serialization.NoEncryption(),
      )
  )


def generate_test_certificates(temp_dir: Path = None) -> TlsTestCerts:
  """
  Generate complete set of test certificates.

  Creates CA, server, and client certificates in a temporary directory.
  The caller is responsible for cleanup (or use as context manager).

  Args:
      temp_dir: Optional directory to use; creates temp dir if None

  Returns:
      TlsTestCerts with paths to all certificate files
  """
  if temp_dir is None:
    temp_dir = Path(tempfile.mkdtemp(prefix="tracker-tls-test-"))
  else:
    temp_dir.mkdir(parents=True, exist_ok=True)

  # Generate CA
  ca_key = generate_private_key()
  ca_cert = generate_ca_certificate(ca_key)
  ca_cert_path = temp_dir / "ca.crt"
  ca_key_path = temp_dir / "ca.key"
  write_cert(ca_cert, ca_cert_path)
  write_key(ca_key, ca_key_path)

  # Generate server certificate
  server_key = generate_private_key()
  server_cert = generate_server_certificate(server_key, ca_key, ca_cert)
  server_cert_path = temp_dir / "server.crt"
  server_key_path = temp_dir / "server.key"
  write_cert(server_cert, server_cert_path)
  write_key(server_key, server_key_path)

  # Generate client certificate
  client_key = generate_private_key()
  client_cert = generate_client_certificate(client_key, ca_key, ca_cert)
  client_cert_path = temp_dir / "client.crt"
  client_key_path = temp_dir / "client.key"
  write_cert(client_cert, client_cert_path)
  write_key(client_key, client_key_path)

  return TlsTestCerts(
      ca=CertificateBundle(cert_path=ca_cert_path, key_path=ca_key_path),
      server=CertificateBundle(cert_path=server_cert_path, key_path=server_key_path),
      client=CertificateBundle(cert_path=client_cert_path, key_path=client_key_path),
      temp_dir=temp_dir,
  )
