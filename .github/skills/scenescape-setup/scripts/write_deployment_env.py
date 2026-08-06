# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Write the deployment environment file from generated SceneScape secrets.

Usage:
  python write_deployment_env.py --deploy-dir <deploy_dir>
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


def read_database_password(secrets_py: Path) -> str:
  text = secrets_py.read_text(encoding="utf-8")
  match = re.search(r"DATABASE_PASSWORD='([^']+)'", text)
  if not match:
    raise ValueError(f"DATABASE_PASSWORD not found in {secrets_py}")
  return match.group(1)


def join_no_proxy(*parts: str) -> str:
  """Join no_proxy host entries, skipping blanks and avoiding duplicate commas."""
  hosts: list[str] = []
  seen: set[str] = set()
  for part in parts:
    for host in part.split(","):
      host = host.strip()
      if host and host not in seen:
        seen.add(host)
        hosts.append(host)
  return ",".join(hosts)


def main() -> None:
  parser = argparse.ArgumentParser(
    description="Write the deployment environment file from generated secrets",
  )
  parser.add_argument("--deploy-dir", required=True, type=Path)
  parser.add_argument(
    "--append-no-proxy",
    action="append",
    default=[],
    metavar="HOST",
    help="Internal hostname to add to no_proxy (repeatable; safe when no_proxy is empty)",
  )
  args = parser.parse_args()

  deploy_dir = args.deploy_dir
  secrets_dir = deploy_dir / "secrets"

  database_password = read_database_password(secrets_dir / "django" / "secrets.py")
  supass = (secrets_dir / "supass").read_text(encoding="utf-8").strip()
  no_proxy = join_no_proxy(os.getenv("no_proxy", ""), os.getenv("NO_PROXY", ""), *args.append_no_proxy)

  env_text = "\n".join(
    [
      f"SECRETSDIR={secrets_dir}",
      f"DATABASE_PASSWORD={database_password}",
      f"SUPASS={supass}",
      f"VERSION={os.getenv('VERSION', 'latest')}",
      f"UID={os.getenv('UID', str(os.getuid()))}",
      f"GID={os.getenv('GID', str(os.getgid()))}",
      f"http_proxy={os.getenv('http_proxy', '')}",
      f"https_proxy={os.getenv('https_proxy', '')}",
      f"no_proxy={no_proxy}",
      f"NO_PROXY={no_proxy}",
      "",
    ]
  )
  # Holds DATABASE_PASSWORD and SUPASS, so create it owner-only before writing
  # and re-apply the mode in case the file already existed.
  env_path = deploy_dir / ".env"
  descriptor = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
  with os.fdopen(descriptor, "w", encoding="utf-8") as env_file:
    env_file.write(env_text)
  os.chmod(env_path, 0o600)


if __name__ == "__main__":
  main()
