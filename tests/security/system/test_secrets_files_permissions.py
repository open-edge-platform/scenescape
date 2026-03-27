# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess
from scene_common import log
from tests.common_test_utils import record_test_result

def get_container_name(pattern, log):
  """Returns the name of a container with specific pattern in name"""

  cmd = ["docker", "ps", "--format", "{{.Names}}"]
  result = subprocess.run(cmd, capture_output=True, text=True)
  containers = result.stdout.splitlines()

  for name in containers:
    if pattern in name:
      log.info(f"Container {pattern} found in the container list.")
      return name

  log.info(f"Container {pattern} not found in the container list.")
  return None

def run_find(container, query):
  cmd = ["docker", "exec", container,
          "bash", "-c", query]

  result = subprocess.run(cmd, capture_output=True, text=True)
  assert result.returncode == 0, (
    f"docker exec failed with exit code {result.returncode}: {result.stderr}"
  )
  return result.stdout

def parse_find_output(output):
  rows = []

  for line in output.splitlines():
    line = line.strip()
    if not line:
      continue
    parts = line.split()
    permissions = parts[0]
    path = parts[-1]
    rows.append((permissions, path))
  return rows

def is_relevant_file(path):
  return (
    path.endswith(".key") or
    path.endswith(".pem") or
    path.endswith(".auth") or
    path.endswith("secrets.py")
  )

def has_strict_read_only_permissions(permissions: str) -> bool:
  return (
    permissions[4:7] == "r--" and
    permissions[7:10] == "r--"
  )

def validate_file_permissions(file_info):
  for permissions, path in file_info:
    if not is_relevant_file(path):
      continue
    if not has_strict_read_only_permissions(permissions):
      log.error(f"File {path} has incorrect permissions: {permissions}")
      return False
    log.info(f"File {path} has correct permissions: {permissions}")
  return True

def test_secrets_file_permissions():
  """ Verifies that all secrets files have expected levels of permission.

  Steps:
    * Get web container name
    * Run find command to obtain file data
    * compare to the expected pattern
  """
  test_name = "NEX-T10548"
  exit_code = 1
  log.info(f"Test: {test_name}")
  try:
    web_container = get_container_name("web", log)
    cmd = "find /run/secrets -type f -exec ls -la {} \\;"
    response = run_find(web_container, cmd)
    file_info = parse_find_output(response)
    relevant_files = [info for info in file_info if is_relevant_file(info[1])]
    assert validate_file_permissions(relevant_files)
    exit_code = 0
  finally:
    record_test_result(test_name, exit_code)
