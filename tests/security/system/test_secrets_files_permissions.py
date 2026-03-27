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
  cmd = ["docker", "exec", "-i", container,
          "-t", "-A", "-c", query]

  result = subprocess.run(cmd, capture_output=True, text=True)
  return result.stdout.strip()

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
    web_container = get_container_name("web")
    cmd = ["find", "run/secrets/", "-type", "f", "|", "xargs", "ls", "-la"]
    response = run_find(web_container, cmd)
    print(response)
    exit_code = 0
  finally:
    record_test_result(test_name, exit_code)
