# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess

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


def test_file_permissions(test_logger):
  """ Verifies that files have sufficient permissions.

  Steps:
    * Get web container name
    * Run command in service
    * Verify file permissions
  """
  test_name = "NEX-T10548"
  log = test_logger
  log.info(f"Test: {test_name}")

  web_container = get_container_name('web', log)

  cmd = ["find", "run/secrets/", "-type", "f", "|", "xargs", "ls", "-la",]

  response = run_find(web_container, cmd)
