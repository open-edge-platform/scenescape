#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Re-assert secret file modes for SceneScape deployments.

Docker Compose file-backed secrets inherit host file modes; `mode:` in compose
is ignored by many Compose/Docker builds. Services that do not run as the host
UID (notably video-analytics as intelmicroserviceuser / UID 1999) cannot read
0600 CA material. Public trust material (.pem / .crt) must be 0644; private
keys and auth files stay 0600.

Idempotent — safe to run on every bootstrap and before calibration. Prints
`changed=0` or `changed=1` so callers can force-recreate video-analytics when
modes were tightened incorrectly on an older deploy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PUBLIC_SUFFIXES = {".pem", ".crt"}


def ensure_modes(secrets_dir: Path) -> int:
  """Apply modes under secrets_dir. Returns count of paths whose mode changed."""
  if not secrets_dir.is_dir():
    raise FileNotFoundError(f"secrets directory missing: {secrets_dir}")

  changed = 0
  secrets_dir.chmod(0o700)
  for path in secrets_dir.rglob("*"):
    if path.is_dir():
      want = 0o700
    elif path.suffix in PUBLIC_SUFFIXES:
      want = 0o644
    else:
      want = 0o600
    current = path.stat().st_mode & 0o777
    if current != want:
      path.chmod(want)
      changed += 1
  return changed


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--deploy-dir", required=True, type=Path)
  args = parser.parse_args()
  secrets_dir = args.deploy_dir.resolve() / "secrets"
  try:
    changed = ensure_modes(secrets_dir)
  except FileNotFoundError as exc:
    print(exc, file=sys.stderr)
    return 1
  print(f"changed={1 if changed else 0}")
  if changed:
    print(f"updated_paths={changed}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
