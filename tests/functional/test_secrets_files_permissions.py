#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest
from tests.utils.spec import FuncTestSpec, AUTH_CONTROLLER
from tests.utils.profiles import FULL_STACK
from tests.utils.log import get_logger

log = get_logger(__name__)

SCENESCAPE_SPEC = FuncTestSpec(
  profile=FULL_STACK,
  auth=AUTH_CONTROLLER,
)

def is_relevant_file(path):
  """Check if a file is a secrets-related file that needs permission validation."""
  return (
    path.endswith(".key") or
    path.endswith(".pem") or
    path.endswith(".auth") or
    path.endswith("secrets.py")
  )


def parse_ls_output(line):
  """Parse a single line from 'ls -la' output.

  Returns (permissions, path) tuple.
  """
  parts = line.split()
  if len(parts) < 9:
    return None
  permissions = parts[0]
  path = parts[-1]
  return (permissions, path)


def has_strict_read_only_permissions(permissions: str) -> bool:
  """Check permissions for strict read-only access.

  Args:
    permissions: 10-character permission string (e.g., '-rw-r--r--')

  Returns:
    True if group and other have read-only (r--) permission
  """
  return (
    permissions[4:7] == "r--" and
    permissions[7:10] == "r--"
  )


@pytest.mark.test_name("NEX-T10548")
def test_secrets_file_permissions(scenescape_env, result_recorder):
  """Verifies that all secrets files have expected levels of permission.

  Steps:
    * Use docker exec to find all files in /run/secrets
    * Filter to relevant secrets files (.key, .pem, .auth, secrets.py)
    * Verify each has strict read-only permissions (r--r--r--)
  """

  # Execute find and ls command in web container to list all secrets files
  cmd = "find /run/secrets -type f -exec ls -la {} \\;"
  output = scenescape_env.docker.compose.execute(
    "web",
    ["sh", "-c", cmd],
    tty=False,
  )

  # Parse output to extract permissions and paths
  file_info = []
  for line in output.splitlines():
    line = line.strip()
    if not line:
      continue
    parsed = parse_ls_output(line)
    if parsed:
      file_info.append(parsed)

  # Filter to relevant secrets files
  relevant_files = [info for info in file_info if is_relevant_file(info[1])]

  log.info(f"Found {len(relevant_files)} relevant secrets files to validate.")
  assert relevant_files, (
    "No relevant secrets files found in /run/secrets; "
    "test configuration may be incorrect."
  )

  # Validate permissions on each file
  failures = []
  for permissions, path in relevant_files:
    if not has_strict_read_only_permissions(permissions):
      msg = f"File {path} has incorrect permissions: {permissions}"
      log.error(msg)
      failures.append(msg)
    else:
      log.info(f"File {path} has correct permissions: {permissions}")

  assert not failures, "\n".join(failures)
  result_recorder.success()
