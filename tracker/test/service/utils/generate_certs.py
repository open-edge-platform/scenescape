#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
CLI script to generate TLS certificates for broker.

Usage:
    python -m utils.generate_certs <output_dir> [--env-file <path>]
"""

import argparse
import sys
from pathlib import Path

from .certs import generate_test_certificates


def main():
  parser = argparse.ArgumentParser(
      description="Generate TLS certificates for MQTT broker"
  )
  parser.add_argument(
      "output_dir",
      type=Path,
      help="Directory to write certificates to"
  )
  parser.add_argument(
      "--env-file",
      type=Path,
      help="Path to write .env file with TLS_* variables"
  )
  args = parser.parse_args()

  certs = generate_test_certificates(args.output_dir)
  print(f"✓ Certificates generated in {args.output_dir}")

  if args.env_file:
    args.env_file.write_text(
        f"TLS_CA_CERT_FILE={certs.ca.cert_path}\n"
        f"TLS_SERVER_CERT_FILE={certs.server.cert_path}\n"
        f"TLS_SERVER_KEY_FILE={certs.server.key_path}\n"
        f"TLS_CLIENT_CERT_FILE={certs.client.cert_path}\n"
        f"TLS_CLIENT_KEY_FILE={certs.client.key_path}\n"
    )
    print(f"✓ Environment file written to {args.env_file}")


if __name__ == "__main__":
  main()
